"""
Weak ground truth for the Laya sweep from git history (SZZ). A file change that
a later bug fix had to repair is a REJECT; one that lived on without such a fix
is an APPROVE. It reads the sweep's data directory and adds to it, and can run
while tools/run_laya_sweep.py is still reviewing.

    py tools/label_laya_sweep.py mine     # blame every fix commit (slow; resumes, safe to kill)
    py tools/label_laya_sweep.py label    # one verdict per planned sample -> labels.jsonl
    py tools/label_laya_sweep.py score    # Laya's reviews against the verdicts -> score.json

mine takes each planned commit whose subject reads as a fix (fix, bug, crash,
regression, wrong, typo, ...), diffs it against its parent ignoring whitespace,
drops the deleted lines that are blank, punctuation only or a comment, and
blames the rest in the parent. The commits that wrote those lines are the
candidates for having introduced the defect: SZZ (Sliwerski, Zimmermann and
Zeller 2005) with the cosmetic-change filter of AG-SZZ (Kim et al. 2006). Lines
attributed to a shallow clone's boundary are dropped. One record per fix goes to
szz.jsonl, so label can apply another policy without blaming again. mine runs
at below-normal priority, so laya-serve keeps the CPU it needs.

label gives every (commit, file) of the plan, the unit the sweep reviews, one of
  REJECT   a counted fix blamed at least --min-lines of its lines on this commit.
           Counted are fixes of the kinds in --kinds (default defect, build and
           test; warning and docs fixes are not defects) that touch at most
           --max-fix-files files and were not reverted themselves;
  APPROVE  no counted fix blames it, and commits from at least --window-days
           later were built on it, so a defect had time to be found;
  none     too recent; a shallow clone's boundary (a whole tree shown as added);
           a revert, or a commit that was reverted: a revert says a change was
           taken back, not that it was wrong, so both are left out.
For each REJECT it also records where the first blamed line sits in the patch
the sweep showed Laya, so score can tell a defect Laya read from one past its
1024-token window.

score joins labels.jsonl with sessions.jsonl and reports, overall and for
subsets: the vote against the label, the AUC of p(REJECT) next to the AUC of the
bare patch size, the empirical P1 and P0 that WaRF's LLR constants assume, and
the reliability omega these verdicts would teach WaRF.

The labels are noisy both ways: a fix also rewrites lines that were fine, many
defects are fixed under a message that does not say so, and APPROVE only means
"no fix found". Everything goes to the sweep's data directory
(.warf-experiments/laya-sweep/), never to .warf/.
"""
import argparse
import collections
import json
import math
import os
import re
import subprocess
import sys
import time
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from run_laya_sweep import (CONTEXT_LINES, DEFAULT_HOME, DEFAULT_PROFILE, INPUT_LABEL, ROOT,
                            git, hold_lock, read_jsonl, repair_tail)

# A subject that reads as a fix. "fixed" before a noun of size or method is an adjective,
# and a regression test guards against a defect rather than repairing one.
FIX = re.compile(r"\b(fix(es|ed|ing|up)?|bugs?|bugfix(es)?|hotfix(es)?|defects?|faults?|faulty|"
                 r"crash(es|ed|ing)?|segfaults?|regressions?|broken|repair(s|ed)?|"
                 r"correct(s|ed|ion|ions)?|wrong|mistakes?|typos?|leaks?)\b", re.I)
NOT_FIX = re.compile(r"\bfixed[- ](size|point|density|number|order|length|width|step|seed|grid|"
                     r"degree|value)s?\b|\bregression[- ]test(s|ing)?\b", re.I)
BUG_WORDS = re.compile(r"\b(bugs?|bugfix(es)?|crash(es|ed|ing)?|segfaults?|leaks?|wrong|regressions?|"
                       r"defects?|faults?|faulty|incorrect(ly)?)\b", re.I)
KINDS = (   # the first that matches, unless the subject names a bug
    ("docs",    re.compile(r"\b(docs?|documentation|doxygen|comments?|readme|spelling|typos?)\b", re.I)),
    ("warning", re.compile(r"\bwarn(ing)?s?\b|-W[\w-]+|\bunused\b", re.I)),
    ("build",   re.compile(r"\b(compil\w*|build\w*|includes?|inclusion|link(er|ing)?|cmake|mingw|msvc|"
                           r"gcc|clang|windows|win32|macos|osx|linux|ci)\b", re.I)),
    ("test",    re.compile(r"\b(unit ?)?tests?\b", re.I)),
)
DEFAULT_KINDS = "defect,build,test"
REVERT_SUBJECT = re.compile(r"\s*revert\b", re.I)
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,64})", re.I)
QUOTED_REVERT = re.compile(r'Revert "(.+)"\s*$')
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
BLAME_HEADER = re.compile(r"([0-9a-f]{40,64}) (\d+) (\d+)")
WORD = re.compile(r"\w")


