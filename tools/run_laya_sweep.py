"""
Laya over every git commit on this machine: the single-agent decision profile of
the validation-suite runs (tools/run_laya_suite.py), applied to every source file
that `warf review-commit` would review, in every commit of every repository
found, with no ground truth. The result is a large set of real-code samples of
Laya's vote and probabilities.

    py tools/run_laya_sweep.py discover --from-list gitdirs.txt heads.txt   # or: --roots C:\\ D:\\
    py tools/run_laya_sweep.py plan
    py tools/run_laya_sweep.py run            # stop with Ctrl+C or by creating <home>/STOP
    py tools/run_laya_sweep.py status

discover finds every repository (worktrees, submodules, linked worktrees, bare
repositories) and keeps one entry per object store, so a clone reached through a
junction or a second worktree counts once. plan lists every non-merge commit
reachable from any ref except refs/stash, each hash once across all clones, in
review order: repositories with fewer commits first, newest commit first, and
commits touching more than --big supported files (initial imports, shallow-clone
boundaries) after all the others. run reviews the plan; it resumes where it
stopped, file by file, and refuses to start while another run holds the data
directory (run.lock). Each run appends laya-serve's /health answer, with the
checkpoint revisions, to runs.jsonl.

Each file is reviewed the way review-commit reviews it: `git show -U30`, the same
diff split and extension filter, enrich_patch, detect_domain, run_review with the
"Patch under review (unified diff)" label, and a session record from session_dict
with the artifact "<commit>:<path>". The differences keep a long unattended run
going:
  * the state is cut to laya-serve's 50 000-character limit, where review-commit
    gets HTTP 413. Laya reads only the head of the state (1024 tokens on the
    multilingual checkpoint), so its answer does not change;
  * git output is decoded with replacement characters rather than strictly as
    UTF-8, and paths are not quoted (core.quotePath=false), so non-ASCII names
    still parse;
  * when enrich_patch raises, the plain patch is reviewed, as its docstring
    promises for a parse error, and the record names the error (`enrich_error`).
    It does raise: it numbers a "\\ No newline at end of file" marker as a line,
    runs past the end of the file and fails with IndexError, which crashes
    review-commit on such a commit;
  * every record carries a `sweep` block: repository, commit metadata, the cut,
    Laya's own truncation report and its probabilities at full precision.
Merge commits are skipped. review-commit skips them too, because its diff split
does not read the combined diff that `git show` prints for a merge.

Needs a laya-serve on http://127.0.0.1:8000 (or LAYA_BASE_URL). Data goes to
.warf-experiments/laya-sweep/ by default (--home overrides), never to the corpus
in .warf/. One review takes about 2.2 s on a 4-core CPU.
"""
import argparse
import collections
import contextlib
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_HOME = ROOT / ".warf-experiments" / "laya-sweep"
DEFAULT_PROFILE = "laya_sweep"
# The README question, as in the laya_q1 suite profile, so the two runs compare.
DEFAULT_PERSONA = "Should this change be merged as it is? A defect you can point to is a REJECT."
CONTEXT_LINES = 30                                  # review-commit's --context default
INPUT_LABEL = "Patch under review (unified diff)"   # the label review-commit passes
MAX_STATE_CHARS = 50_000                            # laya-serve: longer states get HTTP 413
SECONDS_PER_REVIEW = 2.25                           # measured, multilingual, 1024 tokens, CPU
SERVER_WAIT = 30 * 60                               # how long to wait for a laya-serve that went away


# ── shared helpers ───────────────────────────────────────────────────────────

