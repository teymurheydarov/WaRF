"""(1) Verdicts per REJECT class (R_cls) and per t18; (3) new Claude-one vs old p_claude."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
FA = HERE.parent.parent
EXP = FA.parent
V2 = json.loads((EXP / "something-wrong/verify-labels-metrics/v2_data.json").read_text(encoding="utf-8"))
R_cls, T18 = V2["R_cls"], set(V2["t18"])
sel = [json.loads(l) for l in (EXP / "laya-five/selection.jsonl").open(encoding="utf-8")]
S = {s["id"]: s for s in sel}
ARMS = ("claude-one", "claude-standard", "jev-one", "jev-standard")
recs = {}
for arm in ARMS:
    recs[arm] = {}
    for p in sorted(FA.glob(f"{arm}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[arm][r["four"]["id"]] = r


def group(i):
    if S[i]["label"] == "REJECT":
        return "R " + {"has-code": "code-blamed", "plumbing": "plumbing", "comment-only": "comment"}[R_cls[i]]
    return "A t18 (unblameable)" if i in T18 else "A other"


GROUPS = ["R code-blamed", "R plumbing", "R comment", "A other", "A t18 (unblameable)"]
score = {
    "claude-one": lambda i: float(recs["claude-one"][i]["decision"] == "REJECT"),
    "claude-standard": lambda i: sum(v["vote"] == -1 for v in recs["claude-standard"][i]["votes"]) / len(recs["claude-standard"][i]["votes"]),
    "jev-one": lambda i: recs["jev-one"][i]["four"]["round1"]["JEV"]["p_reject"],
    "jev-standard": lambda i: sum(a["p_reject"] for a in recs["jev-standard"][i]["four"]["round1"].values()) / len(recs["jev-standard"][i]["four"]["round1"]),
    "old p_claude": lambda i: S[i]["p_claude"],
    "old laya": lambda i: S[i]["p_single_laya"],
}
ids = [s["id"] for s in sel]
G = {g: [i for i in ids if group(i) == g] for g in GROUPS}
print("== (1) WaRF verdict REJECT count per group  |  mean ranking score per group")
print(f"  {'group':<22} {'n':>3}  " + "  ".join(f"{a:>15}" for a in ARMS))
for g in GROUPS:
    print(f"  {g:<22} {len(G[g]):>3}  " + "  ".join(
        f"{sum(recs[a][i]['decision']=='REJECT' for i in G[g]):>6} ({sum(score[a](i) for i in G[g])/len(G[g]):.2f}) " for a in ARMS)
        + f"   old p_claude mean {sum(score['old p_claude'](i) for i in G[g])/len(G[g]):.3f}")


def auc(sc, P, N):
    return sum((sc(p) > sc(n)) + 0.5 * (sc(p) == sc(n)) for p in P for n in N) / (len(P) * len(N))


def ba(arm, P, N):
    rj = lambda i: recs[arm][i]["decision"] == "REJECT"
    return (sum(rj(i) for i in P) / len(P) + sum(not rj(i) for i in N) / len(N)) / 2


print("\n== AUC (ranking score) / balanced accuracy (verdict), positives vs negatives")
pairs = [("code-blamed R vs A other", G["R code-blamed"], G["A other"]),
         ("code-blamed R vs all A", G["R code-blamed"], G["A other"] + G["A t18 (unblameable)"]),
         ("plumbing R vs A other", G["R plumbing"], G["A other"]),
         ("all R vs A other (=without 18)", G["R code-blamed"] + G["R plumbing"] + G["R comment"], G["A other"]),
         ("all R vs A t18", G["R code-blamed"] + G["R plumbing"] + G["R comment"], G["A t18 (unblameable)"]),
         ("A other vs A t18 (should be 0.5 if t18 irrelevant)", G["A other"], G["A t18 (unblameable)"])]
for name, P, N in pairs:
    print(f"  {name}  (P {len(P)}, N {len(N)})")
    print("    AUC " + "  ".join(f"{k} {auc(f, P, N):.3f}" for k, f in score.items()))
    print("    BA  " + "  ".join(f"{a} {ba(a, P, N):.3f}" for a in ARMS))

# (3) new Claude-one vs old p_claude
print("\n== (3) new claude-one verdict vs old p_claude (selection.jsonl)")
newR = {i: recs["claude-one"][i]["decision"] == "REJECT" for i in ids}
import statistics
for g in GROUPS:
    xs = [S[i]["p_claude"] for i in G[g]]
    print(f"  {g:<22} old p_claude median {statistics.median(xs):.2f}, >=0.5: {sum(x>=0.5 for x in xs):>2}/{len(xs)};"
          f" new REJECT {sum(newR[i] for i in G[g]):>2}/{len(xs)}")
oldR = {i: S[i]["p_claude"] >= 0.5 for i in ids}
agree = sum(oldR[i] == newR[i] for i in ids)
print(f"  old (p_claude>=0.5) vs new verdict agree on {agree}/100; old REJECTs {sum(oldR.values())}, new {sum(newR.values())}")
# AUC of new verdict within old-rank: does old p_claude predict the new verdict?
Pn = [i for i in ids if newR[i]]; Nn = [i for i in ids if not newR[i]]
print(f"  AUC of old p_claude for predicting the new verdict: {auc(lambda i: S[i]['p_claude'], Pn, Nn):.3f}")
Rall = [i for i in ids if S[i]["label"] == "REJECT"]; Aall = [i for i in ids if S[i]["label"] != "REJECT"]
Ao = G["A other"]; At = G["A t18 (unblameable)"]
for nm, f in (("old p_claude", score["old p_claude"]), ("new claude-one", score["claude-one"]),
              ("new claude-std share", score["claude-standard"]), ("jev-one", score["jev-one"])):
    a_all, a_o, a_t = auc(f, Rall, Aall), auc(f, Rall, Ao), auc(f, Rall, At)
    print(f"  {nm:<22} AUC all {a_all:.3f}  vs A other {a_o:.3f}  vs A t18 {a_t:.3f}")
print("  decomposition: AUC_all = (32*AUC_vs_other + 18*AUC_vs_t18)/50")
# disagreement lists
print("\n  disagreements (old>=0.5 vs new REJECT) by group:")
for g in GROUPS:
    d1 = [(i, S[i]["p_claude"]) for i in G[g] if oldR[i] and not newR[i]]
    d2 = [(i, S[i]["p_claude"]) for i in G[g] if not oldR[i] and newR[i]]
    print(f"  {g:<22} old R/new A {len(d1)} {d1}")
    print(f"  {'':<22} old A/new R {len(d2)} {d2}")
# per-id table for reading
rows = []
for i in ids:
    rows.append({"id": i, "group": group(i), "file": S[i]["file"], "commit": S[i]["commit"],
                 "p_claude": S[i]["p_claude"], **{a: recs[a][i]["decision"] for a in ARMS},
                 "jev_p": round(score["jev-one"](i), 3), "cstd_share": round(score["claude-standard"](i), 2)})
(HERE / "table.json").write_text(json.dumps(rows, indent=0), encoding="utf-8")
