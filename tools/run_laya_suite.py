"""
Laya over the validation suite: one single-agent decision profile, every file
of validation/M-00..M-13, ground truth applied, so that measure_llr can score it.

    py tools/run_laya_suite.py laya_q1 "Should this change be merged as it is? A defect you can point to is a REJECT."
    py tools/run_laya_suite.py laya_q1_typed --model typed-decisions "Should this change ..."
    py tools/measure_llr.py --home .warf-experiments/laya --profile laya_q1

Needs a laya-serve on http://127.0.0.1:8000 (or LAYA_BASE_URL). The profile is
created in the data directory on first use with one agent, LAYA, provider
`laya`, the persona text as the question; an existing profile of that name must
carry the same persona. Sessions go to .warf-experiments/laya/ by default
(--home overrides), never to the corpus in .warf/ — same split as
run_persona_experiment.py. Each run is 14 reviews of about a second each.

Prints one row per file: id, truth, Laya's vote, p(REJECT), Laya's confidence,
input tokens, seconds, and whether the vote matched the truth.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (id, artifact, domain, truth). M-00..M-06 from validation/corpus.json; M-04 and
# M-08..M-13 from the labelled corpus log (.warf/sessions.jsonl, see _groundtruth.py).
# M-07 is labelled nowhere: its own comments mark off-by-one reads and writes, a
# division by zero and an unchecked strcpy, hence REJECT.
SUITE = [
    ("M-00", "validation/M-00_baseline/calculator.cpp",          "LOGIC",       "APPROVE"),
    ("M-01", "validation/M-01_no_div_guard/calculator.cpp",      "LOGIC",       "REJECT"),
    ("M-02", "validation/M-02_type_error/main.cpp",              "LOGIC",       "REJECT"),
    ("M-03", "validation/M-03_missing_tests/test_calculator.py", "LOGIC",       "REJECT"),
    ("M-04", "validation/M-04_path_traversal/file_utils.py",     "SECURITY",    "REJECT"),
    ("M-05", "validation/M-05_slow_divide/calculator.cpp",       "PERFORMANCE", "REJECT"),
    ("M-06", "validation/M-06_overflow/calculator.cpp",          "LOGIC",       "REJECT"),
    ("M-07", "validation/M-07_early_stop/array_utils.cpp",       "LOGIC",       "REJECT"),
    ("M-08", "validation/M-08_sql_injection/db_query.py",        "SECURITY",    "REJECT"),
    ("M-09", "validation/M-09_race_condition/counter.py",        "PERFORMANCE", "REJECT"),
    ("M-10", "validation/M-10_cmd_injection/runner.py",          "SECURITY",    "REJECT"),
    ("M-11", "validation/M-11_buffer_overflow/string_ops.c",     "LOGIC",       "REJECT"),
    ("M-12", "validation/M-12_path_traversal/file_server.py",    "SECURITY",    "REJECT"),
    ("M-13", "validation/M-13_use_after_free/node_list.cpp",     "LOGIC",       "REJECT"),
]


def make_profile(home: Path, name: str, persona: str, model: str | None) -> Path:
    from warf.state import AgentProfile, persona_hash, save_profiles
    path = home / "profiles" / f"{name}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing[0]["persona"] != persona:
            sys.exit(f"profile {name} already exists with another persona:\n  {existing[0]['persona']!r}")
        return path
    save_profiles(path, [AgentProfile(name="LAYA", persona=persona, provider="laya", model=model,
                                      persona_hash=persona_hash(persona))])
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one Laya profile over validation/M-00..M-13.")
    ap.add_argument("profile", help="profile name; created on first use")
    ap.add_argument("persona", help="the question Laya is asked (the agent's persona text)")
    ap.add_argument("--model", default=None, metavar="NAME",
                    help="Laya checkpoint (english, multilingual, typed-decisions); default: the provider's")
    ap.add_argument("--ids", default=None, metavar="M-00,M-01,...", help="subset of the suite")
    ap.add_argument("--home", default=str(ROOT / ".warf-experiments" / "laya"), metavar="DIR",
                    help="data directory for sessions and profiles (default: .warf-experiments/laya)")
    args = ap.parse_args()

    home = Path(args.home).resolve()
    if home == (ROOT / ".warf").resolve():
        sys.exit("refusing to write experiment sessions into the corpus directory .warf/")
    home.mkdir(parents=True, exist_ok=True)
    os.environ["WARF_HOME"] = str(home)
    make_profile(home, args.profile, args.persona, args.model)

    env = dict(os.environ, WARF_HOME=str(home), WARF_NO_BROWSER="1", PYTHONIOENCODING="utf-8")
    env.pop("WARF_PROVIDER", None)
    env.pop("WARF_MODEL", None)
    wanted = set(args.ids.split(",")) if args.ids else None

    print(f"\nprofile {args.profile} (model {args.model or 'provider default'}): {args.persona!r}\n")
    print(f"  {'id':<5} {'truth':<8} {'vote':<8} {'p(REJ)':>7} {'conf':>5} {'in_tok':>6} {'s':>5}   ok")
    rows = []
    for sid, rel, domain, truth in SUITE:
        if wanted and sid not in wanted:
            continue
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "warf", "review", rel, "--domain", domain, "--ground-truth", truth,
             "--profile", args.profile, "--no-early-stop", "--json"],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        dt = time.time() - t0
        if proc.returncode not in (0, 1) or not proc.stdout.strip():
            sys.exit(f"  {sid}: review failed, rc={proc.returncode}\n{proc.stderr[-1500:]}")
        rec = json.loads(proc.stdout)
        v = rec["votes"][0]
        vote = "APPROVE" if v["vote"] == 1 else "REJECT"
        m = re.search(r"p\(REJECT\)=([0-9.]+)\s+confidence=([0-9.]+)", v["reasoning"])
        p_rej, conf = (float(m.group(1)), float(m.group(2))) if m else (float("nan"),) * 2
        ok = vote == truth
        rows.append((sid, truth, vote, p_rej, conf, ok))
        print(f"  {sid:<5} {truth:<8} {vote:<8} {p_rej:>7.2f} {conf:>5.2f} {v.get('tokens_in', 0):>6} "
              f"{dt:>5.1f}   {'yes' if ok else 'NO'}")

    n = len(rows)
    bad = [r[3] for r in rows if r[1] == "REJECT"]
    good = [r[3] for r in rows if r[1] == "APPROVE"]
    print(f"\n  correct: {sum(r[5] for r in rows)}/{n}   REJECT votes: {sum(r[2] == 'REJECT' for r in rows)}/{n}"
          f"   mean p(REJECT) on defective: {sum(bad) / max(1, len(bad)):.2f}, on clean: {sum(good) / max(1, len(good)):.2f}")
    print(f"\n  sessions -> {home / 'sessions.jsonl'}")
    print(f"  score    -> py tools/measure_llr.py --home {os.path.relpath(home, ROOT)} --profile {args.profile}")


if __name__ == "__main__":
    main()