def git(git_dir: str, *args: str, cwd: str | None = None) -> str:
    """Run git against one object store. Output is decoded leniently and its
    newlines normalised as text mode would, which is what WaRF's own git calls see.

    With --git-dir, git reads .gitattributes relative to the process's working
    directory, so a diff must run from the reviewed worktree (`cwd`) for that
    repository's diff attributes to apply, as they do under review-commit."""
    proc = subprocess.run(["git", "--git-dir", git_dir, "-c", "core.quotePath=false", *args],
                          capture_output=True, cwd=cwd if cwd and os.path.isdir(cwd) else None)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def read_jsonl(path: Path) -> list[dict]:
    """Records of a JSONL file; a line that does not parse (a write cut short) is skipped."""
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def repair_tail(path: Path) -> None:
    """Drop a last line left without its newline by a killed process, so the next
    append does not glue a fresh record onto the broken one."""
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("rb+") as f:
        end = f.seek(0, os.SEEK_END)
        f.seek(end - 1)
        if f.read(1) == b"\n":
            return
        cut, pos = 0, end
        while pos > 0:                           # back to the last complete line
            step = min(1 << 16, pos)
            pos -= step
            f.seek(pos)
            i = f.read(step).rfind(b"\n")
            if i >= 0:
                cut = pos + i + 1
                break
        f.truncate(cut)
    print(f"  repaired {path.name}: dropped {end - cut} bytes of an unfinished record")


def label_for(path: str) -> str:
    """A readable, unambiguous repository name: its path, home shortened to ~."""
    p = Path(path).as_posix()
    home = Path.home().as_posix()
    return "~" + p[len(home):] if p.lower().startswith(home.lower()) else p


