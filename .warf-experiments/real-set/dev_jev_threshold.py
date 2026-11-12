import json,glob,re
items={json.loads(l)["id"]:json.loads(l) for l in open("items.jsonl",encoding="utf-8")}
p={}
for f in glob.glob("jev.w*.jsonl"):
    for l in open(f,encoding="utf-8"):
        r=json.loads(l); v=r["votes"][0]
        m=re.search(r"p\(REJECT\)=([0-9.]+)",v["reasoning"]); p[r["planted"]["id"]]=float(m.group(1))
ids=list(items); D={i:items[i]["kind"]=="defective" for i in ids}
pos=[p[i] for i in ids if D[i]]; neg=[p[i] for i in ids if not D[i]]
auc=sum((a>b)+0.5*(a==b) for a in pos for b in neg)/len(pos)/len(neg)
print("n",len(p),"AUC %.3f"%auc)
def ba(t,s): 
    P=[i for i in s if D[i]];N=[i for i in s if not D[i]]
    return (sum(p[i]>=t for i in P)/len(P)+sum(p[i]<t for i in N)/len(N))/2
ts=sorted(set(p.values()))
print("BA at 0.5: %.3f"%ba(0.5,ids), " best in-sample: %.3f"%max(ba(t,ids) for t in ts))
loo=0
for i in ids:
    rest=[j for j in ids if j!=i]; t=max(ts,key=lambda t:ba(t,rest))
    loo+= (p[i]>=t)==D[i] if False else 0
pr={}
for i in ids:
    rest=[j for j in ids if j!=i]; t=max(ts,key=lambda t:ba(t,rest)); pr[i]=p[i]>=t
P=[i for i in ids if D[i]];N=[i for i in ids if not D[i]]
print("LOO-threshold BA: %.3f"%((sum(pr[i] for i in P)/66+sum(not pr[i] for i in N)/66)/2))
import statistics
print("median p defective %.2f clean %.2f"%(statistics.median(pos),statistics.median(neg)))
L=[len(items[i]["code"]) for i in ids]; print("input chars median",statistics.median(L),"max",max(L))
def added(c): return sum(1 for ln in c.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
A={i:added(items[i]["code"]) for i in ids}
pa=[A[i] for i in ids if D[i]]; na=[A[i] for i in ids if not D[i]]
print("added-lines AUC %.3f"%(sum((a>b)+0.5*(a==b) for a in pa for b in na)/len(pa)/len(na)))
# Jev within added-line terciles
import bisect
qs=sorted(A.values()); cut=[qs[len(qs)//3],qs[2*len(qs)//3]]
for lo,hi in [(-1,cut[0]),(cut[0],cut[1]),(cut[1],10**9)]:
    s=[i for i in ids if lo<A[i]<=hi]; P_=[p[i] for i in s if D[i]]; N_=[p[i] for i in s if not D[i]]
    if P_ and N_: print("bin",lo,hi,len(P_),len(N_),"Jev AUC %.3f"%(sum((a>b)+0.5*(a==b) for a in P_ for b in N_)/len(P_)/len(N_)))
