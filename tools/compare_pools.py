"""
Head-to-head comparison of agent pools that reviewed the same files.

Each pool is an experiment profile whose sessions were produced by
tools/run_persona_experiment.py: same files, --no-early-stop (every agent votes
on every file), ground truth copied from the corpus. Because all votes are on
record, each pool is scored twice:

    as run    the verdict WaRF actually returned. Weights move while the runner
              labels file after file, so later files are judged with weights the
              earlier ones produced.
    uniform   the same votes replayed with every weight at 0.5, in profile order,
              stopping at the first boundary like a normal review. This is the
              like-for-like view: same weights, same SPRT, same files — only the
              personas differ.

It also reports how often the agents of a pool agree with each other. Five copies
of one persona that always vote alike are one opinion counted five times, and the
SPRT — which treats votes as independent evidence — turns that into confidence.

Zero API cost: reads sessions.jsonl and the profile files only.

Usage:
    py tools/compare_pools.py persona_v3 h2h_auditor5 h2h_skeptic5_v3
    py tools/compare_pools.py --home .warf-experiments persona_v2 persona_v3
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warf.engine import A, B, LLR_APPROVE, LLR_REJECT, synthesis  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _groundtruth import corpus_truth, describe_conflicts, truth_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UNIFORM = 0.5
CORPUS_NOTE = ".warf/sessions.jsonl"

# The table uses em dashes and arrows; a Windows console or a redirect defaults to
# cp1252 and would print them as garbage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_pool(home: Path, profile: str) -> dict[str, dict]:
    """{artifact: latest complete labelled session} for one profile."""
    try:
        order = [a["name"] for a in json.loads((home / "profiles" / f"{profile}.json").read_text(encoding="utf-8"))]
    except (OSError, json.JSONDecodeError):
        order = []
    out: dict[str, dict] = {}
    log = home / "sessions.jsonl"
    if not log.exists():
        return out
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        if s.get("profile") != profile or not s.get("oracle"):
            continue
        if order and len(s.get("votes", [])) < len(order):
            continue                                   # a short panel is not a complete run
        s["_order"] = order
        out[s["artifact"]] = s                         # later lines win
    return out


def uniform_replay(session: dict) -> tuple[str, str, float, int]:
    """(decision, confidence, lambda, votes used) with every weight at 0.5."""
    rank = {name: i for i, name in enumerate(session.get("_order") or [])}
    votes = sorted(session["votes"], key=lambda v: rank.get(v["agent"], 99))
    lam = 0.0
    for k, v in enumerate(votes, 1):
        lam += UNIFORM * (LLR_APPROVE if v["vote"] == 1 else LLR_REJECT)
        if lam >= A:
            return "APPROVE", "HIGH", lam, k
        if lam <= B:
            return "REJECT", "HIGH", lam, k
    decision, confidence, _ = synthesis([v["vote"] for v in votes], [UNIFORM] * len(votes), session["domain"])
    return decision.value, confidence.value, lam, len(votes)


def agreement(session: dict) -> float:
    """Share of agent pairs that cast the same vote on this file."""
    votes = [v["vote"] for v in session["votes"]]
    pairs = list(combinations(votes, 2))
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else 1.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare pools that reviewed the same files.")
    ap.add_argument("profiles", nargs="+", help="Experiment profiles to compare (first = reference)")
    ap.add_argument("--home", default=str(ROOT / ".warf-experiments"), metavar="DIR")
    ap.add_argument("--truth", action="append", default=[], metavar="NAME=LABEL",
                    help="Score a file against this ground truth instead of the label stored with the "
                         "experiment sessions, e.g. --truth help.py=REJECT. NAME matches the end of the "
                         "artifact path.")
    ap.add_argument("--stored-labels", action="store_true",
                    help="Score against the label stored with each experiment session instead of the "
                         "corpus's current ground truth (reproduces a run's original scoring)")
    args = ap.parse_args()
    home = Path(args.home)

    overrides: dict[str, int] = {}
    for item in args.truth:
        name, _, label = item.partition("=")
        if label.upper() not in ("APPROVE", "REJECT"):
            sys.exit(f"--truth {item}: expected NAME=APPROVE or NAME=REJECT")
        overrides[name.replace("\\", "/").lower()] = 1 if label.upper() == "APPROVE" else -1

    # Ground truth: the corpus's CURRENT answer for the file (one per file, the most
    # recent label wins — see _groundtruth.py). The label stored with an experiment
    # session is only what the runner copied at the time; it may have been corrected.
    truths = {} if args.stored_labels else corpus_truth()

    def truth_source(artifact: str, session: dict) -> tuple[int, str]:
        """(label, where it came from: 'override', 'corpus' or 'stored')."""
        a = artifact.replace("\\", "/").lower()
        for name, x in overrides.items():
            if a.endswith(name):
                return x, "override"
        known = truth_for(artifact, truths)
        if known is not None:
            return known.x_star, "corpus"
        return session["oracle"]["x_star"], "stored"

    def truth_of(artifact: str, session: dict) -> int:
        return truth_source(artifact, session)[0]

    pools = {p: load_pool(home, p) for p in args.profiles}
    for p, sessions in pools.items():
        if not sessions:
            sys.exit(f"No complete labelled sessions for profile '{p}' in {home}")
    common = sorted(set.intersection(*(set(s) for s in pools.values())),
                    key=lambda a: (-truth_of(a, pools[args.profiles[0]][a]), a))
    skipped = {p: len(s) - len(common) for p, s in pools.items() if len(s) != len(common)}

    print(f"\n{'=' * 100}\n  Pools on the same files   ({len(common)} files in common)\n{'=' * 100}")
    if skipped:
        print("  not in every pool, ignored: " + ", ".join(f"{p}: {n}" for p, n in skipped.items()))
    if not common:
        sys.exit("  No file was reviewed by every pool.")

    # A file the corpus has no label for is scored against the label the experiment
    # stored at the time, which the corpus may have corrected since. Say so, loudly,
    # rather than presenting the result as the corpus's current ground truth.
    fell_back = [] if args.stored_labels else sorted(
        Path(a).name for a in common
        if truth_source(a, pools[args.profiles[0]][a])[1] == "stored")
    if fell_back:
        print(f"\n  WARNING: {len(fell_back)} of {len(common)} files have no label in the corpus "
              f"({CORPUS_NOTE}).\n  They are scored against the label stored with each experiment "
              f"session, which may be out of date:\n    " + ", ".join(fell_back))

    width = 25
    print(f"\n  {'file':<26}{'truth':<9}" + "".join(f"{p[:width - 2]:<{width}}" for p in args.profiles))
    print(f"  {'':<26}{'':<9}" + "".join(f"{'votes  as run / uniform':<{width}}" for _ in args.profiles))
    print(f"  {'-' * (35 + width * len(args.profiles))}")

    tally = {p: {"run": 0, "uni": 0, "high": 0, "high_wrong": 0, "uhigh": 0, "uhigh_wrong": 0,
                 "agree": [], "unanimous": 0, "app_good": 0, "n_good": 0, "app_bad": 0, "n_bad": 0}
             for p in args.profiles}
    for art in common:
        truth = truth_of(art, pools[args.profiles[0]][art])
        mark = "*" if truth != pools[args.profiles[0]][art]["oracle"]["x_star"] else ""
        line = f"  {Path(art).name[:25]:<26}{('APPROVE' if truth == 1 else 'REJECT') + mark:<9}"
        for p in args.profiles:
            s, t = pools[p][art], tally[p]
            pattern = "".join("A" if v["vote"] == 1 else "R" for v in s["votes"])
            run_ok = (1 if s["decision"] == "APPROVE" else -1) == truth
            u_dec, u_conf, _, _ = uniform_replay(s)
            uni_ok = (1 if u_dec == "APPROVE" else -1) == truth
            t["run"] += run_ok
            t["uni"] += uni_ok
            if s["confidence"] == "HIGH":
                t["high"] += 1
                t["high_wrong"] += not run_ok
            if u_conf == "HIGH":
                t["uhigh"] += 1
                t["uhigh_wrong"] += not uni_ok
            a = agreement(s)
            t["agree"].append(a)
            t["unanimous"] += a == 1.0
            for v in s["votes"]:
                if truth == 1:
                    t["n_good"] += 1
                    t["app_good"] += v["vote"] == 1
                else:
                    t["n_bad"] += 1
                    t["app_bad"] += v["vote"] == 1
            cell = (f"{pattern} {s['decision'][0]}-{s['confidence'][:3]}{'' if run_ok else '!'}"
                    f" / {u_dec[0]}-{u_conf[:3]}{'' if uni_ok else '!'}")
            line += f"{cell:<{width}}"
        print(line)

    n = len(common)
    print(f"\n  {'':<35}" + "".join(f"{p[:width - 2]:<{width}}" for p in args.profiles))
    rows = [
        ("correct, as run",               lambda t: f"{t['run']}/{n}"),
        ("correct, uniform weights",      lambda t: f"{t['uni']}/{n}"),
        ("HIGH verdicts (wrong), as run", lambda t: f"{t['high']} ({t['high_wrong']} wrong)"),
        ("HIGH verdicts (wrong), uniform", lambda t: f"{t['uhigh']} ({t['uhigh_wrong']} wrong)"),
        ("P1  approve | good code",       lambda t: f"{t['app_good'] / t['n_good']:.3f}" if t["n_good"] else "n/a"),
        ("P0  approve | bad code",        lambda t: f"{t['app_bad'] / t['n_bad']:.3f}" if t["n_bad"] else "n/a"),
        ("agents agreeing, mean of pairs", lambda t: f"{sum(t['agree']) / len(t['agree']):.2f}"),
        ("files with a unanimous pool",   lambda t: f"{t['unanimous']}/{n}"),
    ]
    for label, fn in rows:
        print(f"  {label:<35}" + "".join(f"{fn(tally[p]):<{width}}" for p in args.profiles))
    if args.stored_labels:
        source = "the label stored with each session (--stored-labels)"
    elif fell_back:
        source = (f"the corpus's current label for {len(common) - len(fell_back)} files; "
                  f"the stored session label for {len(fell_back)} (see the warning above)")
    else:
        source = "the corpus's current label for each file"
    print("\n  Ground truth: " + source)
    changed = describe_conflicts(truths)
    if changed:
        print("  * differs from the label the runner stored — " + "; ".join(changed))
    if overrides:
        print("    given on the command line: "
              + ", ".join(f"{n}={'APPROVE' if x == 1 else 'REJECT'}" for n, x in overrides.items()))
    print("\n  Cells: votes in the order cast, then verdict-confidence as run / with uniform weights;"
          "\n  '!' marks a wrong verdict. n is small: read differences of one file as noise.\n")


if __name__ == "__main__":
    main()
