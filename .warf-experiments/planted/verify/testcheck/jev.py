import json
from pathlib import Path
OUT = Path(__file__).resolve().parent; H = OUT.parents[1]
items = [json.loads(l) for l in (H/"items.jsonl").open(encoding="utf-8")]
recs = {}
for s in ("jev","laya"):
    recs[s] = {}
    for p in H.glob(f"{s}.w*.jsonl"):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[s][r["planted"]["id"]] = r
pR = lambda s,i: recs[s][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"]
pl = [i for i in items if i["kind"]=="planted"]
ORIG_DEFECT = {5,7,26,31,36,39,52,53}
def added(code):
    patch = code.split("\n\n" + "─"*60)[0]
    return sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
def rank(xs):
    o = sorted(range(len(xs)), key=lambda k: xs[k]); r=[0]*len(xs); k=0
    while k < len(o):
        j=k
        while j+1<len(o) and xs[o[j+1]]==xs[o[k]]: j+=1
        for t in range(k,j+1): r[o[t]]=(k+j)/2
        k=j+1
    return r
def spear(a,b):
    ra, rb = rank(a), rank(b); n=len(a); ma=sum(ra)/n; mb=sum(rb)/n
    num=sum((x-ma)*(y-mb) for x,y in zip(ra,rb)); den=(sum((x-ma)**2 for x in ra)*sum((y-mb)**2 for y in rb))**.5
    return num/den
cl = [p["id"].replace(":planted",":clean") for p in pl]
jc = [pR("jev",i) for i in cl]; jp = [pR("jev",p["id"]) for p in pl]
lc = [pR("laya",i) for i in cl]; lp = [pR("laya",p["id"]) for p in pl]
add = [added(p["code"]) for p in pl]
chars = [len(p["code"]) for p in pl]
print("Jev clean pR: mean %.3f median %.3f; >=0.5: %d/54" % (sum(jc)/54, sorted(jc)[27], sum(x>=0.5 for x in jc)))
print("Jev planted pR: mean %.3f; min %.2f" % (sum(jp)/54, min(jp)))
print("Jev pairs planted>clean %d, equal %d, lower %d" % (sum(a>b for a,b in zip(jp,jc)), sum(a==b for a,b in zip(jp,jc)), sum(a<b for a,b in zip(jp,jc))))
print("Jev mean shift planted-clean %.3f" % (sum(a-b for a,b in zip(jp,jc))/54))
print("Spearman Jev clean pR vs added lines %.3f, vs chars %.3f" % (spear(jc,add), spear(jc,chars)))
d = [n+1 for n in range(54) if n+1 in ORIG_DEFECT]
print("Jev clean pR on verified-defect originals:", {n: jc[n-1] for n in sorted(ORIG_DEFECT)}, "mean %.3f vs others %.3f" % (sum(jc[n-1] for n in ORIG_DEFECT)/len(ORIG_DEFECT), sum(jc[k] for k in range(54) if k+1 not in ORIG_DEFECT)/(54-len(ORIG_DEFECT))))
print("Laya pairs planted>clean %d equal %d lower %d; mean |diff| %.4f" % (sum(a>b for a,b in zip(lp,lc)), sum(a==b for a,b in zip(lp,lc)), sum(a<b for a,b in zip(lp,lc)), sum(abs(a-b) for a,b in zip(lp,lc))/54))
# operator class vs Jev shift
ops = {}
for p,a,b in zip(pl,jp,jc): ops.setdefault(p["operator"],[]).append(round(a-b,2))
print("Jev shift by operator:", ops)