def fix_kind(subject: str) -> str | None:
    """defect, build, test, warning or docs for a subject that reads as a fix, else None."""
    s = NOT_FIX.sub(" ", subject)
    if not FIX.search(s):
        return None
    if BUG_WORDS.search(s):
        return "defect"
    for kind, pattern in KINDS:
        if pattern.search(s):
            return kind
    return "defect"


def lower_priority() -> None:
    """Below-normal priority for this process and for the git processes it starts,
    which inherit it: laya-serve keeps the CPU it needs for the sweep."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL_PRIORITY_CLASS
    else:
        os.nice(10)


def git_timed(git_dir: str, *args: str, cwd: str | None = None, timeout: float | None = None) -> str:
    """run_laya_sweep.git with a time limit, and a lone CR left inside its line, so
    that line numbers stay right in output that carries file content (blame, -U0 diffs)."""
    proc = subprocess.run(["git", "--git-dir", git_dir, "-c", "core.quotePath=false", *args],
                          capture_output=True, timeout=timeout, cwd=cwd if cwd and os.path.isdir(cwd) else None)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[:500] or f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def unquote(path: str) -> str:
    """A path as git prints it when it has to quote it (with core.quotePath=false
    only for control characters, quotes and backslashes)."""
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    raw, out, i = path[1:-1].encode("utf-8"), bytearray(), 0
    escapes = {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\", "a": b"\a", "b": b"\b",
               "f": b"\f", "r": b"\r", "v": b"\v"}
    while i < len(raw):
        if raw[i] == 0x5C and i + 1 < len(raw):
            nxt = chr(raw[i + 1])
            if nxt in "01234567":
                out.append(int(raw[i + 1:i + 4], 8) & 0xFF)
                i += 4
            else:
                out += escapes.get(nxt, nxt.encode())
                i += 2
        else:
            out.append(raw[i])
            i += 1
    return out.decode("utf-8", "replace")


def cosmetic(text: str, suffix: str) -> bool:
    """A deleted line no defect can live on: blank, punctuation only (a closing
    brace), or a comment."""
    s = text.strip()
    if not WORD.search(s):
        return True
    if suffix == ".py":
        return s.startswith("#")
    return s.startswith(("//", "/*", "*/")) or (s.startswith("*") and s[1:2] in ("", " ", "\t", "*"))


# ── mine ─────────────────────────────────────────────────────────────────────

def deleted_lines(diff: str) -> list[dict]:
    """Each file of a -U0 diff: its old and new path (None for /dev/null) and its
    deleted lines as (number in the old file, text)."""
    files: list[dict] = []
    cur: dict | None = None
    in_header = False
    old_no = rem_old = rem_new = 0
    for line in diff.split("\n"):
        if rem_old or rem_new:                  # inside a hunk: count it off, so a deleted
            if line.startswith("-") and rem_old:      # "-- x" is not taken for a header
                cur["deleted"].append((old_no, line[1:]))
                old_no += 1
                rem_old -= 1
            elif line.startswith("+") and rem_new:
                rem_new -= 1
            continue
        if line.startswith("diff --git "):
            cur = {"old": None, "new": None, "deleted": []}
            files.append(cur)
            in_header = True
        elif cur is None:
            continue
        elif in_header and line.startswith("--- "):
            p = unquote(line[4:])
            cur["old"] = None if p == "/dev/null" else p[2:] if p.startswith("a/") else p
        elif in_header and line.startswith("+++ "):
            p = unquote(line[4:])
            cur["new"] = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
        elif line.startswith("@@ "):
            in_header = False
            m = HUNK.match(line)
            if m:
                old_no = int(m.group(1))
                rem_old = int(m.group(2)) if m.group(2) is not None else 1
                rem_new = int(m.group(4)) if m.group(4) is not None else 1
    return files


def blame_lines(git_dir: str, cwd: str, rev: str, path: str, lines: list[int],
                timeout: float) -> list[tuple[str, str, int, bool]]:
    """(commit, its path for the file, line number there, at a shallow boundary?)
    for each of `lines` of `path` at `rev`, whitespace changes passed through."""
    ranges: list[list[int]] = []
    for n in sorted(set(lines)):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n])
    out = []
    for i in range(0, len(ranges), 300):        # keep the command line short
        args = ["blame", "--line-porcelain", "-w"]
        for a, b in ranges[i:i + 300]:
            args += ["-L", f"{a},{b}"]
        text = git_timed(git_dir, *args, rev, "--", path, cwd=cwd, timeout=timeout)
        sha = None
        for line in text.split("\n"):
            if sha is None:
                m = BLAME_HEADER.match(line)
                if m:
                    sha, orig, filename, boundary = m.group(1), int(m.group(2)), path, False
            elif line.startswith("\t"):         # the line itself closes its block
                out.append((sha, filename, orig, boundary))
                sha = None
            elif line == "boundary":
                boundary = True
            elif line.startswith("filename "):
                filename = unquote(line[9:])
    return out


def mine_fix(entry: dict, supported: set[str], timeout: float) -> dict:
    """Blame one fix commit's deleted lines in its parent."""
    sha, gd = entry["sha"], entry["git_dir"]
    cwd = entry["worktree"] or gd
    rec = {"fix": sha, "repo": entry["repo"], "subject": entry["subject"], "files": entry["files"]}
    t0 = time.time()
    try:
        diff = git_timed(gd, "show", "-M", "-w", "-U0", "--no-color", "--no-ext-diff",
                         "--src-prefix=a/", "--dst-prefix=b/", "--format=", sha, cwd=cwd, timeout=timeout)
        blamed: dict[tuple[str, str], list[int]] = {}
        considered = boundary = 0
        for f in deleted_lines(diff):
            # An added file has nothing to blame; deleting a whole file is a removal, not a repair.
            if f["old"] is None or f["new"] is None or Path(f["old"]).suffix not in supported:
                continue
            lines = [n for n, text in f["deleted"] if not cosmetic(text, Path(f["old"]).suffix)]
            considered += len(lines)
            if not lines:
                continue
            for commit, path, n, at_boundary in blame_lines(gd, cwd, sha + "^", f["old"], lines, timeout):
                if at_boundary:
                    boundary += 1
                else:
                    blamed.setdefault((commit, path), []).append(n)
        rec.update(lines=considered, boundary_lines=boundary,
                   blamed=[{"commit": c, "file": p, "lines": sorted(ns)} for (c, p), ns in blamed.items()])
    except Exception as exc:                    # one fix must not end the run; it is retried next time
        rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
    rec["seconds"] = round(time.time() - t0, 2)
    return rec


