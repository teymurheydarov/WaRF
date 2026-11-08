"""Batch effects in Claude's scores (352) and the size matching of the 100.
    python -B check4.py
"""
import json, statistics
from pathlib import Path
EXP = Path(__file__).resolve().parent.parent.parent
CR = EXP / "laya-near-chance" / "claude-review"
def auc(s, y):
    P = [a for a, b in zip(s, y) if b]; N = [a for a, b in zip(s, y) if not b]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
key = {k["id"]: k for k in json.loads((CR / "key.json").read_text(encoding="utf-8"))}
res = json.loads((EXP / "laya-near-chance/laya-probe/claude_review_result.json").read_text(encoding="utf-8"))
pc = {it["id"]: it["p_defect"] for b in res["reviews"] for it in b["items"]}
per = []
for b in range(1, 9):
    ids = [i for i in key if key[i]["batch"] == b]
    a = auc([pc[i] for i in ids], [key[i]["label"] == "REJECT" for i in ids]); per.append(a)
    print(f"batch {b}: AUC {a:.3f} mean p {statistics.mean(pc[i] for i in ids):.3f}")
print(f"mean within-batch AUC {statistics.mean(per):.3f}; pooled {auc([pc[i] for i in key], [key[i]['label']=='REJECT' for i in key]):.3f}")
# pooled after per-batch rank normalisation
z = {}
for b in range(1, 9):
    ids = sorted((i for i in key if key[i]["batch"] == b), key=lambda i: pc[i])
    for r, i in enumerate(ids): z[i] = r / len(ids)
print(f"pooled AUC of within-batch ranks {auc([z[i] for i in key], [key[i]['label']=='REJECT' for i in key]):.3f}")
sel = [json.loads(l) for l in open(EXP / "laya-five/selection.jsonl", encoding="utf-8")]
y = [s["label"] == "REJECT" for s in sel]
print(f"100: AUC patch_chars {auc([s['patch_chars'] for s in sel], y):.3f}  state_tokens {auc([s['state_tokens'] for s in sel], y):.3f}")
