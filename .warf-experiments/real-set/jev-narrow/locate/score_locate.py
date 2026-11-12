"""Score the "locate" lever (answers_locate.jsonl) with ../jevscore.py. Scores fixed before the run:
  locate (primary): max over the item's chunks of 1 - P(NONE)  (deletion-only hunks have no locate question: 0)
  checks:           mean over the 7 generic checks of logit(max over chunks of P(YES)), this run (re-run of ref N)
  maxline:          max over chunks and lines of P(Lj)

    python -B score_locate.py   # writes score.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as js  # noqa: E402

recs = [json.loads(l) for l in (HERE / "answers_locate.jsonl").open(encoding="utf-8")]
by = {}
for r in recs:
    by.setdefault(r["id"], []).append(r)
missing = set(js.ids) - set(by)
if missing:
    sys.exit(f"{len(missing)} items have no answers")


def p_of(r, q):
    return ((r["answers"].get(q) or {}).get("p") or {})


S = {"locate": {}, "checks": {}, "maxline": {}}
for i in js.ids:
    rs = by[i]
    S["locate"][i] = max((1 - p_of(r, "locate").get("NONE", 1.0)) if r["k"] else 0.0 for r in rs)
    S["maxline"][i] = max([v for r in rs for c, v in p_of(r, "locate").items() if c != "NONE"] or [0.0])
    S["checks"][i] = sum(js.lg(max(p_of(r, q).get("YES", 0.0) for r in rs)) for q in js.GENERIC) / len(js.GENERIC)

N = js.ref_N()
cost = sum(float((r.get("usage") or {}).get("cost") or 0) for r in recs)
lines = [f"{len(recs)} calls, {len(by)} items, cost in answers_locate.jsonl ${cost:.5f}",
         "score     auc    within  loo_size  d_vs_N  [lo, hi]"]
for name, s in [("ref_N", N)] + list(S.items()):
    d, lo, hi = js.boot_diff(s, N)
    lines.append(f"{name:8s} {js.auc(s):.3f}  {js.within(s):.3f}   {js.loo_size(s):.3f}   {d:+.3f}  [{lo:+.3f}, {hi:+.3f}]")
print("\n".join(lines))
(HERE / "score.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
json.dump({k: v for k, v in S.items()}, (HERE / "scores.json").open("w", encoding="utf-8"))
