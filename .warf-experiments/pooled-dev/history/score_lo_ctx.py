"""LO with the project context (run_lo_ctx.py) against LO, on the RocksDB matched set (development).

    python score_lo_ctx.py      # writes score_lo_ctx.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv = [sys.argv[0], str(HERE / "answers.jsonl")]
sys.path.insert(0, str(HERE.parent / "context"))
import score_ctx as C  # noqa: E402
sys.path.insert(0, str(HERE))
import score_checks as K  # noqa: E402  (check seats: K.check_seats)

C.out.clear()
CTXS = {}
for l in (HERE / "sessions_LO_ctx.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    CTXS[r["artifact"]] = [{"agent": v["agent"], "persona": v["persona"], "persona_text": C.TEXT[v["persona"]],
                            "provider": "jev", "model": v["model"], "evidence_source": "",
                            "p_reject": C.p_reject_from_text(v["reasoning"])} for v in r["votes"]]
if set(CTXS) != set(C.rdb):
    raise SystemExit(f"{len(set(C.rdb) - set(CTXS))} LO-with-context reviews missing")


def mean_p(ss):
    return sum(x["p_reject"] for x in ss) / len(ss)


base = {i: mean_p(C.PERS[i]) for i in C.rdb}; ctx = {i: mean_p(CTXS[i]) for i in C.rdb}
d = sorted(C.auc(ctx, P, N) - C.auc(base, P, N) for P, N in C.boots)
C.say(f"AUC of the five seats' mean p: LO {C.auc(base):.3f}, LO with project context {C.auc(ctx):.3f} "
      f"({C.auc(ctx) - C.auc(base):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}])")
C.say("\nBalanced accuracy on 800 RocksDB changes, 10-fold x 5 within RocksDB")
for name, cfg, extra in (("LO, RocksDB folds only", lambda i: C.PERS[i], ()),
                         ("LO, + other projects", lambda i: C.PERS[i], C.other),
                         ("LO with context, RocksDB folds only", lambda i: CTXS[i], ()),
                         ("LO with context + checks, RocksDB folds", lambda i: CTXS[i] + K.check_seats(i), ())):
    m, a, b = C.cv(cfg, extra)
    C.say(f"  {name:<42} {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
cal = C.calibrator(C.other, lambda i: C.PERS[i])
for name, S in (("LO", C.PERS), ("LO with context", CTXS)):
    pred = {i: C.decide(S[i], C.ITEMS[i]["domain"], cal) for i in C.rdb}
    C.say(f"  {name + ', calibrated on the other projects only':<42} {100 * C.ba(pred, C.rdb):5.1f}%")
(HERE / "score_lo_ctx.log").write_text("\n".join(C.out) + "\n", encoding="utf-8")