def server_url() -> str:
    return (os.environ.get("LAYA_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def server_health() -> dict | None:
    """laya-serve's /health answer (loaded checkpoints and their revisions), or None."""
    try:
        with urllib.request.urlopen(server_url() + "/health", timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body if body.get("status") == "ok" else None
    except Exception:
        return None


def hold_lock(path: Path):
    """An exclusive lock on `path` for the life of the process (keep the returned
    file open), or None when another process holds it."""
    f = path.open("a+")
    f.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


# ── discover ─────────────────────────────────────────────────────────────────

def scan(root: str, name: str) -> list[str]:
    """Every file or directory called `name` under root, hidden ones included.
    cmd's dir /s is far quicker than a Python walk on NTFS; /u makes it write UTF-16."""
    proc = subprocess.run(["cmd", "/u", "/c", "dir", "/s", "/b", "/a", os.path.join(root, name)],
                          capture_output=True)
    return [l for l in proc.stdout.decode("utf-16-le", "replace").splitlines() if l.strip()]


def read_list(path: str) -> list[str]:
    raw = Path(path).read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    return [l.strip() for l in text.splitlines() if l.strip()]


def git_line(*args: str) -> str | None:
    """One-line git answer, or None when git fails (not a repository, no commits)."""
    proc = subprocess.run(["git", *args], capture_output=True)
    return proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else None


def cmd_discover(args: argparse.Namespace, home: Path) -> None:
    entries: list[str] = []
    for lst in args.from_list or []:
        entries += read_list(lst)
    if not args.from_list:
        for root in args.roots:
            print(f"  scanning {root} ...", flush=True)
            entries += scan(root, ".git") + scan(root, "HEAD")

    repos: dict[str, dict] = {}
    skipped = 0
    for entry in entries:
        p = Path(entry)
        if p.name == ".git":                       # worktree, submodule or linked worktree
            seen_at = str(p.parent)
            common = git_line("-C", seen_at, "rev-parse", "--path-format=absolute", "--git-common-dir")
            top = git_line("-C", seen_at, "rev-parse", "--show-toplevel")
        elif p.name == "HEAD" and (p.parent / "objects").is_dir() and (p.parent / "refs").is_dir():
            seen_at = str(p.parent)                 # a git directory itself: bare, .git or modules/x
            common = git_line("--git-dir", seen_at, "rev-parse", "--path-format=absolute", "--git-common-dir")
            top = None
        else:
            continue
        if not common:
            # Said out loud: a worktree git refuses (safe.directory, "dubious ownership")
            # would otherwise come back through its HEAD file without a worktree, and its
            # samples would lose enrich_patch's function context without a trace.
            why = subprocess.run(["git", "-C", seen_at, "rev-parse", "--git-dir"], capture_output=True)
            reason = why.stderr.decode("utf-8", "replace").strip().splitlines()
            print(f"  skipped {entry}: {reason[0] if reason else 'not a git repository'}")
            skipped += 1
            continue
        git_dir = os.path.realpath(common)
        key = os.path.normcase(git_dir)
        repo = repos.setdefault(key, {"git_dir": git_dir, "worktree": None, "seen_at": []})
        if seen_at not in repo["seen_at"]:
            repo["seen_at"].append(seen_at)
        if top and not repo["worktree"]:
            repo["worktree"] = os.path.realpath(top)

    out = []
    for repo in repos.values():
        gd = repo["git_dir"]
        n = git_line("--git-dir", gd, "rev-list", "--exclude=refs/stash", "--all", "--count")
        repo.update({
            "name":    label_for(repo["worktree"] or gd),
            "bare":    git_line("--git-dir", gd, "rev-parse", "--is-bare-repository") == "true",
            "shallow": (Path(gd) / "shallow").exists(),
            "commits": int(n) if n and n.isdigit() else 0,
        })
        out.append(repo)
    out.sort(key=lambda r: (r["commits"], r["name"].lower()))
    home.mkdir(parents=True, exist_ok=True)
    (home / "repos.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"\n  {len(out)} repositories (one per object store), {len(entries)} entries read, "
          f"{skipped} skipped\n")
    for r in out:
        flags = " ".join(f for f, on in (("shallow", r["shallow"]), ("bare", r["bare"])) if on)
        print(f"  {r['commits']:>6}  {r['name']}  {flags}")
    print(f"\n  -> {home / 'repos.json'}")


# ── plan ─────────────────────────────────────────────────────────────────────

def cmd_plan(args: argparse.Namespace, home: Path) -> None:
    from warf.cli import SUPPORTED_EXTENSIONS

    repos = json.loads((home / "repos.json").read_text(encoding="utf-8"))
    # A commit in several clones is reviewed once, in the largest clone that has it with its
    # history; the others go to also_in. Largest first, so shared history is credited to the
    # fullest clone and not to whichever fork happens to be smallest.
    seen: dict[str, dict] = {}
    for repo in sorted(repos, key=lambda r: (-r["commits"], r["name"].lower())):
        gd = repo["git_dir"]
        shallow_file = Path(gd) / "shallow"
        shallow = set(shallow_file.read_text(encoding="utf-8").split()) if shallow_file.exists() else set()
        # The diff settings `git show` uses, so the file count matches what run will review
        # (rename detection on: a rename is listed under its new name, as review-commit reviews it).
        out = git(gd, "log", "--exclude=refs/stash", "--all", "--name-only",
                  "--format=%x00%H%x01%P%x01%aI%x01%s")
        n_new = 0
        for block in out.split("\x00")[1:]:
            head, _, names = block.partition("\n")
            sha, parents, date, subject = (head.split("\x01", 3) + ["", "", ""])[:4]
            n_parents = len(parents.split())
            files = [f for f in names.split("\n") if f.strip() and Path(f).suffix in SUPPORTED_EXTENSIONS]
            entry = {
                "sha": sha, "repo": repo["name"], "git_dir": gd, "worktree": repo["worktree"],
                "parents": n_parents, "date": date, "subject": subject, "files": len(files),
                "root": n_parents == 0 and sha not in shallow, "shallow_boundary": sha in shallow,
                "also_in": [],
            }
            old = seen.get(sha)
            if old is None:
                seen[sha] = entry
                n_new += 1
            elif old["shallow_boundary"] and not entry["shallow_boundary"]:
                # A shallow clone's boundary commit shows its whole tree as added; a clone
                # with the history shows the real change. Review it there.
                entry["also_in"] = old["also_in"] + [old["repo"]]
                seen[sha] = entry
            else:
                old["also_in"].append(repo["name"])
        print(f"  {repo['name']}: {n_new} new commits", flush=True)

    # Review order: repositories owning fewer commits first (the small ones are one's own),
    # each newest commit first, as git log lists them. Phase A is ordinary commits; B those
    # touching more than --big files (initial imports, sweeping reformats); C the boundary
    # commits of shallow clones, which show a whole tree as added rather than a change.
    by_owner: dict[str, list[dict]] = {}
    for e in seen.values():
        by_owner.setdefault(e["repo"], []).append(e)
    phases: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    merges = no_files = 0
    for owner in sorted(by_owner, key=lambda r: (len(by_owner[r]), r.lower())):
        for e in by_owner[owner]:
            if e["parents"] > 1:
                merges += 1
            elif not e["files"]:
                no_files += 1
            else:
                e["phase"] = "C" if e["shallow_boundary"] else "B" if e["files"] > args.big else "A"
                phases[e["phase"]].append(e)
    plan = phases["A"] + phases["B"] + phases["C"]
    with (home / "plan.jsonl").open("w", encoding="utf-8") as f:
        for e in plan:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    hours = lambda n: n * SECONDS_PER_REVIEW / 3600
    print(f"\n  unique commits: {len(seen)}   merges (skipped): {merges}   "
          f"no supported file: {no_files}")
    what = {"A": f"<= {args.big} files", "B": f"> {args.big} files", "C": "shallow boundary"}
    for name, entries in phases.items():
        n = sum(e["files"] for e in entries)
        print(f"  phase {name}, {what[name]:<16}: {len(entries):>5} commits {n:>6} reviews  ~{hours(n):.1f} h")
    print(f"\n  -> {home / 'plan.jsonl'}")


# ── run ──────────────────────────────────────────────────────────────────────

def ensure_profile(home: Path, name: str, persona: str, model: str | None) -> Path:
    """One agent, LAYA, provider `laya`, the persona as the question: as run_laya_suite.py makes it."""
    from warf.state import AgentProfile, persona_hash, save_profiles
    path = home / "profiles" / f"{name}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing[0]["persona"] != persona or existing[0].get("model") != model:
            sys.exit(f"profile {name} already exists with another persona or model:\n"
                     f"  {existing[0]['persona']!r} model={existing[0].get('model')}")
        return path
    save_profiles(path, [AgentProfile(name="LAYA", persona=persona, provider="laya", model=model,
                                      persona_hash=persona_hash(persona))])
    return path


class LayaTap:
    """Keeps the last /v1/systemone response body. WaRF's provider renders the answer
    into its two-line vote text and drops the rest; the sweep wants the full-precision
    probabilities and the truncation report too. Reviews run one at a time, so one
    slot is enough."""

    def __init__(self) -> None:
        from warf.providers import SystemOneProvider
        self.body: dict | None = None
        original = SystemOneProvider._post
        tap = self

        def _post(provider, request, timeout):
            body = original(provider, request, timeout)
            tap.body = body
            return body

        SystemOneProvider._post = _post


def cmd_run(args: argparse.Namespace, home: Path) -> None:
    from warf.cli import SUPPORTED_EXTENSIONS, _parse_diff
    from warf.context_extractor import enrich_patch
    from warf.detector import detect_domain
    from warf.logger import session_dict
    from warf.orchestrator import run_review
    from warf.paths import find_context

    # One run per data directory. A second would review the same files again and
    # delete a STOP meant for the first; the lock dies with its process, even a killed one.
    lock = hold_lock(home / "run.lock")
    if lock is None:
        sys.exit(f"another run is using {home}: let it finish, or create {home / 'STOP'} and wait for it to exit")
    profile_path = ensure_profile(home, args.profile, args.persona, args.model)
    tap = LayaTap()
    health = server_health()
    if health is None:
        sys.exit(f"laya-serve is not answering on {server_url()}/health; start it first")

    sessions_path, commits_path, errors_path = (home / "sessions.jsonl", home / "commits.jsonl",
                                                home / "errors.jsonl")
    for p in (sessions_path, commits_path, errors_path):
        repair_tail(p)
    stop_path = home / "STOP"
    if stop_path.exists():
        stop_path.unlink()
    with (home / "runs.jsonl").open("a", encoding="utf-8") as f:   # which server answered when
        f.write(json.dumps({"started": datetime.now(timezone.utc).isoformat(), "profile": args.profile,
                            "persona": args.persona, "model": args.model, "server": server_url(),
                            "health": health, "argv": sys.argv[1:]}, ensure_ascii=False) + "\n")

    done_files = {(s["sweep"]["commit"], s["sweep"]["file"], s["sweep"].get("file_index", 0))
                  for s in read_jsonl(sessions_path)
                  if s.get("profile") == args.profile and "sweep" in s}
    # A commit is finished only with a session for every file its record counts: after a
    # hard crash the record can be on disk while a session line written before it is not.
    reviewed = collections.Counter(k[0] for k in done_files)
    done_commits = {c["sha"] for c in read_jsonl(commits_path)
                    if c.get("profile") == args.profile and c.get("status") in ("done", "no-files")
                    and reviewed[c["sha"]] >= (c.get("supported") or 0)}
    plan = read_jsonl(home / "plan.jsonl")
    if not plan:
        sys.exit(f"no plan in {home}; run `discover` and `plan` first")
    todo = [e for e in plan if e["sha"] not in done_commits
            and (not args.phase or e["phase"] == args.phase)
            and (not args.repo or args.repo.lower() in e["repo"].lower())]
    todo_shas = {e["sha"] for e in todo}
    est_left = max(0, sum(e["files"] for e in todo) - sum(1 for k in done_files if k[0] in todo_shas))
    print(f"\n  profile {args.profile} (model {args.model or 'provider default'}): {args.persona!r}")
    print(f"  plan {len(plan)} commits; done {len(done_commits)} commits, {len(done_files)} files; "
          f"left {len(todo)} commits, ~{est_left} reviews, ~{est_left * SECONDS_PER_REVIEW / 3600:.1f} h\n",
          flush=True)

    contexts: dict[str, str | None] = {}
    stop = threading.Event()
    work: queue.Queue = queue.Queue(maxsize=64)

    def prepare(entry: dict) -> None:
        sha, gd = entry["sha"], entry["git_dir"]
        cwd = entry["worktree"] or gd
        try:
            diff = git(gd, "show", f"-U{CONTEXT_LINES}", "--no-color", "--no-ext-diff",
                       "--src-prefix=a/", "--dst-prefix=b/", "--format=", sha, cwd=cwd)
        except RuntimeError as exc:
            work.put(("end", entry, {"status": "git-error", "error": str(exc)[:500]}))
            return
        patches = [(f, p) for f, p in _parse_diff(diff) if Path(f).suffix in SUPPORTED_EXTENSIONS]
        del diff
        occurrences: dict[str, int] = {}
        for path, patch in patches:
            if stop.is_set():
                return                              # cut short: no commit record, resume redoes it
            index = occurrences.get(path, 0)        # a type change lists one path twice
            occurrences[path] = index + 1
            if (sha, path, index) in done_files:
                continue
            try:
                enriched, enrich_error = enrich_patch(cwd, sha, path, patch), None
            except Exception as exc:
                # enrich_patch promises the patch back on a parse error, but it numbers a
                # "\ No newline at end of file" marker as a line, runs past the end of the
                # file and raises IndexError, which crashes review-commit. Keep its promise.
                enriched, enrich_error = patch, f"{type(exc).__name__}: {exc}"
            try:
                domain, why = detect_domain(Path(path), patch)
            except Exception as exc:
                work.put(("fail", entry, (path, index, f"detect_domain: {type(exc).__name__}: {exc}")))
                continue
            work.put(("file", entry, (path, index, patch, enriched, enrich_error, domain, why)))
        if not stop.is_set():
            work.put(("end", entry, {"status": "listed", "supported": len(patches)}))

    def produce() -> None:
        """git show, split, enrich and classify ahead of the reviews, so the git
        subprocesses overlap Laya's forward passes instead of adding to them. The
        closing "eof" says whether the whole plan was gone through, so that a thread
        that died is not taken for a finished run."""
        complete = False
        try:
            for entry in todo:
                if stop.is_set():
                    break
                try:
                    prepare(entry)
                except Exception as exc:            # one bad commit must not end the run
                    work.put(("end", entry, {"status": "producer-error",
                                             "error": f"{type(exc).__name__}: {exc}"[:500]}))
            else:
                complete = True
        finally:
            work.put(("eof", None, {"complete": complete}))

    producer = threading.Thread(target=produce, name="sweep-producer", daemon=True)
    producer.start()

    sessions = sessions_path.open("a", encoding="utf-8")
    commits = commits_path.open("a", encoding="utf-8")
    errors = errors_path.open("a", encoding="utf-8")
    t_start = last_status = time.time()
    n_done = n_err = consecutive_err = 0
    per_commit: dict[str, list[int]] = {}       # sha -> [reviewed, errors]
    tally = {"APPROVE": 0, "REJECT": 0}
    commit_t0: dict[str, float] = {}
    exit_code = 0

    def write_status(entry: dict | None) -> None:
        elapsed = time.time() - t_start
        rate = n_done / elapsed if elapsed > 0 else 0.0
        left = max(0, est_left - n_done)
        status = {
            "updated": datetime.now(timezone.utc).isoformat(), "profile": args.profile,
            "reviews_this_run": n_done, "errors_this_run": n_err, "votes_this_run": tally,
            "seconds_per_review": round(elapsed / n_done, 2) if n_done else None,
            "reviews_left_est": left, "eta_hours": round(left / rate / 3600, 1) if rate else None,
            "current": {"repo": entry["repo"], "commit": entry["sha"], "phase": entry["phase"]} if entry else None,
        }
        try:                                      # a reader holding the file must not end the run
            (home / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"  status.json not written: {exc}", flush=True)
        print(f"  [{datetime.now():%H:%M:%S}] {n_done} reviews ({n_err} errors) this run, "
              f"{status['seconds_per_review']} s each, ~{left} left, ETA {status['eta_hours']} h  "
              f"| {entry['repo'] if entry else ''}", flush=True)

    def log_error(entry: dict, path: str, index: int, error: str, state_chars: int | None) -> None:
        errors.write(json.dumps({"sha": entry["sha"], "repo": entry["repo"], "file": path,
                                 "file_index": index, "profile": args.profile, "error": error[:2000],
                                 "state_chars": state_chars, "at": datetime.now(timezone.utc).isoformat()},
                                ensure_ascii=False) + "\n")
        errors.flush()
        print(f"  ERROR {entry['repo']} {entry['sha'][:10]} {path}: {error[:200]}", flush=True)

    try:
        while True:
            kind, entry, payload = work.get()
            if kind == "eof":
                if payload["complete"]:
                    print("  every planned commit has been gone through", flush=True)
                else:
                    print("  the producer thread ended before the end of the plan (traceback above); "
                          "rerun to resume", flush=True)
                    exit_code = 4
                break
            sha = entry["sha"]
            commit_t0.setdefault(sha, time.time())
            counts = per_commit.setdefault(sha, [0, 0])

            if kind == "fail":
                path, index, error = payload
                n_err += 1
                counts[1] += 1
                log_error(entry, path, index, error, None)
                continue

            if kind == "end":
                status = payload["status"]
                if status == "listed":
                    status = ("no-files" if payload["supported"] == 0
                              else "partial" if counts[1] else "done")
                commits.write(json.dumps({
                    "sha": sha, "repo": entry["repo"], "profile": args.profile, "status": status,
                    "supported": payload.get("supported"), "reviewed": counts[0], "errors": counts[1],
                    "error": payload.get("error"), "seconds": round(time.time() - commit_t0.pop(sha), 1),
                    "at": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
                commits.flush()
                per_commit.pop(sha, None)
                continue

            if stop_path.exists():
                print("  STOP file found: stopping", flush=True)
                break
            if args.limit and n_done >= args.limit:
                print(f"  --limit {args.limit} reached", flush=True)
                break

            path, index, patch, enriched, enrich_error, domain, why = payload
            cwd = entry["worktree"] or entry["git_dir"]
            if cwd not in contexts:
                contexts[cwd] = find_context(Path(cwd)) if Path(cwd).exists() else None
            context = contexts[cwd]
            # The state the orchestrator builds for a decision agent (no reply-format block);
            # what is left of the 50 000 characters after its frame is the room for the code.
            ctx_section = f"Project context:\n{context}\n\n" if context else ""
            frame = len(f"Domain: {domain}\n\n{ctx_section}{INPUT_LABEL}:\n```\n") + len("\n```")
            room = MAX_STATE_CHARS - frame
            code = enriched if len(enriched) <= room else enriched[:room]

            attempt_started = time.time()
            while True:
                tap.body = None
                t0 = time.time()
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = run_review(code, domain, profile_path, verbose=False,
                                            input_label=INPUT_LABEL, context=context)
                    if len(result.votes) != 1 or tap.body is None:
                        raise RuntimeError(f"expected one Laya vote, got {len(result.votes)}")
                    error = None
                except Exception as exc:          # one file must not end a day-long run
                    error = f"{type(exc).__name__}: {exc}"
                dt = time.time() - t0
                unreachable = error is not None and ("Cannot reach" in error or "timed out" in error)
                if not unreachable:
                    break
                if time.time() - attempt_started > SERVER_WAIT or stop_path.exists():
                    break
                print(f"  laya-serve unreachable ({error[:120]}); waiting 30 s", flush=True)
                for _ in range(30):                   # a STOP is honoured while waiting, too
                    if stop_path.exists():
                        break
                    time.sleep(1)

            if error is not None and stop_path.exists():
                print("  STOP file found: stopping", flush=True)   # the file is redone on resume
                break

            if error is not None:
                n_err += 1
                consecutive_err += 1
                counts[1] += 1
                log_error(entry, path, index, error, len(code) + frame)
                if consecutive_err >= args.max_errors or (unreachable and time.time() - attempt_started > SERVER_WAIT):
                    print(f"  stopping: {consecutive_err} consecutive errors", flush=True)
                    exit_code = 3
                    break
                continue

            consecutive_err = 0
            body = tap.body
            answer = (body.get("answers") or {}).get("verdict") or {}
            record = session_dict(result, artifact_path=f"{sha}:{path}", profile_name=args.profile)
            record["sweep"] = {
                "repo": entry["repo"], "also_in": entry["also_in"], "commit": sha, "file": path,
                "file_index": index, "parents": entry["parents"], "author_date": entry["date"],
                "subject": entry["subject"], "phase": entry["phase"], "commit_files": entry["files"],
                "root": entry["root"], "shallow_boundary": entry["shallow_boundary"],
                "domain_reason": why, "patch_chars": len(patch), "enriched_chars": len(enriched),
                "enrich_error": enrich_error,
                "state_chars": len(code) + frame, "cut": len(code) < len(enriched),
                "laya": {"model": body.get("model"), "choice": answer.get("choice"),
                         "probabilities": answer.get("probabilities"),
                         "confidence": answer.get("confidence"), "usage": body.get("usage"),
                         "routing": body.get("routing")},
                "seconds": round(dt, 3),
            }
            sessions.write(json.dumps(record, ensure_ascii=False) + "\n")
            sessions.flush()
            n_done += 1
            counts[0] += 1
            tally[record["decision"]] = tally.get(record["decision"], 0) + 1
            if time.time() - last_status > args.status_every:
                write_status(entry)
                last_status = time.time()
    except KeyboardInterrupt:
        print("\n  interrupted: stopping", flush=True)
    finally:
        stop.set()
        while producer.is_alive():                # let a producer blocked on put() see the stop
            try:
                work.get(timeout=0.2)
            except queue.Empty:
                pass
        write_status(None)
        for f in (sessions, commits, errors):
            f.close()
    print(f"\n  sessions -> {sessions_path}")
    sys.exit(exit_code)


# ── status ───────────────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace, home: Path) -> None:
    plan = read_jsonl(home / "plan.jsonl")
    sessions = [s for s in read_jsonl(home / "sessions.jsonl") if s.get("profile") == args.profile]
    commit_recs = [c for c in read_jsonl(home / "commits.jsonl") if c.get("profile") == args.profile]
    errors = [e for e in read_jsonl(home / "errors.jsonl") if e.get("profile") == args.profile]
    finished = {c["sha"] for c in commit_recs if c["status"] in ("done", "no-files")}
    total = sum(e["files"] for e in plan)
    print(f"\n  profile {args.profile}: {len(sessions)} reviews of ~{total} planned "
          f"({100 * len(sessions) / max(1, total):.1f} %), {len(finished)}/{len(plan)} commits finished, "
          f"{len(errors)} errors logged")
    if not sessions:
        return
    rej = [s for s in sessions if s["decision"] == "REJECT"]
    p_rej = [s["sweep"]["laya"]["probabilities"].get("REJECT", 0.0) for s in sessions]
    cut = sum(1 for s in sessions if (s["sweep"]["laya"]["usage"] or {}).get("truncated"))
    print(f"  REJECT {len(rej)} / APPROVE {len(sessions) - len(rej)}   mean p(REJECT) "
          f"{sum(p_rej) / len(p_rej):.3f}   state read in full: {len(sessions) - cut}/{len(sessions)}")
    by_repo: dict[str, list[dict]] = {}
    for s in sessions:
        by_repo.setdefault(s["sweep"]["repo"], []).append(s)
    planned = {}
    for e in plan:
        planned[e["repo"]] = planned.get(e["repo"], 0) + e["files"]
    print(f"\n  {'reviews':>8} {'planned':>8} {'REJECT':>7}  repo")
    for repo, ss in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(ss):>8} {planned.get(repo, 0):>8} {sum(s['decision'] == 'REJECT' for s in ss):>7}  {repo}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one Laya profile over every git commit on this machine.")
    ap.add_argument("--home", default=str(DEFAULT_HOME), metavar="DIR",
                    help="data directory for the plan, sessions and profile (default: .warf-experiments/laya-sweep)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="profile name; created on first use")
    sub = ap.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="find the repositories, write repos.json")
    d.add_argument("--roots", nargs="+", default=["C:\\"], metavar="DIR", help="drives or folders to scan")
    d.add_argument("--from-list", nargs="+", metavar="FILE",
                   help="read `dir /s /b` output (paths of .git entries and HEAD files) instead of scanning")

    p = sub.add_parser("plan", help="list the commits to review, write plan.jsonl")
    p.add_argument("--big", type=int, default=50, metavar="N",
                   help="commits with more supported files than this go last (default: 50)")

    r = sub.add_parser("run", help="review the plan; resumes")
    r.add_argument("--persona", default=DEFAULT_PERSONA, help="the question Laya is asked")
    r.add_argument("--model", default=None, metavar="NAME",
                   help="Laya checkpoint (english, multilingual, typed-decisions); default: the provider's")
    r.add_argument("--phase", choices=["A", "B", "C"], default=None, help="only this part of the plan")
    r.add_argument("--repo", default=None, metavar="TEXT",
                   help="only commits of repositories whose name contains TEXT (case-insensitive)")
    r.add_argument("--limit", type=int, default=0, metavar="N", help="stop after N reviews")
    r.add_argument("--max-errors", type=int, default=20, metavar="N",
                   help="stop after N consecutive failed reviews (default: 20)")
    r.add_argument("--status-every", type=float, default=60.0, metavar="S",
                   help="seconds between progress lines and status.json updates (default: 60)")

    sub.add_parser("status", help="count what is done")
    args = ap.parse_args()

    home = Path(args.home).resolve()
    if home == (ROOT / ".warf").resolve():
        sys.exit("refusing to write experiment sessions into the corpus directory .warf/")
    home.mkdir(parents=True, exist_ok=True)
    # Before warf is imported: its paths are read from WARF_HOME.
    os.environ["WARF_HOME"] = str(home)
    os.environ["WARF_NO_BROWSER"] = "1"
    os.environ.pop("WARF_PROVIDER", None)
    os.environ.pop("WARF_MODEL", None)

    {"discover": cmd_discover, "plan": cmd_plan, "run": cmd_run, "status": cmd_status}[args.command](args, home)


if __name__ == "__main__":
    main()
