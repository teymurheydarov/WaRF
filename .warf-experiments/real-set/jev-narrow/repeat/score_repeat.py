"""Score the "repeat" lever: three identical runs of the frozen run_narrow.py request (README.md).

    python -B score_repeat.py   # no calls; reads ../answers.jsonl (run 1), run2.jsonl, run3.jsonl

Scores, fixed before looking at results (primary first):
  N_mean3  per call, mean of p over runs 1-3, then hmax over hunks + mean logit of the 7 checks (primary)
  N_run2   frozen N from run 2 alone
  N_run3   frozen N from run 3 alone
  N_mean12 as N_mean3 with runs 1 and 2 only (dose-response)"""
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as J  # noqa: E402

RUNS = {"run1": HERE.parent / "answers.jsonl", "run2": HERE / "run2.jsonl", "run3": HERE / "run3.jsonl"}
QS = ["verdict"] + J.GENERIC


def calls(path):
    """(id, state, hunk) -> {question: p}, p = P(REJECT) for verdict, P(YES) otherwise; plus models, cost."""
    out, models, cost = {}, set(), 0.0
    for l in Path(path).open(encoding="utf-8"):
        r = json.loads(l)
        k = (r["id"], r["state"], r["hunk"])
        if k in out:
            raise SystemExit(f"{path}: duplicate call {k}")
        out[k] = {q: (v.get("p") or {}).get("REJECT" if q == "verdict" else "YES", 0.0)
                  for q, v in (r.get("answers") or {}).items()}
        models.add(r.get("model")); cost += float((r.get("usage") or {}).get("cost") or 0)
    return out, models, cost


def to_wh(c):
    whole, hunk = {}, {}
    for (i, st, k), p in sorted(c.items()):
        if st == "whole":
            whole[i] = p
        else:
            hunk.setdefault(i, []).append(p)
    return whole, hunk


def N(c):
    w, h = to_wh(c)
    return {i: J.meanlg(w, h, J.GENERIC, i) for i in J.ids}


def mean_calls(cs):
    keys = set(cs[0])
    for c in cs[1:]:
        if set(c) != keys:
            raise SystemExit("runs do not have the same calls")
    return {k: {q: sum(c[k][q] for c in cs) / len(cs) for q in QS} for k in keys}


def main():
    R, tot = {}, 0.0
    for name, p in RUNS.items():
        c, models, cost = calls(p)
        R[name] = c; tot += cost
        print(f"{name}: {len(c)} calls, models {sorted(models)}, cost ${cost:.4f}")
    print(f"cost runs 2+3: ${tot - calls(RUNS['run1'])[2]:.4f}\n")

    print("Call-to-call noise per question (pairs of runs, 321 calls each, both states)")
    print(f"{'question':10} {'mean|dp|':>9} {'max|dp|':>8} {'same p':>7} {'same choice':>11} {'whole mean|dp|':>14}")
    for q in QS:
        d, dw, same, samec = [], [], 0, 0
        for a, b in combinations(R, 2):
            for k in R[a]:
                x, y = R[a][k][q], R[b][k][q]
                d.append(abs(x - y)); same += x == y; samec += (x >= 0.5) == (y >= 0.5)
                if k[1] == "whole":
                    dw.append(abs(x - y))
        print(f"{q:10} {statistics.mean(d):9.3f} {max(d):8.2f} {same / len(d):7.2f} {samec / len(d):11.2f} "
              f"{statistics.mean(dw):14.3f}")

    ref = J.ref_N()
    Ns = {"N_run1": N(R["run1"]), "N_run2": N(R["run2"]), "N_run3": N(R["run3"])}
    assert all(abs(Ns["N_run1"][i] - ref[i]) < 1e-12 for i in J.ids), "run 1 does not reproduce ref_N"
    print("\nItem-level N noise: mean |dN| between runs (logit units), Spearman-free check of rank agreement")
    for a, b in combinations(["N_run1", "N_run2", "N_run3"], 2):
        dn = [abs(Ns[a][i] - Ns[b][i]) for i in J.ids]
        print(f"  {a} vs {b}: mean |dN| {statistics.mean(dn):.3f}, max {max(dn):.3f}")

    scores = {"N_mean3 (primary)": N(mean_calls([R["run1"], R["run2"], R["run3"]])),
              "N_run2": Ns["N_run2"], "N_run3": Ns["N_run3"],
              "N_mean12": N(mean_calls([R["run1"], R["run2"]]))}
    print(f"\n{'score':18} {'auc':>6} {'within':>7} {'loo_size':>9}   d vs ref_N [95% CI]")
    print(f"{'ref_N (run 1)':18} {J.auc(ref):6.3f} {J.within(ref):7.3f} {J.loo_size(ref):9.3f}")
    for name, s in scores.items():
        d, lo, hi = J.boot_diff(s, ref)
        print(f"{name:18} {J.auc(s):6.3f} {J.within(s):7.3f} {J.loo_size(s):9.3f}   {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")


if __name__ == "__main__":
    main()
