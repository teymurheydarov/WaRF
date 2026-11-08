"""Parity light: are all +/- lines Claude saw present in the state Jev was sent (states.jsonl)?"""
import json, re
from pathlib import Path
HERE=Path(__file__).resolve().parent; EXP=HERE.parent.parent
items={}
for p in sorted((EXP/"laya-near-chance/claude-review/batches").glob("batch-*.txt")):
    for m in re.finditer(r"<<<ITEM (\w+)>>>\n(.*?)(?=<<<ITEM |\Z)",p.read_text(encoding="utf-8"),re.S): items[m.group(1)]=m.group(2)
st={json.loads(l)["id"]:json.loads(l) for l in open(EXP/"jev-five/verify/refute/states.jsonl",encoding="utf-8")}
sel=[json.loads(l) for l in open(EXP/"laya-five/selection.jsonl",encoding="utf-8")]
miss_items=0; tot_missing=0; cl_len=[]; jv_len=[]; ctx_c=[]; ctx_j=[]
for s in sel:
    c=items[s["id"]]; j=st[s["id"]]["state"]
    ch=[l for l in c.split("\n") if l[:1] in "+-" and not l.startswith(("+++","---"))]
    miss=[l for l in ch if l not in j]
    if miss: miss_items+=1; tot_missing+=len(miss)
    cl_len.append(len(c)); jv_len.append(len(j))
    ctx_c.append(sum(1 for l in c.split("\n") if l.startswith(" "))); ctx_j.append(sum(1 for l in j.split("\n") if l.startswith(" ")))
print("items where some changed line Claude saw is absent from Jev's state:",miss_items,"lines",tot_missing)
print("median chars Claude item",sorted(cl_len)[50],"Jev state",sorted(jv_len)[50])
print("median context lines Claude",sorted(ctx_c)[50],"Jev",sorted(ctx_j)[50])
