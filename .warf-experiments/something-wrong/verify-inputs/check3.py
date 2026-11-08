"""Deletion-only items: confirm they are pure deletions; effect of the 'no added line -> APPROVE' rule on the other Jev arms.
    python -B check3.py
"""
import json
from pathlib import Path
EXP = Path(__file__).resolve().parent.parent.parent
JEV, LAYA, CR = EXP / "jev-five", EXP / "laya-five", EXP / "laya-near-chance" / "claude-review"
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
def auc(s, y):
    P = [a for a, b in zip(s, y) if b]; N = [a for a, b in zip(s, y) if not b]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
items = {}
for bf in sorted((CR / "batches").glob("batch-*.txt")):
    for ch in open(bf, encoding="utf-8").read().split("<<<ITEM ")[1:]:
        iid = ch[:6]; items[iid] = ch[10:ch.rindex(f"\n<<<END {iid}>>>")]
sel = jl(LAYA / "selection.jsonl"); ids = [s["id"] for s in sel]; y = [s["label"] == "REJECT" for s in sel]
cnt = lambda t, c: sum(1 for l in t.split("\n") if l.startswith(c) and not l.startswith(c * 3))
for s in sel:
    t = items[s["id"]]
    if cnt(t, "+") == 0:
        print(f"  {s['id']} {s['label']} {s['file']}: +{cnt(t,'+')} -{cnt(t,'-')}  new/deleted file: {'deleted file mode' in t}")
dele = {i for i in ids if cnt(items[i], "+") == 0}
for arm in ("five", "standard"):
    rows = {r["jev"]["id"]: r["jev"] for r in jl(JEV / f"sessions_{arm}.jsonl")}
    m1 = [sum(v["p_reject"] for v in rows[i]["round1"].values()) / len(rows[i]["round1"]) for i in ids]
    out = f"{arm}: mean Round-1 p_reject AUC {auc(m1, y):.3f} -> with deletion rule {auc([0 if i in dele else v for i, v in zip(ids, m1)], y):.3f}"
    if arm == "five":
        m2 = [sum(v["p_reject"] for v in rows[i]["round2"].values()) / len(rows[i]["round2"]) if rows[i]["round2"] else None for i in ids]
        ok = [k for k in range(100) if m2[k] is not None]
        out += f"; Round-2 mean (n={len(ok)}) {auc([m2[k] for k in ok], [y[k] for k in ok]):.3f} -> {auc([0 if ids[k] in dele else m2[k] for k in ok], [y[k] for k in ok]):.3f}"
    print(out)
