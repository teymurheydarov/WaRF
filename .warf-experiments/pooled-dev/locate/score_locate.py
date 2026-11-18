"""Line localisation and build diagnostics (run_locate.py) on the RocksDB matched set (development, offline).

  1. Ranking: AUC of build = 1 - prod_w p_w(NONE), runtime likewise, their combination, and each diagnostic;
     against prof_ctx's verdict (the same project context, WaRF's question) with a paired stratified bootstrap.
  2. Learned weights (../history/stack.py, 10-fold x 5 within RocksDB): all earlier views, + the new ones.

    python score_locate.py      # writes score_locate.log"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "history"))
import stack as K  # noqa: E402
from run_locate import DIAG  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


none, diag = {}, {}
for l in (HERE / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l); a = r["answers"]
    for q in ("build", "runtime"):
        p = (a.get(q, {}).get("p") or {}).get("NONE", 1.0)
        none.setdefault(r["id"], {}).setdefault(q, 1.0)
        none[r["id"]][q] *= p
    if r["window"] == 0:
        diag[r["id"]] = {k: (a[k]["p"] or {}).get("YES", 0.0) for k in DIAG}
if set(diag) != set(K.ids):
    raise SystemExit(f"{len(set(K.ids) - set(diag))} items missing")
S = {"build": {i: 1 - none[i]["build"] for i in K.ids}, "runtime": {i: 1 - none[i]["runtime"] for i in K.ids}}
S["either"] = {i: 1 - none[i]["build"] * none[i]["runtime"] for i in K.ids}
S["diag mean"] = {i: sum(diag[i].values()) / len(DIAG) for i in K.ids}
for k in DIAG:
    S[k] = {i: diag[i][k] for i in K.ids}
pos = [i for i in K.ids if K.Y[i] == 1]; neg = [i for i in K.ids if K.Y[i] == -1]


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


rng = random.Random(7)
boots = [([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(2000)]
ref = {i: K.ST["prof_ctx"][i]["verdict"] for i in K.ids}
say(f"1. Ranking on 800 RocksDB changes (AUC; reference: WaRF's question with the same context {auc(ref):.3f})")
for name, sc in S.items():
    d = sorted(auc(sc, P, N) - auc(ref, P, N) for P, N in boots)
    say(f"  {name:<10} {auc(sc):.3f}   vs reference {auc(sc) - auc(ref):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}]")

new = lambda i: [K.lg(S[k][i]) for k in ["build", "runtime"] + list(DIAG)]  # noqa: E731
loc = lambda i: [K.lg(S["build"][i]), K.lg(S["runtime"][i])]  # noqa: E731
base = K.F["all views"]
V = {"all views (stack.py)": base, "new views alone (13)": new, "localisation alone (2)": loc,
     "all views + localisation": lambda i: base(i) + loc(i), "all views + new views": lambda i: base(i) + new(i)}
say("\n2. Learned weights, 10-fold x 5 within RocksDB (balanced accuracy)")
for name, f in V.items():
    for sd in (1.0, 0.3):
        m, a, b = K.cv(f, sd)
        say(f"  {name:<28} prior sd {sd}: {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
(HERE / "score_locate.log").write_text("\n".join(out) + "\n", encoding="utf-8")
