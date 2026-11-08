"""Do Claude's batch items carry the file of the key entry with the same id? Is any label text leaked into batches?"""
import json, re
from pathlib import Path
HERE=Path(__file__).resolve().parent; EXP=HERE.parent.parent
key={k["id"]:k for k in json.load(open(EXP/"laya-near-chance/claude-review/key.json",encoding="utf-8"))}
items={}
for p in sorted((EXP/"laya-near-chance/claude-review/batches").glob("batch-*.txt")):
    t=p.read_text(encoding="utf-8")
    for m in re.finditer(r"<<<ITEM (\w+)>>>\n(.*?)(?=<<<ITEM |\Z)",t,re.S):
        items[m.group(1)]=(p.name,m.group(2))
ok=bad=0
for i,k in key.items():
    if i not in items: bad+=1; print("missing",i); continue
    body=items[i][1]
    if ("b/"+k["file"]) in body or ("a/"+k["file"]) in body: ok+=1
    else: bad+=1; print("file not in item",i,k["file"])
print("items",len(items),"file match",ok,"bad",bad)
leak=[i for i,(f,b) in items.items() if re.search(r"\b(REJECT|APPROVE|later fixed|never fixed)\b",b)]
print("items mentioning REJECT/APPROVE/fixed-labels words:",len(leak),leak[:10])
sel=[json.loads(l) for l in open(EXP/"laya-five/selection.jsonl",encoding="utf-8")]
print("batch of the 100:",sorted({items[s['id']][0] for s in sel}))
