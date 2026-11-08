"""Arm verdicts on a hand classification of the 50 later-fixed changes (from git show of each change's
diff and of its first fix(es); see breakdown.log / show.py). Classification is by this verifier, not blinded
to Claude's replies."""
import json, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
rows = {r["id"]: r for r in json.loads((HERE / "table.json").read_text(encoding="utf-8"))}
C = {
 "visible defect, fix addresses it": "5f8ecf b89217 7db77f 2a162c 6d18ae 482f99 d05ce2 2140a8 ebcf2a c79f8b 88cb75 fad955 d9b330 920dfd f38d3a".split(),
 "visible doc slip, fix addresses it": "b1f90f 4b41ad".split(),
 "arguable": "6017c0 da06b6 616e66 a314c7".split(),
 "real defect, not visible in this diff": "7d18e0 a3d51f c518a5 60f802 46d7d2 cc497b 6c5281".split(),
 "no defect introduced (refactor, later change, comment/author edit)":
   "515d5f 03e58b b2330f 5201b9 7f37bf ebe5b3 09b5b3 bb047a d983e9 7cac17 39f2ad c1b11a 16af02 ff66f7 ee60aa 19767a 451246 0c0789 894df0 e001c7 b4f8a3 c2f1b9".split(),
}
allR = [i for i, r in rows.items() if r["group"].startswith("R")]
assert sorted(sum(C.values(), [])) == sorted(allR), (len(sum(C.values(), [])), set(allR) - set(sum(C.values(), [])))
Aother = [i for i, r in rows.items() if r["group"] == "A other"]
At18 = [i for i, r in rows.items() if r["group"].startswith("A t18")]
ARMS = ("claude-one", "claude-standard", "jev-one", "jev-standard")
print(f"{'class':<68} n  " + "  ".join(f"{a:>15}" for a in ARMS) + "   jev p  old p_claude")
def line(name, ids):
    print(f"{name:<68} {len(ids):>2} " + "  ".join(f"{sum(rows[i][a]=='REJECT' for i in ids):>6} ({sum(rows[i][a]=='REJECT' for i in ids)/len(ids):.2f})" for a in ARMS)
          + f"   {sum(rows[i]['jev_p'] for i in ids)/len(ids):.2f}   {sum(rows[i]['p_claude'] for i in ids)/len(ids):.2f}")
for k, v in C.items(): line(k, v)
line("never fixed, other", Aother); line("never fixed, t18", At18)

V = C["visible defect, fix addresses it"] + C["visible doc slip, fix addresses it"]
def auc(sc, P, N): return sum((sc(p) > sc(n)) + 0.5 * (sc(p) == sc(n)) for p in P for n in N) / (len(P) * len(N))
sc = {"claude-one": lambda i: float(rows[i]["claude-one"] == "REJECT"), "claude-std share": lambda i: rows[i]["cstd_share"],
      "jev-one p": lambda i: rows[i]["jev_p"], "old p_claude": lambda i: rows[i]["p_claude"]}
rng = random.Random(7)
print(f"\nvisible-defect set V ({len(V)}) vs never-fixed: AUC [95% bootstrap]")
for N, nn in ((Aother, "A other"), (Aother + At18, "all A")):
    for k, f in sc.items():
        xs = sorted(auc(f, [rng.choice(V) for _ in V], [rng.choice(N) for _ in N]) for _ in range(1000))
        print(f"  vs {nn:<8} {k:<17} {auc(f, V, N):.3f} [{xs[24]:.3f}, {xs[974]:.3f}]")
ND = C["no defect introduced (refactor, later change, comment/author edit)"]
print(f"\n'no defect introduced' later-fixed ({len(ND)}) vs A other: " + "  ".join(f"{k} {auc(f, ND, Aother):.3f}" for k, f in sc.items()))
print(f"V vs 'no defect introduced' later-fixed: " + "  ".join(f"{k} {auc(f, V, ND):.3f}" for k, f in sc.items()))
