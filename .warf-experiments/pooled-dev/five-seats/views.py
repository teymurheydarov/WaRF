"""One-seat views from stored Jev answers on the RocksDB matched set (development, offline, no calls).

Every view is what one WaRF seat would return from one Jev call (several questions in one call where the
stored call asked several):
  P:<agent>        a persona seat of LO with the project context (../history/sessions_LO_ctx.jsonl)
  LB / LR          locate build / runtime, 1 - min_w p_w(NONE) (../locate/answers.jsonl, with context)
  LE               locate build and runtime in one call: 1 - min_w (p_w,build(NONE) * p_w,runtime(NONE))
  CK.mean/max/or   the seven project checks of one call (../history/answers_checks.jsonl, whole change, no
                   context): mean p(YES), max, and 1 - prod(1 - p) ("noisy or")
  DG.mean/max      the eleven diagnostics of the locate call (with context)
  V.whole          the verdict asked in the checks call; V.<state> the verdict of ../context and ../history
                   states (plain, ctx, commit, both, prof, prof_ctx), C.<state> their compile question

    import views; views.V[name][item] -> p(REJECT); views.auc(scores)"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
items = {json.loads(l)["id"]: json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
pos = [i for i in ids if items[i]["kind"] == "defective"]; neg = [i for i in ids if items[i]["kind"] == "clean"]
V = {}
for l in (HERE.parent / "history" / "sessions_LO_ctx.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    for v in r["votes"]:
        V.setdefault(f"P:{v['agent']}", {})[r["artifact"]] = v["p_reject"]
none, diag = {}, {}
for l in (HERE.parent / "locate" / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l); a = r["answers"]
    pb, pr = (a["build"]["p"] or {}).get("NONE", 1.0), (a["runtime"]["p"] or {}).get("NONE", 1.0)
    n = none.setdefault(r["id"], {"b": 1.0, "r": 1.0, "e": 1.0})
    n["b"], n["r"], n["e"] = min(n["b"], pb), min(n["r"], pr), min(n["e"], pb * pr)
    if r["window"] == 0:
        diag[r["id"]] = [(v["p"] or {}).get("YES", 0.0) for k, v in a.items() if k not in ("build", "runtime")]
V["LB"] = {i: 1 - none[i]["b"] for i in ids}; V["LR"] = {i: 1 - none[i]["r"] for i in ids}
V["LE"] = {i: 1 - none[i]["e"] for i in ids}
V["DG.mean"] = {i: sum(diag[i]) / len(diag[i]) for i in ids}; V["DG.max"] = {i: max(diag[i]) for i in ids}
CHK = ["inttype", "format", "warning", "assert", "lifetime", "concurrency", "edge"]
for l in (HERE.parent / "history" / "answers_checks.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if r["state"] != "whole":
        continue
    p = [(r["answers"][k]["p"] or {}).get("YES", 0.0) for k in CHK]
    V.setdefault("CK.mean", {})[r["id"]] = sum(p) / 7
    V.setdefault("CK.max", {})[r["id"]] = max(p)
    V.setdefault("CK.or", {})[r["id"]] = 1 - math.prod(1 - x for x in p)
    V.setdefault("V.whole", {})[r["id"]] = (r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0)
    for k, x in zip(CHK, p):
        V.setdefault(f"CK:{k}", {})[r["id"]] = x
for f in (HERE.parent / "context" / "answers.jsonl", HERE.parent / "history" / "answers.jsonl"):
    for l in f.open(encoding="utf-8"):
        r = json.loads(l)
        V.setdefault(f"V.{r['state']}", {})[r["id"]] = (r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0)
        if "compile" in r["answers"]:
            V.setdefault(f"C.{r['state']}", {})[r["id"]] = (r["answers"]["compile"]["p"] or {}).get("YES", 0.0)
for name, sc in V.items():
    if set(sc) != set(ids):
        raise SystemExit(f"view {name}: {len(set(ids) - set(sc))} items missing")


def auc(sc, P=pos, N=neg):
    vals = sorted([(sc[i], 1) for i in P] + [(sc[i], 0) for i in N])
    rank_sum, k = 0.0, 0
    while k < len(vals):
        j = k
        while j < len(vals) and vals[j][0] == vals[k][0]:
            j += 1
        rank_sum += (k + 1 + j) / 2 * sum(v[1] for v in vals[k:j])
        k = j
    return (rank_sum - len(P) * (len(P) + 1) / 2) / (len(P) * len(N))


if __name__ == "__main__":
    for name in sorted(V, key=lambda n: -auc(V[n])):
        print(f"  {name:<18} AUC {auc(V[name]):.3f}")
