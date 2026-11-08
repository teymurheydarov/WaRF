"""REJECTs vs the 15 auditor-trivial APPROVEs; mean on the other 35 APPROVEs."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
D=json.load(open(HERE/"v1_data.json",encoding="utf-8")); V2=json.load(open(HERE/"v2_data.json"))
sc,F,y,ids=D["scores"],D["F"],D["y"],D["ids"]
sc["added"]=F["added"]
def auc(score,pos):
    P=[s for s,t in zip(score,pos) if t];N=[s for s,t in zip(score,pos) if not t]
    return sum((p>q)+0.5*(p==q) for p in P for q in N)/(len(P)*len(N))
for setname,T in (("15",V2["t15"]),("18",V2["t18"])):
    keep=[j for j in range(100) if y[j] or ids[j] in T]
    for n in ("Claude","Jev one","Jev five R1 mean","Laya one","added"):
        oth=[sc[n][j] for j in range(100) if not y[j] and ids[j] not in T]
        print(f"set {setname} {n:<17} R vs trivial A AUC {auc([sc[n][j] for j in keep],[y[j] for j in keep]):.3f}   mean other A {sum(oth)/len(oth):.3f}")
