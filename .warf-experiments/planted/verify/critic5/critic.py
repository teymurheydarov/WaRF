"""Critic5: checks beyond five-audit, from stored records only (pure Python, no warf import, no calls).
    python -B critic.py > critic.log"""
import json, math, random
from itertools import product
from pathlib import Path
HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
FOUR = EXP.parent / "four-arms"
HARMLESS, NOCOMPILE, DEAD = {15, 18, 22, 31, 33}, {17, 32, 35, 47, 54}, {46, 50}
ORIG_DEFECT = {5, 7, 26, 31, 36, 39, 52, 53}
items = [json.loads(l) for l in (EXP / "items.jsonl").open(encoding="utf-8")]
num = {it["base"]: k + 1 for k, it in enumerate(i for i in items if i["kind"] == "planted")}
bases = list(num)


def load(arm, d=EXP, key="planted"):
    out = {}
    for p in sorted(d.glob(f"{arm}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            out[r[key]["id"]] = r
    return out


one, five = load("claude"), load("claude-standard")
R1 = {i: r["decision"] == "REJECT" for i, r in one.items()}
R5 = {i: r["decision"] == "REJECT" for i, r in five.items()}


def votes(i):
    return {v["agent"]: v["vote"] == -1 for v in five[i]["votes"]}


nrej = {i: sum(votes(i).values()) for i in five}
nb = lambda i: num[i.rsplit(":", 1)[0]]
print("== 1. Relabel: clean originals with a defect Claude named (ORIG_DEFECT) count as defective ==")


def ba_rel(f):
    P, N = [], []
    for b in bases:
        P.append(f[f"{b}:planted"])
        if num[b] in ORIG_DEFECT:
            P.append(f[f"{b}:clean"])
        else:
            N.append(not f[f"{b}:clean"])
    return sum(P) / len(P), sum(N) / len(N), (sum(P) / len(P) + sum(N) / len(N)) / 2, len(P), len(N)


for name, f in (("one", R1), ("five", R5)):
    tp, tn, ba, nP, nN = ba_rel(f)
    print(f"  {name}: TPR {tp:.3f} (n {nP})  TNR {tn:.3f} (n {nN})  BA {ba:.4f}")
truth = {f"{b}:{k}": (k == "planted" or num[b] in ORIG_DEFECT) for b in bases for k in ("clean", "planted")}
o5 = [i for i in truth if R5[i] == truth[i] and R1[i] != truth[i]]
o1 = [i for i in truth if R1[i] == truth[i] and R5[i] != truth[i]]
print(f"  only five right {len(o5)} {sorted((nb(i), i[-7:]) for i in o5)}; only one right {len(o1)} {sorted((nb(i), i[-7:]) for i in o1)}")
k, n = min(len(o5), len(o1)), len(o5) + len(o1)
print(f"  exact McNemar p {min(1, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n):.3f}")

print("\n== 2. Error ledger: every panel error vs Claude alone's errors (scored as in score_five) ==")
err1 = {i for i in R1 if R1[i] != i.endswith(":planted")}
err5 = {i for i in R5 if R5[i] != i.endswith(":planted")}
lab = lambda s: sorted((nb(i), i.rsplit(":", 1)[1]) for i in s)
print(f"  Claude alone errors {len(err1)}, panel errors {len(err5)}, shared {len(err1 & err5)}")
print(f"  shared: {lab(err1 & err5)}")
print(f"  panel only: {lab(err5 - err1)}   one only: {lab(err1 - err5)}")

print("\n== 3. Panel REJECT-vote count as a graded score (RRRR early stop = 4) ==")
for t in range(1, 5):
    c = sum(nrej[f'{b}:planted'] >= t for b in bases)
    p = sum(nrej[f'{b}:clean'] < t for b in bases)
    print(f"  REJECT if >= {t} R votes: BA {(c + p) / 108:.4f}  caught {c}/54 passed {p}/54")
pos = [nrej[f'{b}:planted'] for b in bases]
neg = [nrej[f'{b}:clean'] for b in bases]
auc = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))
print(f"  AUC of R count {auc:.4f}; Claude alone (binary) AUC = its BA 0.8241")
print("  R count on clean, by Claude alone's verdict:")
for v in (True, False):
    h = [0] * 5
    for b in bases:
        if R1[f"{b}:clean"] == v:
            h[nrej[f'{b}:clean']] += 1
    print(f"    Claude alone {'REJECT' if v else 'APPROVE'}: R=0..4 {h}")

print("\n== 4. Is the seats' agreement within-item dependence or item difficulty? ==")
SEATS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED")


def fleiss(rows):
    n = len(rows[0]); N = len(rows)
    pj = sum(sum(r) for r in rows) / (N * n)
    Pi = [(sum(r) * (sum(r) - 1) + (n - sum(r)) * (n - sum(r) - 1)) / (n * (n - 1)) for r in rows]
    Pe = pj ** 2 + (1 - pj) ** 2
    return (sum(Pi) / N - Pe) / (1 - Pe)


def row(i):
    v = votes(i)
    return [int(v[s]) for s in SEATS]


