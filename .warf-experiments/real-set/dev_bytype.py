import json,glob,collections,math
items={}
for l in open("items.jsonl",encoding="utf-8"):
    d=json.loads(l); items[d["id"]]=d
def typ(it):
    p=it["file"].split("/")
    return p[1] if p[0]=="src" and len(p)>2 else p[0]
arms=sorted({f.rsplit(".w",1)[0] for f in glob.glob("*.w*.jsonl")}-{"claude-verify","claude-verify-tools"})
V={}
for a in arms:
    for f in glob.glob(a+".w*.jsonl"):
        for l in open(f,encoding="utf-8"):
            r=json.loads(l)
            for v in r["votes"]:
                V.setdefault(a+":"+v["agent"],{})[r["planted"]["id"]]=v["label"]=="REJECT"
R={k:v for k,v in V.items() if len(v)==len(items)}
print(len(R),"reviewers:",", ".join(sorted(R)))
ids=list(items); D={i:items[i]["kind"]=="defective" for i in ids}
T={i:typ(items[i]) for i in ids}
print(sorted(collections.Counter(T.values()).items(),key=lambda x:-x[1]))
def ba(pred,s):
    pos=[i for i in s if D[i]]; neg=[i for i in s if not D[i]]
    if not pos or not neg: return sum(pred[i]==D[i] for i in s)/len(s)
    return (sum(pred[i] for i in pos)/len(pos)+sum(not pred[i] for i in neg)/len(neg))/2
best=sorted(((ba(R[k],ids),k) for k in R),reverse=True)[:5]
print("best single (in-sample):",[(k,round(b,3)) for b,k in best])
# LOO: global choice vs per-type choice
def choose(pool):
    return max(R,key=lambda k:(ba(R[k],pool),k))
glob_pred={}; type_pred={}; nb_pred={}
for i in ids:
    rest=[j for j in ids if j!=i]
    g=choose(rest); glob_pred[i]=R[g][i]
    same=[j for j in rest if T[j]==T[i]]
    k=choose(same) if len(same)>=8 and any(D[j] for j in same) and any(not D[j] for j in same) else g
    type_pred[i]=R[k][i]
    # naive Bayes, per-type rates shrunk to global rates (pseudo 4)
    lo=0
    for r in R:
        def rates(s):
            tp=sum(R[r][j] for j in s if D[j]); P=sum(D[j] for j in s)
            fp=sum(R[r][j] for j in s if not D[j]); N=len(s)-P
            return tp,P,fp,N
        gtp,gP,gfp,gN=rates(rest); ttp,tP,tfp,tN=rates(same)
        m=4
        sens=(ttp+m*(gtp+1)/(gP+2))/(tP+m); fpr=(tfp+m*(gfp+1)/(gN+2))/(tN+m)
        lo+= math.log(sens/fpr) if R[r][i] else math.log((1-sens)/(1-fpr))
    nb_pred[i]=lo>0
print("LOO global best-single: %.3f"%ba(glob_pred,ids))
print("LOO per-type best-single: %.3f"%ba(type_pred,ids))
print("LOO per-type naive-Bayes pool (all reviewers): %.3f"%ba(nb_pred,ids))
low=R["claude-commit-strict-tools@low:"+[v for v in [k.split(":")[1] for k in R if k.startswith("claude-commit-strict-tools@low:")]][0]]
print("fixed S-low: %.3f"%ba(low,ids))
# how different are per-type winners?
for t,c in collections.Counter(T.values()).most_common(6):
    s=[i for i in ids if T[i]==t]
    top=sorted(((ba(R[k],s),k) for k in R),reverse=True)[:2]
    print(t,c,[(k,round(b,2)) for b,k in top])
