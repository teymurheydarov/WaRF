"""Re-derive replay.py's single-seat OOF AUCs with my own MAP-Platt fit (no warf import), check rounding."""
import json, math, random
from pathlib import Path
HERE=Path(__file__).resolve().parent; EXP=HERE.parent.parent
OUT=open(HERE/"v5.log","w",encoding="utf-8")
def say(*a):
    s=" ".join(str(x) for x in a); print(s); OUT.write(s+"\n")
sel=[json.loads(l) for l in open(EXP/"laya-five/selection.jsonl",encoding="utf-8")]
one={json.loads(l)["jev"]["id"]:json.loads(l)["jev"]["round1"]["JEV"]["p_reject"] for l in open(EXP/"jev-five/sessions_one.jsonl",encoding="utf-8")}
ids=[s["id"] for s in sel]; y={s["id"]:(-1 if s["label"]=="REJECT" else 1) for s in sel}
P={"Jev":{i:one[i] for i in ids},"Laya":{s["id"]:s["p_single_laya"] for s in sel},"Claude":{s["id"]:s["p_claude"] for s in sel}}
def auc(score,pos):
    Pp=[s for s,t in zip(score,pos) if t];N=[s for s,t in zip(score,pos) if not t]
    return sum((p>q)+0.5*(p==q) for p in Pp for q in N)/(len(Pp)*len(N))
clamp=lambda p:min(0.99,max(0.01,round(p,2)))
pos=[y[i]==-1 for i in ids]
for n,d in P.items():
    say(f"{n:<7} raw {auc([d[i] for i in ids],pos):.4f}  rounded+clamped {auc([clamp(d[i]) for i in ids],pos):.4f}  distinct raw {len(set(d.values()))} rounded {len({clamp(v) for v in d.values()})}")
# folds exactly as replay.py
rng=random.Random(11); folds={}
for label in (1,-1):
    m=[i for i in ids if y[i]==label]; rng.shuffle(m)
    for k,i in enumerate(m): folds[i]=k%5
def sig(x): return 1/(1+math.exp(-x)) if x>=0 else math.exp(x)/(1+math.exp(x))
def fit(rs,ys):
    # MAP: a~N(0,1), b~N(1,1); plain gradient ascent with backtracking, many iterations
    def lp(a,b):
        t=-0.5*a*a-0.5*(b-1)**2
        for r,yy in zip(rs,ys):
            z=a+b*r; s=z if yy==1 else -z
            t+= -math.log1p(math.exp(-s)) if s>=0 else s-math.log1p(math.exp(s))
        return t
    a,b=0.0,1.0; cur=lp(a,b); lr=0.05
    for _ in range(20000):
        ga=-a; gb=-(b-1)
        for r,yy in zip(rs,ys):
            p=sig(a+b*r); t=1.0 if yy==1 else 0.0; ga+=t-p; gb+=(t-p)*r
        na,nb=a+lr*ga,b+lr*gb; c=lp(na,nb)
        if c>=cur: a,b,cur=na,nb,c; lr*=1.1
        else: lr*=0.5
        if abs(ga)+abs(gb)<1e-9: break
    nc=sum(1 for v in ys if v==1)
    return a,b,math.log(((nc+1)/(len(ys)+2))/(1-(nc+1)/(len(ys)+2)))
for n,d in P.items():
    ev={}; fits=[]
    for k in range(5):
        tr=[i for i in ids if folds[i]!=k]
        rs=[math.log((1-clamp(d[i]))/clamp(d[i])) for i in tr]
        a,b,pr=fit(rs,[y[i] for i in tr]); fits.append((round(a,3),round(b,3)))
        for i in ids:
            if folds[i]==k:
                r=math.log((1-clamp(d[i]))/clamp(d[i])); ev[i]=a+b*r-pr
    oof=auc([-ev[i] for i in ids],pos)
    perfold=[auc([clamp(d[i]) for i in ids if folds[i]==k],[pos[j] for j,i in enumerate(ids) if folds[i]==k]) for k in range(5)]
    say(f"{n:<7} OOF AUC {oof:.4f}  mean per-fold AUC {sum(perfold)/5:.4f}  fits (a,b) {fits}")
