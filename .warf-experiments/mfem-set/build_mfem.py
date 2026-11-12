"""Mine the MFEM candidates and clean controls (README.md), with git only and no model calls.

  candidates.jsonl   defective candidates: B-SZZ from fixes on origin/master. A fix is a non-merge commit
                     whose subject names a bug (the confirm set's BUG expression), not a revert, touching at
                     most 5 files. Its deleted non-cosmetic lines in C++ files (git diff -w; not blank,
                     punctuation only or a comment) are blamed (-w) in the fix's parent. A blamed (commit,
                     file) qualifies if the fix came 0..180 days later, the commit is a non-merge, non-revert
                     commit made before CUTOFF, and its input is at most MAX_CHARS. One file per commit; fixes
                     are visited in a seeded random order until N_DEFECT candidates exist. The fix's diff on
                     the file is kept for the judges only.
  clean_pool.jsonl   clean controls: non-merge, non-revert commits on origin/master, 2014-01-01..CUTOFF, one
                     C++ file each whose every added non-blank line is still blamed on the commit at
                     origin/master; no candidate's commit and no fix's commit.

    python .warf-experiments/mfem-set/build_mfem.py      # writes candidates.jsonl, clean_pool.jsonl, build.log"""
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import git, prepare  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402

MFEM = Path(r"C:\workdir\warf\repos\mfem")
GD, REF = str(MFEM / ".git"), "origin/master"
BASE = {"git_dir": GD, "worktree": str(MFEM)}
CUTOFF, MAX_CHARS, N_DEFECT, N_CLEAN = "2025-11-12", 20000, 600, 500
CPP = (".h", ".hpp", ".cpp", ".cc", ".cxx")
BUG = re.compile(r"\b(bugs?|bugfix(es)?|crash(es|ed|ing)?|segfaults?|leaks?|wrong|regressions?|defects?|"
                 r"faults?|faulty|incorrect(ly)?)\b|^fix", re.I)
log = []


def say(s=""):
    log.append(s); print(s, flush=True)


def cosmetic(line):
    s = line.strip()
    return (not s or re.fullmatch(r"[{}()\[\];,.:]*", s) is not None or s.startswith(("//", "/*", "*")))


def is_merge(sha):
    return len(git(GD, "rev-list", "--parents", "-n", "1", sha).split()) > 2


def day(s):
    return date.fromisoformat(s).toordinal()


def info(sha):
    d, s = git(GD, "show", "-s", "--format=%ad%x09%s", "--date=short", sha).strip().split("\t", 1)
    return d, s


def blamed(fix, path):
    """{commit: [old line numbers]} for the fix's deleted non-cosmetic lines of path, blamed in fix^."""
    diff = git(GD, "diff", "-w", "-U0", "--no-color", f"{fix}^", fix, "--", path)
    out, old = {}, None
    for ln in diff.splitlines():
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+", ln)
        if m:
            old = int(m.group(1)); continue
        if old is None or ln.startswith(("---", "+++")):
            continue
        if ln.startswith("-"):
            if not cosmetic(ln[1:]):
                row = git(GD, "blame", "-l", "-s", "-w", "-L", f"{old},{old}", f"{fix}^", "--", path).split(" ", 1)[0]
                sha = row.lstrip("^")
                if not row.startswith("^"):          # a boundary commit is not an introducer
                    out.setdefault(sha, []).append(old)
            old += 1
    return out


