"""Blamed-line classes for all gismo6 REJECTs of the 352-item Claude sample; Claude AUC there."""
import json, re, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent; EXP=HERE.parent.parent
src=open(HERE/"v2.py",encoding="utf-8").read()
ns={"__file__": str(HERE/"v2.py")}
exec(src.split('say("== REJECTs of the 100')[0].replace('OUT = open(HERE / "v2.log", "w", encoding="utf-8")','OUT = open(HERE / "v4.log", "w", encoding="utf-8")'), ns)
say=ns["say"]; blamed_classes=ns["blamed_classes"]; summary=ns["summary"]; auc=ns["auc"]
key=json.load(open(EXP/"laya-near-chance/claude-review/key.json",encoding="utf-8"))
kd={(k["commit"],k["file"]):k for k in key if "gismo6" in k["repo"]}
rows={}
for line in open(EXP/"laya-sweep/labels.jsonl",encoding="utf-8"):
    if "gismo6" not in line: continue
    r=json.loads(line)
    if (r["commit"],r["file"]) in kd: rows[(r["commit"],r["file"])]=r
res=json.load(open(EXP/"laya-near-chance/laya-probe/claude_review_result.json",encoding="utf-8"))
cl={it["id"]:it["p_defect"] for b in res["reviews"] for it in b["items"]}
cnt={}; cls_of={}
for k,kk in kd.items():
    if kk["label"]!="REJECT": continue
    c,err=blamed_classes(rows[k],k[0])
    s=summary(c) if c else "ERR"; cls_of[kk["id"]]=s; cnt[s]=cnt.get(s,0)+1
say("gismo6 key items",len(kd),"REJECT",sum(v["label"]=="REJECT" for v in kd.values()),"classes",cnt)
items=list(kd.values()); yy=[k["label"]=="REJECT" for k in items]
say("Claude AUC gismo6 subset of key", round(auc([cl[k["id"]] for k in items],yy),3))
say("Claude AUC full key (352)", round(auc([cl[k["id"]] for k in key],[k["label"]=="REJECT" for k in key]),3))
sel_ids={json.loads(l)["id"] for l in open(EXP/"laya-five/selection.jsonl",encoding="utf-8")}
rest=[k for k in items if k["id"] not in sel_ids]
say("Claude AUC on gismo6 key items NOT in the 100:",len(rest),round(auc([cl[k["id"]] for k in rest],[k["label"]=="REJECT" for k in rest]),3))