clean = [f"{b}:clean" for b in bases]
print(f"  Fleiss kappa, 4 seats, all clean: {fleiss([row(i) for i in clean]):+.3f} (n {len(clean)})")
for v in (True, False):
    rows = [row(i) for i in clean if R1[i] == v]
    print(f"  ... within Claude alone {'REJECT' if v else 'APPROVE'} items: {fleiss(rows):+.3f} (n {len(rows)})")
raters = list(SEATS) + ["ONE"]
X = [row(i) + [int(R1[i])] for i in clean]


def lik(x, pi, th):
    return [math.prod(t if xi else 1 - t for t, xi in zip(th[c], x)) * (pi if c else 1 - pi) for c in (0, 1)]


rng = random.Random(1)
best = None
for start in range(20):
    pi = rng.uniform(0.1, 0.5)
    th = [[rng.uniform(0.0, 0.3) for _ in raters], [rng.uniform(0.5, 1.0) for _ in raters]]
    for _ in range(500):
        post = []
        for x in X:
            l = lik(x, pi, th)
            post.append(l[1] / (l[0] + l[1]))
        pi = sum(post) / len(X)
        for c in (0, 1):
            w = [p if c else 1 - p for p in post]
            th[c] = [min(1 - 1e-6, max(1e-6, sum(wi * x[j] for wi, x in zip(w, X)) / sum(w))) for j in range(len(raters))]
    ll = sum(math.log(sum(lik(x, pi, th))) for x in X)
    if best is None or ll > best[0]:
        best = (ll, pi, [r[:] for r in th])
ll, pi, th = best
print(f"  2-class conditional-independence fit (4 seats + Claude alone), clean items: share 'suspicious' {pi:.3f}, loglik {ll:.2f}")
for c in (0, 1):
    print(f"    class {c}: P(REJECT) " + " ".join(f"{r} {t:.2f}" for r, t in zip(raters, th[c])))
exp = [0.0] * 5
for x in product((0, 1), repeat=4):
    p = sum(math.prod(t if xi else 1 - t for t, xi in zip(th[c][:4], x)) * (pi if c else 1 - pi) for c in (0, 1))
    exp[sum(x)] += p * len(X)
obs = [0] * 5
for x in X:
    obs[sum(x[:4])] += 1
print(f"    4-seat R count 0..4 observed {obs}, under the fit {[round(e, 1) for e in exp]}")
q = [th[0][4], th[1][4]]
maj = lambda p: sum(math.comb(5, j) * p ** j * (1 - p) ** (5 - j) for j in range(3, 6))
print(f"    Claude alone REJECT rate by class {q[0]:.2f} / {q[1]:.2f}; majority of 5 iid samples -> "
      f"{maj(q[0]):.3f} / {maj(q[1]):.3f}; expected clean false alarms {len(X) * ((1 - pi) * maj(q[0]) + pi * maj(q[1])):.1f} "
      f"(one sample {len(X) * ((1 - pi) * q[0] + pi * q[1]):.1f}, panel observed {sum(R5[i] for i in clean)})")

print("\n== 5. Same comparison on 100 real gismo6 commits (four-arms), recomputed from records ==")
sel = [json.loads(l) for l in (EXP.parent / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
lab4 = {s["id"]: s["label"] == "REJECT" for s in sel}
a1, a5 = load("claude-one", FOUR, "four"), load("claude-standard", FOUR, "four")
ids = [i for i in lab4 if i in a1 and i in a5]
rj = lambda a, i: a[i]["decision"] == "REJECT"


def ba4(a):
    P = [rj(a, i) for i in ids if lab4[i]]
    N = [not rj(a, i) for i in ids if not lab4[i]]
    return sum(P) / len(P), sum(N) / len(N), (sum(P) / len(P) + sum(N) / len(N)) / 2


for name, a in (("one", a1), ("five", a5)):
    tp, tn, ba = ba4(a)
    print(f"  {name}: n {len(ids)}  REJECTs {sum(rj(a, i) for i in ids)}  TPR {tp:.3f} TNR {tn:.3f} BA {ba:.3f}")
d1 = [i for i in ids if rj(a5, i) == lab4[i] and rj(a1, i) != lab4[i]]
d2 = [i for i in ids if rj(a1, i) == lab4[i] and rj(a5, i) != lab4[i]]
print(f"  only five right {len(d1)}, only one right {len(d2)}")
sub = [i for i in ids if rj(a5, i)]
print(f"  panel REJECTs that Claude alone also rejected: {sum(rj(a1, i) for i in sub)}/{len(sub)}")

print("\n== 6. Single seats as one-call reviewers on the planted set (post hoc) ==")
for s in SEATS:
    c = sum(votes(f"{b}:planted")[s] for b in bases)
    p = sum(not votes(f"{b}:clean")[s] for b in bases)
    print(f"  {s:<13} BA {(c + p) / 108:.4f} caught {c}/54 passed {p}/54")
for name, a in (("four-arms seats", a5),):
    for s in SEATS:
        vs = {i: {v["agent"]: v["vote"] == -1 for v in a[i]["votes"]} for i in ids}
        P = [vs[i][s] for i in ids if lab4[i]]
        N = [not vs[i][s] for i in ids if not lab4[i]]
        print(f"  {name} {s:<13} BA {(sum(P) / len(P) + sum(N) / len(N)) / 2:.3f}  REJECTs {sum(vs[i][s] for i in ids)}")
