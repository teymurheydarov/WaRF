"""Question / target hints in Claude's reasons (all 352), and how much of each score is added-line count.
    python -B check2.py
"""
import json, re
from pathlib import Path
EXP = Path(__file__).resolve().parent.parent.parent
JEV, LAYA, CR = EXP / "jev-five", EXP / "laya-five", EXP / "laya-near-chance" / "claude-review"
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
def auc(s, y):
    P = [a for a, b in zip(s, y) if b]; N = [a for a, b in zip(s, y) if not b]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r
def spear(a, b):
    ra, rb = ranks(a), ranks(b); n = len(a); ma, mb = sum(ra) / n, sum(rb) / n
    c = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return c / (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5

items = {}
for bf in sorted((CR / "batches").glob("batch-*.txt")):
    for ch in open(bf, encoding="utf-8").read().split("<<<ITEM ")[1:]:
        iid = ch[:6]; items[iid] = ch[10:ch.rindex(f"\n<<<END {iid}>>>")]
key = {k["id"]: k for k in json.loads((CR / "key.json").read_text(encoding="utf-8"))}
res = json.loads((EXP / "laya-near-chance/laya-probe/claude_review_result.json").read_text(encoding="utf-8"))
rev = {it["id"]: it for b in res["reviews"] for it in b["items"]}

tgt = re.compile(r"(rather than fixed|later fix|fixed later|be fixed|follow-?up|blame|churn|rewritten|reverted|revisit|"
                 r"likely (to be )?(changed|touched|edited|reworked|replaced)|will be (changed|touched))", re.I)
hits = [i for i in key if tgt.search(rev[i]["reason"])]
print(f"352 reasons with target-like wording: {len(hits)}  (REJECT {sum(key[i]['label']=='REJECT' for i in hits)})")
for i in hits[:40]:
    print(f"  {i} [{key[i]['label']}] p={rev[i]['p_defect']}: {rev[i]['reason'][:140]}")

sel = jl(LAYA / "selection.jsonl"); ids = [s["id"] for s in sel]; y = [s["label"] == "REJECT" for s in sel]
add = lambda t: sum(1 for l in t.split("\n") if l.startswith("+") and not l.startswith("+++"))
A = [add(items[i]) for i in ids]
pc = [rev[i]["p_defect"] for i in ids]
one = {r["jev"]["id"]: r["jev"]["round1"]["JEV"]["p_reject"] for r in jl(JEV / "sessions_one.jsonl")}
pj = [one[i] for i in ids]
print(f"\n100: AUC added {auc(A, y):.3f} Claude {auc(pc, y):.3f} Jev-one {auc(pj, y):.3f}")
print(f"spearman with added lines: Claude {spear(pc, A):.3f}  Jev {spear(pj, A):.3f};  Claude vs Jev {spear(pc, pj):.3f}")
# within selection pairs (consecutive rows)
for name, s in (("Claude", pc), ("Jev", pj), ("added", A)):
    w = [(s[k] > s[k + 1]) + 0.5 * (s[k] == s[k + 1]) for k in range(0, 100, 2)]
    print(f"  {name}: REJECT ranked above its matched APPROVE in {sum(w)}/50 pairs")
# AUC restricted to comparisons where the two changes have similar added-line counts (ratio <= 1.5)
for name, s in (("Claude", pc), ("Jev", pj)):
    num = den = 0
    for a in range(100):
        for b in range(100):
            if y[a] and not y[b] and max(A[a], A[b]) <= 1.5 * max(1, min(A[a], A[b])):
                den += 1; num += (s[a] > s[b]) + 0.5 * (s[a] == s[b])
    print(f"  {name}: AUC over REJECT/APPROVE comparisons with added lines within 1.5x: {num/den:.3f} (n={den})")

# deletion-only changes: B-SZZ can never blame them, so they are APPROVE by construction
z = [k for k in range(100) if A[k] == 0]
print(f"\n100: zero-added-line items {len(z)}: labels {[sel[k]['label'] for k in z]}  Claude p {[pc[k] for k in z]}  Jev p {[pj[k] for k in z]}")
zall = [i for i in key if add(items[i]) == 0]
print(f"352: zero-added-line items {len(zall)}, REJECT {sum(key[i]['label']=='REJECT' for i in zall)}; Claude p mean "
      f"{sum(rev[i]['p_defect'] for i in zall)/max(1,len(zall)):.3f}")
hit100 = [k for k, i in enumerate(ids) if tgt.search(rev[i]["reason"])]
keep = [k for k in range(100) if k not in hit100]
print(f"100: target-worded reasons {len(hit100)}; Claude AUC without them {auc([pc[k] for k in keep],[y[k] for k in keep]):.3f}, "
      f"Jev on same subset {auc([pj[k] for k in keep],[y[k] for k in keep]):.3f}, added {auc([A[k] for k in keep],[y[k] for k in keep]):.3f} (n={len(keep)})")
keep = [k for k in range(100) if A[k] > 0]
print(f"100 without deletion-only: Claude {auc([pc[k] for k in keep],[y[k] for k in keep]):.3f}  Jev {auc([pj[k] for k in keep],[y[k] for k in keep]):.3f}  added {auc([A[k] for k in keep],[y[k] for k in keep]):.3f} (n={len(keep)})")
pj0 = [0.0 if A[k] == 0 else pj[k] for k in range(100)]
print(f"Jev with deletion-only items set to p=0 (the rule Claude applied): {auc(pj0, y):.3f}")
keep2 = [k for k in keep if k not in hit100]
print(f"without deletion-only and target-worded: Claude {auc([pc[k] for k in keep2],[y[k] for k in keep2]):.3f}  Jev {auc([pj[k] for k in keep2],[y[k] for k in keep2]):.3f}  added {auc([A[k] for k in keep2],[y[k] for k in keep2]):.3f} (n={len(keep2)})")
