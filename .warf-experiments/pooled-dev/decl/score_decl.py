"""Retrieved declarations (run_decl.py) on the RocksDB matched set (development, offline, no calls).

  1. Ranking: AUC of the verdict and of the seven project checks with declarations (decl) against the same
     frame and questions without them (../history/answers_checks.jsonl, state `whole`), and with the project
     context (decl_ctx) against the verdict of prof_ctx (same context, questions verdict + compile);
     paired stratified bootstrap of the difference (2000 resamples).
  2. Control: the AUC of the declaration block's length alone (the blocks are longer for defective changes
     although added lines are matched), and the stacker with block length as its own feature, so a gain of the
     declaration views has to beat plain length.
  3. Learned weights (../history/stack.py, 10-fold x 5 within RocksDB).

    python score_decl.py      # writes score_decl.log"""
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "history"))
import stack as K  # noqa: E402  (views, labels and the cross-validation of stack.py)

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


D = {}
for l in (HERE / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    D.setdefault(r["state"], {})[r["id"]] = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0)
                                             for q, v in r["answers"].items()}
for s in ("decl", "decl_ctx"):
    if set(D.get(s, {})) != set(K.ids):
        raise SystemExit(f"state {s}: {len(set(K.ids) - set(D.get(s, {})))} answers missing")
BLEN = {json.loads(l)["id"]: len(json.loads(l)["block"]) for l in (HERE / "decl_items.jsonl").open(encoding="utf-8")}
pos = [i for i in K.ids if K.Y[i] == 1]; neg = [i for i in K.ids if K.Y[i] == -1]


def auc(sc, P=pos, N=neg):
    """Mann-Whitney AUC from mid-ranks (ties count one half); P and N may repeat items."""
    vals = sorted([(sc[i], 1) for i in P] + [(sc[i], 0) for i in N])
    rank_sum, k = 0.0, 0
    while k < len(vals):
        j = k
        while j < len(vals) and vals[j][0] == vals[k][0]:
            j += 1
        rank_sum += (k + 1 + j) / 2 * sum(v[1] for v in vals[k:j])
        k = j
    return (rank_sum - len(P) * (len(P) + 1) / 2) / (len(P) * len(N))


rng = random.Random(7)
boots = [([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(2000)]


def compare(new, base):
    d = sorted(auc(new, P, N) - auc(base, P, N) for P, N in boots)
    return f"{auc(base):.3f} -> {auc(new):.3f}  ({auc(new) - auc(base):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}])"


say("1. Ranking on 800 RocksDB changes (AUC without -> with declarations; 95% bootstrap interval of the difference)")
for q in ["verdict"] + K.CHK:
    say(f"  {q:<12} {compare({i: D['decl'][i][q] for i in K.ids}, {i: K.whole[i][q] for i in K.ids})}")
mean_new = {i: sum(D["decl"][i][q] for q in K.CHK) / 7 for i in K.ids}
mean_old = {i: sum(K.whole[i][q] for q in K.CHK) / 7 for i in K.ids}
say(f"  {'mean check':<12} {compare(mean_new, mean_old)}")
say(f"  with project context: verdict prof_ctx -> decl_ctx "
    f"{compare({i: D['decl_ctx'][i]['verdict'] for i in K.ids}, {i: K.ST['prof_ctx'][i]['verdict'] for i in K.ids})}")
for q in K.CHK:
    say(f"  {q:<12} decl -> decl_ctx {compare({i: D['decl_ctx'][i][q] for i in K.ids}, {i: D['decl'][i][q] for i in K.ids})}")
say(f"\n2. Control: AUC of the declaration block's length alone {auc(BLEN):.3f}")

blen = lambda i: [math.log(1 + BLEN[i])]  # noqa: E731
dv = lambda i: [K.lg(D[s][i][q]) for s in ("decl", "decl_ctx") for q in ["verdict"] + K.CHK]  # noqa: E731
base = K.F["all views"]
V = {
    "all views (stack.py)": base,
    "all views + block length": lambda i: base(i) + blen(i),
    "declaration views (16)": dv,
    "declaration views + block length": lambda i: dv(i) + blen(i),
    "all views + declarations": lambda i: base(i) + dv(i),
    "all views + declarations + length": lambda i: base(i) + dv(i) + blen(i),
}
say("\n3. Learned weights, 10-fold x 5 within RocksDB (balanced accuracy)")
for name, f in V.items():
    for sd in (1.0, 0.3):
        m, a, b = K.cv(f, sd)
        say(f"  {name:<36} prior sd {sd}: {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
(HERE / "score_decl.log").write_text("\n".join(out) + "\n", encoding="utf-8")