def cmd_mine(args: argparse.Namespace, home: Path) -> None:
    from warf.cli import SUPPORTED_EXTENSIONS

    lock = hold_lock(home / "szz.lock")
    if lock is None:
        sys.exit(f"another `mine` is using {home}")
    lower_priority()
    plan = read_jsonl(home / "plan.jsonl")
    if not plan:
        sys.exit(f"no plan in {home}; run run_laya_sweep.py discover and plan first")
    out_path = home / "szz.jsonl"
    repair_tail(out_path)
    done = {r["fix"] for r in read_jsonl(out_path) if "error" not in r}
    # A root commit has no parent to blame in, a shallow boundary none in this clone,
    # and a revert undoes rather than repairs.
    fixes = [e for e in plan if e["parents"] == 1 and not e["shallow_boundary"]
             and fix_kind(e["subject"]) and not REVERT_SUBJECT.match(e["subject"])
             and (not args.repo or args.repo.lower() in e["repo"].lower())]
    todo = [e for e in fixes if e["sha"] not in done and e["files"] <= args.max_files]
    too_big = sum(1 for e in fixes if e["sha"] not in done and e["files"] > args.max_files)
    if args.limit:
        todo = todo[:args.limit]
    print(f"\n  {len(fixes)} fix commits in the plan: {sum(e['sha'] in done for e in fixes)} blamed before, "
          f"{too_big} with more than {args.max_files} files left out, {len(todo)} to blame "
          f"({args.workers} workers)\n", flush=True)

    t0 = last = time.time()
    n = n_err = 0
    with out_path.open("a", encoding="utf-8") as out, ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(mine_fix, e, SUPPORTED_EXTENSIONS, args.timeout) for e in todo]
        for fut in as_completed(futures):
            rec = fut.result()
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if "error" in rec:
                n_err += 1
                print(f"  ERROR {rec['repo']} {rec['fix'][:10]}: {rec['error'][:200]}", flush=True)
            if time.time() - last > args.status_every or n == len(todo):
                rate = n / (time.time() - t0)
                print(f"  [{time.strftime('%H:%M:%S')}] {n}/{len(todo)} fixes blamed ({n_err} errors), "
                      f"ETA {(len(todo) - n) / rate / 60:.0f} min", flush=True)
                last = time.time()
    print(f"\n  -> {out_path}")


