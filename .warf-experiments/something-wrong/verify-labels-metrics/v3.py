"""The 18 unblameable APPROVEs item by item; bootstrap of Claude-Jev on the 82 and 76."""
import json, random, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = open(HERE / "v3.log", "w", encoding="utf-8")
def say(*a):
    s=" ".join(str(x) for x in a); print(s); OUT.write(s+"\n")
D=json.load(open(HERE/"v1_data.json",encoding="utf-8")); V2=json.load(open(HERE/"v2_data.json"))
sc,F,y,ids=D["scores"],D["F"],D["y"],D["ids"]
FJ={json.loads(l)["id"]:json.loads(l) for l in open(HERE.parent.parent/"jev-five/verify/refute/features.jsonl",encoding="utf-8")}
say("id      added noncosm comment_only status         Claude  Jev1  Jev5")
for i in V2["t18"]:
    j=ids.index(i); f=FJ[i]
    say(f"{i}  {F['added'][j]:>5} {F['added_noncosmetic'][j]:>6} {str(f['comment_only']):>12} {f['status']:<14} {sc['Claude'][j]:.2f}  {sc['Jev one'][j]:.2f}  {sc['Jev five R1 mean'][j]:.2f}  {'*' if i not in V2['t15'] else ''}")
GD=r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"
sel={json.loads(l)["id"]:json.loads(l) for l in open(HERE.parent.parent/"laya-five/selection.jsonl",encoding="utf-8")}
for i in V2["t18"]:
    if i in V2["t15"]: continue
    s=sel[i]
    d=subprocess.run(["git","--git-dir",GD,"show","-M","-U0","--format=",s["commit"]],capture_output=True).stdout.decode("utf-8","replace")
    blk=[b for b in d.split("diff --git ") if (" b/"+s["file"]) in b.split("\n",1)[0]]
    say("----",i,s["file"]); say("\n".join(l for l in blk[0].split("\n") if l[:1] in "+-@" )[:900])
def auc(score,pos):
    P=[s for s,t in zip(score,pos) if t];N=[s for s,t in zip(score,pos) if not t]
    return sum((p>q)+0.5*(p==q) for p in P for q in N)/(len(P)*len(N))
def boot(a,b,pos,n=4000,seed=23):
    P=[i for i,t in enumerate(pos) if t];N=[i for i,t in enumerate(pos) if not t];r=random.Random(seed);d=[]
    for _ in range(n):
        ix=[r.choice(P) for _ in P]+[r.choice(N) for _ in N];yy=[pos[i] for i in ix]
        d.append(auc([a[i] for i in ix],yy)-auc([b[i] for i in ix],yy))
    d.sort();return auc(a,pos)-auc(b,pos),d[int(.025*n)],d[int(.975*n)-1]
R=V2["R_cls"]
for title,keep in (("all 100",list(range(100))),("drop 15",[j for j in range(100) if ids[j] not in V2["t15"]]),
                   ("drop 18",[j for j in range(100) if ids[j] not in V2["t18"]]),
                   ("drop 18 + comment R",[j for j in range(100) if ids[j] not in V2["t18"] and R.get(ids[j])!="comment-only"])):
    yk=[y[j] for j in keep]
    for b in ("Jev one","Jev five R1 mean"):
        d,lo,hi=boot([sc["Claude"][j] for j in keep],[sc[b][j] for j in keep],yk)
        say(f"{title:<22} Claude - {b:<17} {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
