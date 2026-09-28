"""
Persona A/B experiment.

Re-reviews every oracle-labelled artifact of the corpus that still exists on
disk, under a named experiment profile, and applies the known ground truth so
that discrimination can be measured afterwards with:

    py tools/measure_llr.py --home .warf-experiments --profile <name>

Two data directories, on purpose:

    .warf/               the human-labelled corpus. Read-only here: it supplies
                         the artifacts and their ground truth; nothing is written.
    .warf-experiments/   where this script's sessions and profiles go.

Experiment sessions must never land in the corpus log. The corpus is what the
talk's charts are generated from, and every review regenerates those charts
from the whole log: thirty extra labelled sessions once turned the published
27 / 63 / 75 calibration into 39 / 72 / 85. The cli.py children are therefore
started with WARF_HOME pointing at the experiments directory, and the script
refuses to run if that directory is the corpus.

A profile that does not exist yet is created in the experiments directory from
the personas currently in warf/state.py, so the workflow for a new persona
version is: edit state.py, then run this with a new --profile name.

Runs with --no-early-stop so every agent votes on every file. Without that, low
weight agents are polled less often and their measured discrimination is not
comparable with the rest of the panel.

Resumable: an artifact that already has a complete, labelled session under the
profile is skipped, so the script can be re-run after a quota pause without
repeating work or double applying the oracle.

Usage (from anywhere; relative paths resolve against the repo root):
    py tools/run_persona_experiment.py --profile persona_v4
    py tools/run_persona_experiment.py --profile persona_v4 --limit 4   # partial
    py tools/run_persona_experiment.py --profile persona_v4 --dry-run
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _groundtruth import corpus_truth, describe_conflicts  # noqa: E402

# The reviewer this script drives: the package's CLI, run as a script.
CLI = ROOT / "warf" / "cli.py"

CORPUS_HOME      = ROOT / ".warf"               # ground truth; never written to from here
EXPERIMENTS_HOME = ROOT / ".warf-experiments"   # default output; --home overrides


def _sessions(log: Path) -> list[dict]:
    if not log.exists():
        return []
    out = []
    with log.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def labelled_targets(only: set[str] | None = None) -> dict[str, tuple[str, str]]:
    """{artifact path relative to the repo root: (domain, ground truth label)}.

    Ground truth comes from tools/_groundtruth.py: one answer per FILE — every
    spelling the corpus logged it under mapped to the same file, the most recent
    label winning. Only files present on this disk are returned, since each one is
    reviewed. Matching on the raw path string instead once fed this script a
    label the corpus had already corrected (requests/help.py).

    The key is the path relative to the repo root, which is also what the children
    log, so resumability keeps matching on it.
    """
    truths = corpus_truth()
    for line in describe_conflicts(truths):
        print(f"  ! label changed over time — {line}")
    targets: dict[str, tuple[str, str]] = {}
    for t in truths.values():
        if t.file is None:                       # labelled, but not on this disk: cannot be reviewed
            continue
        spelling = os.path.relpath(t.file, ROOT)
        if only is None or spelling in only:
            targets[spelling] = (t.domain, t.label)
    return targets


def already_done(sessions: list[dict], profile: str, expected_panel: int) -> set[str]:
    """Artifacts with a COMPLETE session under this profile.

    A session whose panel is short (agents timed out, or the backend died partway)
    is deliberately not counted as done, so re-running the script retries it rather
    than leaving a biased hole in the sample.
    """
    return {
        s.get("artifact", "")
        for s in sessions
        if s.get("profile") == profile
        and len(s.get("votes", [])) >= expected_panel
        # An unlabelled session cannot be scored by measure_llr, so it does not
        # count as done even with a full panel (e.g. a manual review run without
        # --ground-truth).
        and s.get("oracle")
    }


def _session_for(log: Path, profile: str, artifact: str) -> dict | None:
    """Most recent LABELLED session for this (profile, artifact), re-read from disk."""
    match = None
    for s in _sessions(log):
        if (s.get("profile") == profile and s.get("artifact") == artifact
                and s.get("oracle")):
            match = s
    return match


def panel_size(profiles_dir: Path, profile: str) -> int:
    """How many agents this profile defines (5 if it does not exist yet)."""
    path = profiles_dir / f"{profile}.json"
    if not path.exists():
        return 5
    try:
        return len(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return 5


def _show(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-review the corpus's labelled artifacts under an experiment profile.")
    ap.add_argument("--profile", required=True, help="Experiment profile to run the panel under")
    ap.add_argument("--home", default=None, metavar="DIR",
                    help="Experiments data directory (default: .warf-experiments in the repo root)")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N files")
    ap.add_argument("--same-files-as", default=None, metavar="PROFILE",
                    help="Only review the files PROFILE has complete sessions for, so the two pools "
                         "can be compared file by file (tools/compare_pools.py)")
    ap.add_argument("--dry-run", action="store_true", help="List the plan and exit")
    ap.add_argument("--timeout", type=int, default=600,
                    help="Per-file timeout in seconds (default: 600)")
    args = ap.parse_args()

    # Corpus artifacts are usually logged relative to the repo root.
    os.chdir(ROOT)

    home = (Path(args.home) if args.home else EXPERIMENTS_HOME).resolve()
    if home == CORPUS_HOME.resolve():
        sys.exit("Refusing to write experiment sessions into the corpus (.warf): "
                 "the talk's charts are generated from it. Choose another --home.")

    exp_log      = home / "sessions.jsonl"
    exp_profiles = home / "profiles"
    # The children resolve their data directory from this, so their sessions and
    # profile updates land with the experiments and nowhere else.
    # WARF_NO_BROWSER: every review regenerates the dashboards, and four of them
    # open a browser tab when they do — not something to repeat once per file.
    child_env = {**os.environ, "WARF_HOME": str(home), "WARF_NO_BROWSER": "1"}

    only = None
    if args.same_files_as:
        ref_panel = panel_size(exp_profiles, args.same_files_as)
        only = already_done(_sessions(exp_log), args.same_files_as, ref_panel)
        if not only:
            sys.exit(f"--same-files-as {args.same_files_as}: that profile has no complete sessions in {_show(home)}")

    targets        = labelled_targets(only)
    expected_panel = panel_size(exp_profiles, args.profile)
    done           = already_done(_sessions(exp_log), args.profile, expected_panel)

    pending = [(p, d, t) for p, (d, t) in sorted(targets.items()) if p not in done]
    if args.limit:
        pending = pending[: args.limit]

    ok = fail = partial = consecutive = 0
    measure = f"py tools/measure_llr.py --home {_show(home)} --profile {args.profile}"

    print(f"Profile      : {args.profile}  ({expected_panel} agents)")
    print(f"Corpus       : {_show(CORPUS_HOME)}  (ground truth, read-only)")
    print(f"Experiments  : {_show(home)}")
    print(f"Labelled set : {len(targets)} artifact(s) on disk")
    print(f"Already done : {len(done)} complete")
    print(f"To run       : {len(pending)}")
    print()

    if not pending:
        print("Nothing to do. Measure with:")
        print(f"    {measure}")
        return

    for path, domain, truth in pending:
        print(f"  {truth:<8} {domain:<12} {Path(path).name}")
    print()

    if args.dry_run:
        print("Dry run — nothing executed.")
        return

    for i, (path, domain, truth) in enumerate(pending, 1):
        name = Path(path).name
        print(f"[{i}/{len(pending)}] {name}  [{domain}]  truth={truth} ... ",
              end="", flush=True)
        t0 = time.time()
        cmd = [
            sys.executable, str(CLI), "review", path,
            "--domain", domain,
            "--profile", args.profile,
            "--ground-truth", truth,
            "--no-early-stop",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=str(ROOT), env=child_env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT after {args.timeout}s")
            fail += 1
            consecutive += 1
            if consecutive >= 2:
                print("\nTwo consecutive timeouts — stopping. Re-run to resume.")
                break
            continue

        elapsed = time.time() - t0

        # Do not trust the exit code. review exits 1 for a REJECT verdict, so a
        # crash that also exits 1 is indistinguishable from a successful reject.
        # The only reliable evidence that the review happened is a session in the
        # experiments log carrying the full panel.
        written = _session_for(exp_log, args.profile, path)
        if written is None:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            reason = tail[-1][:160] if tail else f"rc={proc.returncode}"
            print(f"NO SESSION ({elapsed:.0f}s): {reason}")
            fail += 1
            consecutive += 1
        elif len(written.get("votes", [])) < expected_panel:
            got = len(written.get("votes", []))
            print(f"PARTIAL ({elapsed:.0f}s): only {got}/{expected_panel} agents voted")
            partial += 1
            consecutive = 0
        else:
            print(f"done ({elapsed:.0f}s)")
            ok += 1
            consecutive = 0

        # A run of failures almost always means quota exhaustion or a dead
        # backend. Stop rather than burning the rest of the list on calls that
        # cannot succeed; the script is resumable.
        if consecutive >= 2:
            print(f"\n{consecutive} consecutive failures — stopping.")
            print("Re-run the same command once quota restores; "
                  "completed files are skipped automatically.")
            break

    print(f"\n  ok={ok}  partial={partial}  failed={fail}")
    if partial or fail:
        print("  Incomplete runs are NOT counted as done and will be retried "
              "on the next invocation.")
    print("\nMeasure the result:")
    print(f"    {measure}")


if __name__ == "__main__":
    main()