# ── label ────────────────────────────────────────────────────────────────────

def history(repos: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Over every object store: each commit's committer time, the time of the latest
    commit built on it (in any clone), and the reverts, as revert -> reverted
    commits and reverted commit -> its revert."""
    ctime: dict[str, int] = {}
    latest: dict[str, int] = {}
    revert_of: dict[str, list[str]] = {}
    reverted_by: dict[str, str] = {}
    for repo in repos:
        out = git_timed(repo["git_dir"], "log", "--exclude=refs/stash", "--all", "--topo-order",
                        "--format=%x00%H%x01%P%x01%ct%x01%B")
        acc: dict[str, int] = {}                # latest time below each commit seen so far
        subjects: dict[str, list[str]] = {}
        reverts: list[tuple[str, list[str], str | None]] = []
        for block in out.split("\x00")[1:]:
            sha, parents, ct, body = (block.split("\x01", 3) + ["", "", ""])[:4]
            t = int(ct or 0)
            ctime[sha] = t
            # --topo-order lists every child before its parents, so `acc` is complete here.
            last = max(t, acc.pop(sha, t))
            latest[sha] = max(latest.get(sha, last), last)
            for p in parents.split():
                acc[p] = max(acc.get(p, last), last)
            subject = body.split("\n", 1)[0].strip()
            subjects.setdefault(subject, []).append(sha)
            targets = REVERTS.findall(body)
            if targets or REVERT_SUBJECT.match(subject):
                quoted = QUOTED_REVERT.match(subject)
                reverts.append((sha, targets, quoted.group(1) if quoted and not targets else None))
        shas = sorted(ctime)

        def resolve(prefix: str) -> str | None:
            i = bisect_left(shas, prefix.lower())
            hits = []
            while i < len(shas) and shas[i].startswith(prefix.lower()) and len(hits) < 2:
                hits.append(shas[i])
                i += 1
            return hits[0] if len(hits) == 1 else None

        for sha, targets, quoted in reverts:
            found = [r for r in map(resolve, targets) if r]
            if quoted:                          # `Revert "subject"` without the trailer
                same = [c for c in subjects.get(quoted, []) if ctime[c] <= ctime[sha] and c != sha]
                found += same if len(same) == 1 else []
            revert_of.setdefault(sha, [])
            for r in found:
                if r not in revert_of[sha]:
                    revert_of[sha].append(r)
                reverted_by.setdefault(r, sha)
    return ctime, latest, revert_of, reverted_by


def first_offset(patch: str, wanted: set[int]) -> int | None:
    """Characters into `patch` where the first line with a new-side number in `wanted` begins."""
    pos, new_no = 0, None
    for line in patch.split("\n"):
        if line.startswith("@@"):
            m = HUNK.match(line)
            new_no = int(m.group(3)) if m else None
        elif new_no is not None and line[:1] in ("+", " "):
            if new_no in wanted:
                return pos
            new_no += 1
        pos += len(line) + 1
    return None


def defect_offsets(entry: dict, wanted: dict[str, set[int]]) -> dict[str, int | None]:
    """For one commit, where the first blamed line of each file sits in the patch the
    sweep showed Laya: the same `git show` and diff split as run_laya_sweep.py."""
    from warf.cli import _parse_diff
    cwd = entry["worktree"] or entry["git_dir"]
    diff = git(entry["git_dir"], "show", f"-U{CONTEXT_LINES}", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", "--format=", entry["sha"], cwd=cwd)
    out: dict[str, int | None] = {}
    for path, patch in _parse_diff(diff):
        if path in wanted and path not in out:
            out[path] = first_offset(patch, wanted[path])
    return out


def quantiles(values: list[float], qs=(0.25, 0.5, 0.75, 0.9)) -> list[float]:
    v = sorted(values)
    return [v[min(len(v) - 1, int(q * len(v)))] for q in qs] if v else []


def cmd_label(args: argparse.Namespace, home: Path) -> None:
    from warf.cli import SUPPORTED_EXTENSIONS

    lower_priority()
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    plan = read_jsonl(home / "plan.jsonl")
    repos = json.loads((home / "repos.json").read_text(encoding="utf-8"))
    by_fix: dict[str, dict] = {}
    for r in read_jsonl(home / "szz.jsonl"):     # a fix blamed again replaces its earlier record
        by_fix[r["fix"]] = r
    if not by_fix:
        sys.exit(f"no szz.jsonl in {home}; run `mine` first")

    print("  reading the history of every repository ...", flush=True)
    ctime, latest, revert_of, reverted_by = history(repos)

    # The verdicts each fix gives, under the policy.
    evidence: dict[tuple[str, str], list[tuple[str, str, list[int]]]] = collections.defaultdict(list)
    fixes_used: collections.Counter = collections.Counter()
    for r in by_fix.values():
        kind = fix_kind(r["subject"])
        why = ("blame failed" if "error" in r else "not a fix" if kind is None
               else f"{kind} fix" if kind not in kinds
               else f"more than {args.max_fix_files} files" if r["files"] > args.max_fix_files
               else "fix was reverted" if r["fix"] in reverted_by
               else "is a revert" if r["fix"] in revert_of else None)
        fixes_used["left out: " + why if why else "counted"] += 1
        if why:
            continue
        for b in r["blamed"]:
            evidence[(b["commit"], b["file"])].append((r["fix"], kind, b["lines"]))

    # The samples: every supported file of every planned commit, listed as plan listed them.
    entries = {e["sha"]: e for e in plan}
    owned: dict[str, set[str]] = collections.defaultdict(set)
    for e in plan:
        owned[e["git_dir"]].add(e["sha"])
    files_of: dict[str, list[str]] = {}
    for gd, shas in owned.items():
        out = git_timed(gd, "log", "--exclude=refs/stash", "--all", "--name-only", "--format=%x00%H")
        for block in out.split("\x00")[1:]:
            sha, _, names = block.partition("\n")
            if sha in shas and sha not in files_of:
                files_of[sha] = list(dict.fromkeys(
                    f for f in names.split("\n") if f.strip() and Path(f).suffix in SUPPORTED_EXTENSIONS))
    off = sum(1 for e in plan if len(files_of.get(e["sha"], ())) != e["files"])
    if off:
        print(f"  note: {off} commits list another number of files than the plan did", flush=True)

    labels: list[dict] = []
    for sha, files in files_of.items():
        e = entries[sha]
        later = (latest.get(sha, 0) - ctime.get(sha, 0)) / 86400
        for path in files:
            ev = evidence.get((sha, path), [])
            lines = sorted({n for _, _, ns in ev for n in ns})
            if sha in reverted_by:
                label, reason = None, "reverted"
            elif sha in revert_of:
                label, reason = None, "revert"
            elif e["shallow_boundary"]:
                label, reason = None, "shallow boundary"
            elif ev and len(lines) >= args.min_lines:
                label, reason = "REJECT", "fixed later"
            elif ev:
                label, reason = None, f"fewer than {args.min_lines} blamed lines"
            elif later < args.window_days:
                label, reason = None, f"less than {args.window_days} days of later history"
            else:
                label, reason = "APPROVE", "no fix found"
            fixes = sorted(({"fix": f, "kind": k, "lines": len(ns),
                             "days": round((ctime.get(f, 0) - ctime.get(sha, 0)) / 86400, 1)}
                            for f, k, ns in ev), key=lambda x: x["days"])
            labels.append({"commit": sha, "file": path, "repo": e["repo"], "phase": e["phase"],
                           "label": label, "reason": reason, "later_days": round(later, 1),
                           "blamed_lines": len(lines), "first_line": lines[0] if lines else None,
                           "lines": lines[:200], "fixes": fixes, "defect_at": None})

    # Where each REJECT's first blamed line is in the patch Laya was shown.
    wanted: dict[str, dict[str, set[int]]] = collections.defaultdict(dict)
    for lab in labels:
        if lab["label"] == "REJECT":
            wanted[lab["commit"]][lab["file"]] = set(lab["lines"])
    print(f"  locating the blamed lines of {sum(map(len, wanted.values()))} REJECTs "
          f"in {len(wanted)} patches ...", flush=True)
    offsets: dict[tuple[str, str], int | None] = {}
    with ThreadPoolExecutor(4) as pool:
        futures = {pool.submit(defect_offsets, entries[sha], w): sha for sha, w in wanted.items()}
        for fut in as_completed(futures):
            try:
                for path, at in fut.result().items():
                    offsets[(futures[fut], path)] = at
            except Exception as exc:
                print(f"  could not locate {futures[fut][:10]}: {exc}", flush=True)
    for lab in labels:
        lab["defect_at"] = offsets.get((lab["commit"], lab["file"]))

    with (home / "labels.jsonl").open("w", encoding="utf-8") as f:
        for lab in labels:
            f.write(json.dumps(lab, ensure_ascii=False) + "\n")
    policy = {"kinds": sorted(kinds), "max_fix_files": args.max_fix_files,
              "min_lines": args.min_lines, "window_days": args.window_days}
    (home / "labels-policy.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")

    print(f"\n  fixes: " + ", ".join(f"{n} {k}" for k, n in fixes_used.most_common()))
    print(f"  reverts: {len(revert_of)} revert commits, {len(reverted_by)} reverted commits")
    by = collections.Counter((lab["label"] or "none", lab["reason"]) for lab in labels)
    print(f"\n  {len(labels)} samples:")
    for (label, reason), n in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>8}  {label:<8} {reason}")
    print(f"\n  {'phase':<6} {'REJECT':>7} {'APPROVE':>8} {'none':>7}")
    for phase in "ABC":
        c = collections.Counter(lab["label"] for lab in labels if lab["phase"] == phase)
        print(f"  {phase:<6} {c['REJECT']:>7} {c['APPROVE']:>8} {c[None]:>7}")
    days = [lab["fixes"][0]["days"] for lab in labels if lab["label"] == "REJECT"]
    if days:
        q = quantiles(days)
        within = sum(d <= args.window_days for d in days) / len(days)
        print(f"\n  days from a REJECT to its first fix: quartiles {q[0]:.0f} / {q[1]:.0f} / {q[2]:.0f}, "
              f"90 % {q[3]:.0f}; {100 * within:.0f} % within the {args.window_days}-day window")
    located = [lab for lab in labels if lab["label"] == "REJECT"]
    print(f"  REJECTs with the blamed line found in the patch: "
          f"{sum(lab['defect_at'] is not None for lab in located)}/{len(located)}")
    print(f"\n  -> {home / 'labels.jsonl'}")


# ── score ────────────────────────────────────────────────────────────────────

def auc(scores: list[float], positive: list[bool]) -> tuple[float | None, float | None]:
    """P(a REJECT-labelled sample scores above an APPROVE-labelled one), ties half,
    with the Hanley-McNeil standard error."""
    import numpy as np
    s, y = np.asarray(scores, dtype=float), np.asarray(positive, dtype=bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if not n1 or not n0:
        return None, None
    _, inverse, counts = np.unique(s, return_inverse=True, return_counts=True)
    ranks = ((np.cumsum(counts) - counts) + (counts + 1) / 2.0)[inverse]
    a = float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt(max(0.0, (a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0)))
    return a, se


def auc_within_size(rows: list[dict], bins: int = 5) -> float | None:
    """The AUC of p(REJECT) over pairs of samples of about the same patch size (the
    same size quintile): what Laya adds beyond telling a big change from a small one."""
    ordered = sorted(rows, key=lambda r: r["size"])
    num = den = 0.0
    for i in range(bins):
        chunk = ordered[i * len(ordered) // bins:(i + 1) * len(ordered) // bins]
        a, _ = auc([r["p"] for r in chunk], [r["y"] for r in chunk])
        if a is not None:
            pairs = sum(r["y"] for r in chunk) * sum(not r["y"] for r in chunk)
            num += a * pairs
            den += pairs
    return num / den if den else None


def metrics(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["y"]]
    neg = [r for r in rows if not r["y"]]
    tp = sum(r["vote"] for r in pos)
    fp = sum(r["vote"] for r in neg)
    a, se = auc([r["p"] for r in rows], [r["y"] for r in rows])
    a_size, se_size = auc([r["size"] for r in rows], [r["y"] for r in rows])
    a_within = auc_within_size(rows)
    # WaRF's P1 = P(APPROVE | good code), P0 = P(APPROVE | bad code), smoothed by a half.
    p1 = (len(neg) - fp + 0.5) / (len(neg) + 1)
    p0 = (len(pos) - tp + 0.5) / (len(pos) + 1)
    mean = lambda rs: sum(r["p"] for r in rs) / len(rs) if rs else None
    return {"n": len(rows), "reject_labels": len(pos), "approve_labels": len(neg),
            "laya_reject_on_reject": tp, "laya_reject_on_approve": fp,
            "tpr": tp / len(pos) if pos else None, "fpr": fp / len(neg) if neg else None,
            "accuracy": (tp + len(neg) - fp) / len(rows) if rows else None,
            "mean_p_reject_on_reject": mean(pos), "mean_p_reject_on_approve": mean(neg),
            "auc": a, "auc_se": se, "auc_patch_size": a_size, "auc_patch_size_se": se_size,
            "auc_within_size_quintiles": a_within,
            "P1": p1, "P0": p0, "llr_approve": math.log(p1 / p0), "llr_reject": math.log((1 - p1) / (1 - p0))}


def cmd_score(args: argparse.Namespace, home: Path) -> None:
    labels = {(lab["commit"], lab["file"]): lab for lab in read_jsonl(home / "labels.jsonl")}
    if not labels:
        sys.exit(f"no labels.jsonl in {home}; run `label` first")
    sessions = [s for s in read_jsonl(home / "sessions.jsonl") if s.get("profile") == args.profile and "sweep" in s]
    rows: list[dict] = []
    unlabelled: collections.Counter = collections.Counter()
    for s in sessions:
        sw = s["sweep"]
        lab = labels.get((sw["commit"], sw["file"]))
        if lab is None or lab["label"] is None:
            unlabelled[lab["reason"] if lab else "not in labels.jsonl"] += 1
            continue
        usage = sw["laya"].get("usage") or {}
        total, dropped = usage.get("state_tokens") or 0, usage.get("state_tokens_dropped") or 0
        chars_read = sw["state_chars"] * ((total - dropped) / total if total else 1.0)
        frame = (sw["state_chars"] - sw["enriched_chars"] if not sw["cut"]
                 else len(f"Domain: {s['domain']}\n\n{INPUT_LABEL}:\n```\n"))
        rows.append({"y": lab["label"] == "REJECT", "p": sw["laya"]["probabilities"]["REJECT"],
                     "vote": s["decision"] == "REJECT", "size": sw["patch_chars"], "phase": sw["phase"],
                     "repo": sw["repo"], "domain": s["domain"], "full": not dropped, "later": lab["later_days"],
                     "seen": lab["defect_at"] is not None and frame + lab["defect_at"] < chars_read})
    print(f"\n  {len(sessions)} reviews; {len(rows)} with a verdict from the history, unlabelled: "
          + ", ".join(f"{n} {k}" for k, n in unlabelled.most_common()))
    if not rows:
        return

    policy_path = home / "labels-policy.json"
    window = json.loads(policy_path.read_text(encoding="utf-8"))["window_days"] if policy_path.exists() else 180
    a_rows = [r for r in rows if r["phase"] == "A"]
    subsets = [
        ("all with a verdict", rows),
        ("phase A (<= 50 files)", a_rows),
        # An APPROVE needs the window of later history and a REJECT does not; held to the
        # same window, both classes come from the same years of the history.
        (f"phase A, REJECTs too with {window} days later", [r for r in a_rows if r["later"] >= window]),
        ("phase A, state read in full", [r for r in a_rows if r["full"]]),
        ("phase A, REJECTs whose blamed line Laya read", [r for r in a_rows if not r["y"] or r["seen"]]),
        ("phase A, REJECTs whose blamed line it did not", [r for r in a_rows if not r["y"] or not r["seen"]]),
        ("phase B (> 50 files)", [r for r in rows if r["phase"] == "B"]),
    ]
    for repo in sorted({r["repo"] for r in a_rows}):
        rs = [r for r in a_rows if r["repo"] == repo]
        if len(rs) >= 50 and 0 < sum(r["y"] for r in rs) < len(rs):
            subsets.append((f"phase A, {repo}", rs))

    fmt = lambda x, d=3: "-" if x is None else f"{x:.{d}f}"
    print(f"\n  {'':<48} {'n':>6} {'REJ':>6} {'Laya REJECT on':>15} {'mean p(REJECT) on':>18} "
          f"{'AUC p(REJECT)':>14} {'AUC size':>9} {'AUC p, same size':>17}")
    print(f"  {'':<48} {'':>6} {'label':>6} {'REJ':>7} {'APP':>7} {'REJ':>9} {'APP':>8}")
    report = {}
    for name, rs in subsets:
        if not rs:
            continue
        m = metrics(rs)
        report[name] = m
        print(f"  {name[:48]:<48} {m['n']:>6} {m['reject_labels']:>6} {fmt(m['tpr']):>7} {fmt(m['fpr']):>7} "
              f"{fmt(m['mean_p_reject_on_reject']):>9} {fmt(m['mean_p_reject_on_approve']):>8} "
              f"{fmt(m['auc']):>7} ±{fmt(m['auc_se']):<5} {fmt(m['auc_patch_size']):>8} "
              f"{fmt(m['auc_within_size_quintiles']):>17}")

    m = report["phase A (<= 50 files)"] if a_rows else report["all with a verdict"]
    print(f"\n  As WaRF's SPRT sees it (phase A): P1 = P(APPROVE | good) {m['P1']:.3f}, "
          f"P0 = P(APPROVE | bad) {m['P0']:.3f};")
    print(f"  one APPROVE is worth LLR {m['llr_approve']:+.3f} and one REJECT {m['llr_reject']:+.3f} "
          f"(WaRF assumes +0.981 and -1.253)")
    print(f"\n  omega WaRF would learn from these verdicts, by domain (gamma 1: (1 + correct) / (2 + n)):")
    report["omega"] = {}
    for domain in sorted({r["domain"] for r in rows}):
        rs = [r for r in rows if r["domain"] == domain]
        correct = sum(r["vote"] == r["y"] for r in rs)
        omega = (1 + correct) / (2 + len(rs))
        always = (1 + sum(not r["y"] for r in rs)) / (2 + len(rs))
        report["omega"][domain] = {"n": len(rs), "correct": correct, "omega": omega, "always_approve": always}
        print(f"  {domain:<12} n {len(rs):>6}  correct {correct:>6}  omega {omega:.3f}  "
              f"(an agent that always approves: {always:.3f})")
    report["unlabelled"] = dict(unlabelled)
    (home / "score.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  -> {home / 'score.json'}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Label the Laya sweep's samples from git history (SZZ) and score Laya.")
    ap.add_argument("--home", default=str(DEFAULT_HOME), metavar="DIR",
                    help="the sweep's data directory (default: .warf-experiments/laya-sweep)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="the sweep profile to score")
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("mine", help="blame every fix commit of the plan, append to szz.jsonl; resumes")
    m.add_argument("--workers", type=int, default=3, help="parallel git processes (default: 3)")
    m.add_argument("--timeout", type=float, default=600, metavar="S", help="limit for one git call (default: 600)")
    m.add_argument("--max-files", type=int, default=50, metavar="N",
                   help="leave out fixes touching more supported files than this (default: 50)")
    m.add_argument("--repo", default=None, metavar="TEXT", help="only fixes of repositories whose name contains TEXT")
    m.add_argument("--limit", type=int, default=0, metavar="N", help="stop after N fixes")
    m.add_argument("--status-every", type=float, default=60.0, metavar="S", help="seconds between progress lines")

    l = sub.add_parser("label", help="one verdict per planned sample, write labels.jsonl")
    l.add_argument("--kinds", default=DEFAULT_KINDS,
                   help=f"fix kinds that count: defect, build, test, warning, docs (default: {DEFAULT_KINDS})")
    l.add_argument("--max-fix-files", type=int, default=20, metavar="N",
                   help="fixes touching more supported files do not count (default: 20)")
    l.add_argument("--min-lines", type=int, default=1, metavar="N",
                   help="blamed lines a REJECT needs (default: 1)")
    l.add_argument("--window-days", type=int, default=180, metavar="D",
                   help="later history an APPROVE needs (default: 180)")

    sub.add_parser("score", help="Laya's reviews against labels.jsonl, write score.json")
    args = ap.parse_args()

    home = Path(args.home).resolve()
    if home == (ROOT / ".warf").resolve():
        sys.exit("refusing to write into the corpus directory .warf/")
    if not (home / "plan.jsonl").exists():
        sys.exit(f"no sweep in {home}")
    os.environ["WARF_HOME"] = str(home)          # before warf is imported: its paths come from here
    {"mine": cmd_mine, "label": cmd_label, "score": cmd_score}[args.command](args, home)


if __name__ == "__main__":
    main()
