"""Score lever "context" (answers_context.jsonl) with jevscore. Writes score_context.log.

Four scores, fixed before the run:
  C  (PRIMARY) whole state + related code, mean logit of the 7 generic checks
  CV whole state + related code, verdict logit P(REJECT)
  CA mean of C and W0 (the same checks without the related code)
  CN N-style: per check the max of {whole + related code, the stored hunks of answers.jsonl}, mean logit
References: N = jevscore.ref_N(); W0 = whole state without related code, mean logit of the 7 checks
(answers.jsonl); V0 = verdict on the whole state without related code."""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as j  # noqa: E402
import json  # noqa: E402

G = j.GENERIC
w0, h0 = j.load(j.HERE / "answers.jsonl")
wc, _ = j.load(HERE / "answers_context.jsonl")
cost = sum(float((json.loads(l).get("usage") or {}).get("cost") or 0) for l in (HERE / "answers_context.jsonl").open(encoding="utf-8"))
n_calls = sum(1 for _ in (HERE / "answers_context.jsonl").open(encoding="utf-8"))

N = j.ref_N()
W0 = {i: sum(j.lg(w0[i][q]) for q in G) / len(G) for i in j.ids}
V0 = {i: j.lg(w0[i]["verdict"]) for i in j.ids}
C = {i: sum(j.lg(wc[i][q]) for q in G) / len(G) for i in j.ids}
CV = {i: j.lg(wc[i]["verdict"]) for i in j.ids}
CA = {i: (C[i] + W0[i]) / 2 for i in j.ids}
CN = {i: sum(j.lg(max([wc[i][q]] + [h[q] for h in h0.get(i, []) if q in h])) for q in G) / len(G) for i in j.ids}

clean = [i for i in j.ids if not j.D[i]]
nof = [i for i in j.ids if j.ITEMS[i].get("visible") == "needs_other_file"]
rest = [i for i in j.ids if j.D[i] and j.ITEMS[i].get("visible") != "needs_other_file"]


def boot_sub(s, r, pos, neg=clean, n=2000, seed=4):
    rng = random.Random(seed); d = []
    for _ in range(n):
        smp = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        d.append(j.auc(s, smp) - j.auc(r, smp))
    d.sort()
    return j.auc(s, pos + neg) - j.auc(r, pos + neg), d[int(0.025 * n)], d[int(0.975 * n) - 1]


out = [f"answers_context.jsonl: {n_calls} calls, cost ${cost:.6f}", "",
       f"{'score':<34} {'AUC':>6} {'within':>7} {'LOO':>6}   {'d vs N [95%]':>24}   {'d vs W0 [95%]':>24}   "
       f"{'AUC nof17':>9} {'AUC rest49':>10}"]
rows = {}
for name, s in (("N  ref: generic 7, hunk max", N), ("W0 ref: generic 7, whole, no ctx", W0),
                ("V0 ref: verdict, whole, no ctx", V0), ("C  PRIMARY: generic 7, whole+ctx", C),
                ("CV verdict, whole+ctx", CV), ("CA mean of C and W0", CA), ("CN max(whole+ctx, hunks)", CN)):
    a, wi, lo = j.auc(s), j.within(s), j.loo_size(s)
    dn, dw = j.boot_diff(s, N), j.boot_diff(s, W0)
    an, ar = j.auc(s, nof + clean), j.auc(s, rest + clean)
    rows[name.split()[0]] = dict(auc=a, within=wi, loo=lo, dN=dn, dW=dw, nof=an, rest=ar)
    out.append(f"{name:<34} {a:6.3f} {wi:7.3f} {lo:6.3f}   {dn[0]:+.3f} [{dn[1]:+.3f},{dn[2]:+.3f}]   "
               f"{dw[0]:+.3f} [{dw[1]:+.3f},{dw[2]:+.3f}]   {an:9.3f} {ar:10.3f}")
out += ["", "Subset bootstrap (17 needs_other_file defects vs 66 clean), d = AUC(score) - AUC(ref):"]
for name, s, r, rn in (("C - W0", C, W0, "W0"), ("C - N", C, N, "N"), ("CV - V0", CV, V0, "V0")):
    d = boot_sub(s, r, nof)
    out.append(f"  {name:<8} {d[0]:+.3f} [{d[1]:+.3f},{d[2]:+.3f}]")
out += ["", "Subset bootstrap (49 other defects vs 66 clean):"]
for name, s, r in (("C - W0", C, W0), ("CV - V0", CV, V0)):
    d = boot_sub(s, r, rest)
    out.append(f"  {name:<8} {d[0]:+.3f} [{d[1]:+.3f},{d[2]:+.3f}]")
# per-check AUC with and without the related code
out += ["", f"{'check':<10} {'AUC no ctx':>10} {'AUC ctx':>8} {'within no':>10} {'within ctx':>11}"]
for q in G:
    s0 = {i: w0[i][q] for i in j.ids}; s1 = {i: wc[i][q] for i in j.ids}
    out.append(f"{q:<10} {j.auc(s0):10.3f} {j.auc(s1):8.3f} {j.within(s0):10.3f} {j.within(s1):11.3f}")
# Spearman-like agreement: AUC of C vs W0 ranks is not needed; report rank correlation
def ranks(s):
    o = sorted(j.ids, key=lambda i: s[i]); return {i: k for k, i in enumerate(o)}
rC, rW = ranks(C), ranks(W0); n = len(j.ids)
rho = 1 - 6 * sum((rC[i] - rW[i]) ** 2 for i in j.ids) / (n * (n * n - 1))
out += ["", f"Spearman(C, W0) = {rho:.3f} (ties broken by order)"]
txt = "\n".join(out) + "\n"
print(txt)
(HERE / "score_context.log").write_text(txt, encoding="utf-8")
(HERE / "score_context.json").write_text(json.dumps({"cost": cost, "n_calls": n_calls, "rows": rows}, indent=1), encoding="utf-8")
