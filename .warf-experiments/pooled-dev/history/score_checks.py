"""Score run_checks.py (and run_hist.py's profile states) on the RocksDB matched set (development).

  1. AUC of each project-learned check (its highest p(YES) over the whole change and its hunks), of their
     mean log-odds, and of the usual question asked in the same call.
  2. In WaRF: the seven checks as seats of one evidence group ("checks"; each Platt-calibrated, the group
     contributes their mean), alone and added to LO; the profile seat (prof) added too. 10-fold x 5
     cross-validation within RocksDB; LO's seats also calibrated on the other three projects.

    python score_checks.py      # writes score_checks.log"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv = [sys.argv[0], str(HERE / "answers.jsonl")]
sys.path.insert(0, str(HERE.parent / "context"))
import score_ctx as C  # noqa: E402  (its own output is printed first: plain/ctx/commit/prof states)

sys.path.insert(0, str(HERE))
from run_checks import rn  # noqa: E402

CH = list(rn.CHECKS)
whole, hunk = {}, {}
for l in (HERE / "answers_checks.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
if set(whole) != set(C.rdb):
    raise SystemExit(f"{len(set(C.rdb) - set(whole))} whole-change answers missing")
top = {i: {q: max([whole[i][q]] + [h[q] for h in hunk.get(i, [])]) for q in CH} for i in C.rdb}


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


C.say("\n4. Project-learned checks, highest p over the whole change and its hunks (AUC on 800 changes)")
C.say("  " + "  ".join(f"{q} {C.auc({i: top[i][q] for i in C.rdb}):.3f}" for q in CH))
C.say(f"  mean log-odds of the seven checks {C.auc({i: sum(lg(top[i][q]) for q in CH) / len(CH) for i in C.rdb}):.3f};"
      f" usual question in the same call {C.auc({i: whole[i]['verdict'] for i in C.rdb}):.3f}")


def check_seats(i):
    return [{"agent": f"CHK-{q}", "persona": C.persona_hash(rn.CHECKS[q]), "persona_text": rn.CHECKS[q], "provider": "jev",
             "model": "jev-1.14", "evidence_source": "checks", "p_reject": min(0.99, max(0.01, round(top[i][q], 2)))} for q in CH]


C.say("\n5. In WaRF (10-fold x 5 within RocksDB)")
m, a, b = C.cv(lambda i: check_seats(i))
C.say(f"  checks alone            {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
m, a, b = C.cv(lambda i: C.PERS[i] + (check_seats(i) if i in top else []), C.other)
C.say(f"  LO + checks             {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
if "prof" in C.S:
    m, a, b = C.cv(lambda i: C.PERS[i] + ([C.seat_new(i, "prof")] + check_seats(i) if i in top else []), C.other)
    C.say(f"  LO + checks + profile   {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
(HERE / "score_checks.log").write_text("\n".join(C.out) + "\n", encoding="utf-8")