def defects():
    fixes = [r.split("\t", 2) for r in git(GD, "log", REF, "--no-merges", "--format=%H%x09%ad%x09%s",
                                           "--date=short").splitlines()]
    fixes = [(h, d, s) for h, d, s in fixes if BUG.search(s) and not s.startswith("Revert")]
    reverted = set(re.findall(r"This reverts commit ([0-9a-f]{40})", git(GD, "log", REF, "--format=%B")))
    rng = random.Random(20261112)
    rng.shuffle(fixes)
    say(f"{len(fixes)} fix commits on {REF}")
    out, seen, visited = [], set(), 0
    for fix, fdate, fsubj in fixes:
        if len(out) >= N_DEFECT:
            break
        visited += 1
        files = git(GD, "show", "--format=", "--name-only", fix).split()
        if len(files) > 5 or fix in reverted:
            continue
        for path in [f for f in files if f.endswith(CPP)]:
            try:
                hits = blamed(fix, path)
            except RuntimeError:
                continue                              # added by the fix, or renamed
            for sha, lines in sorted(hits.items(), key=lambda kv: -len(kv[1])):
                if sha in seen or sha in reverted:
                    continue
                cdate, csubj = info(sha)
                days = day(fdate) - day(cdate)
                if not 0 <= days <= 180 or cdate >= CUTOFF or csubj.startswith(("Revert", "Merge")) or is_merge(sha):
                    continue
                try:
                    code, domain, context, enrich_error = prepare({**BASE, "sha": sha}, path)
                except Exception:
                    continue                          # the file is not in that commit's diff (renamed since)
                if len(code) > MAX_CHARS:
                    continue
                seen.add(sha)
                out.append({"base": f"{sha[:7]}:{Path(path).name}", "commit": sha, "date": cdate, "subject": csubj,
                            "file": path, "domain": domain, "context": context, "enrich_error": enrich_error,
                            "blamed_lines": lines, "fix": fix, "fix_days": days, "fix_subject": fsubj,
                            "fix_diff": git(GD, "show", "-U5", "--format=%H%n%ad%n%s%n%n%b", "--date=short",
                                            fix, "--", path),
                            "code": code})
                if len(out) % 50 == 0:
                    say(f"  {len(out)} candidates after {visited} fixes")
                break                                 # one candidate per fix file is enough
    say(f"defective candidates {len(out)} from {visited} fixes visited")
    return out, {h for h, _, _ in fixes}


def survives(sha, path, code):
    added = [ln[1:] for ln in code.split("\n# Full function context", 1)[0].splitlines()
             if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]
    try:
        blame = git(GD, "blame", "-l", "-s", REF, "--", path)
    except RuntimeError:
        return False
    remaining = [row.split(") ", 1)[1] for row in blame.splitlines() if row.startswith(sha) and ") " in row]
    for line in added:
        if line in remaining:
            remaining.remove(line)
        else:
            return False
    return True


def clean(exclude):
    commits = git(GD, "log", REF, "--no-merges", "--since=2014-01-01", f"--until={CUTOFF}",
                  "--format=%H%x09%ad%x09%s", "--date=short", "--", *[f"*{e}" for e in CPP]).splitlines()
    rng = random.Random(20261113)
    rng.shuffle(commits)
    out = []
    for row in commits:
        if len(out) >= N_CLEAN:
            break
        sha, cdate, subj = row.split("\t", 2)
        if sha in exclude or subj.startswith(("Revert", "Merge")):
            continue
        files = [f for f in git(GD, "show", "--format=", "--name-only", "--diff-filter=AM", sha).split() if f.endswith(CPP)]
        rng.shuffle(files)
        for f in files:
            try:
                code, domain, context, enrich_error = prepare({**BASE, "sha": sha}, f)
            except Exception:
                continue
            if len(code) > MAX_CHARS or not any(ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()
                                                for ln in code.splitlines()):
                continue
            if survives(sha, f, code):
                out.append({"base": f"{sha[:7]}:{Path(f).name}", "commit": sha, "date": cdate, "subject": subj,
                            "file": f, "domain": domain, "context": context, "enrich_error": enrich_error, "code": code})
                if len(out) % 100 == 0:
                    say(f"  {len(out)} clean controls")
                break
    say(f"clean pool {len(out)}")
    return out


def main():
    d, fix_shas = defects()
    c = clean({x["commit"] for x in d} | fix_shas)
    for name, rows in (("candidates.jsonl", d), ("clean_pool.jsonl", c)):
        with (HERE / name).open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (HERE / "build.log").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
