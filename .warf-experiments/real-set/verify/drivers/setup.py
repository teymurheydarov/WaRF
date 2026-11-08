import json, re, statistics as st
from load import *
from verdicts import V
ids = [it["id"] for it in items]; D = {i: by_id[i]["kind"]=="defective" for i in ids}
ARMS = ["claude","claude-strict","claude-advocate","claude-standard","jev"]
print("reject counts:", {a: sum(rej(a,i) for i in ids) for a in ARMS})
# size confound
def nadd(i): return sum(1 for l in by_id[i]["code"].split("\n") if l.startswith("+") and not l.startswith("+++"))
for f, name in ((lambda i: len(by_id[i]["code"]), "chars"), (nadd, "added lines")):
    P = [f(i) for i in ids if D[i]]; N = [f(i) for i in ids if not D[i]]
    auc = sum((p>n)+0.5*(p==n) for p in P for n in N)/(len(P)*len(N))
    print(f"{name}: median defective {st.median(P)}, clean {st.median(N)}, AUC(size->defective) {auc:.3f}")
# by period
def ba(a, S):
    P=[i for i in S if D[i]]; N=[i for i in S if not D[i]]
    return (sum(rej(a,i) for i in P)/len(P)+sum(not rej(a,i) for i in N)/len(N))/2, f"{sum(rej(a,i) for i in P)}/{len(P)}", f"{sum(rej(a,i) for i in N)}/{len(N)}"
for lo, hi in (("2014","2019"),("2020","2023"),("2024","2026")):
    S=[i for i in ids if lo<=by_id[i]["date"][:4]<=hi]
    print(lo,hi, {a: (round(ba(a,S)[0],3), ba(a,S)[1], ba(a,S)[2]) for a in ARMS})
# false alarm verdicts by year
for v in ("REAL","PRE","DEB","FALSE"):
    print(v, sorted(by_id[i]["date"][:4] for i in V if V[i]==v))
# memory phrases
pat = re.compile(r"as far as I (know|recall)|as I recall|from memory|I recall|I remember|later (fixed|commit)|upstream|in G\+Smo's history|was fixed in", re.I)
for a in ARMS[:3]:
    hits=[i for i in ids if pat.search(reply(a,i))]
    print(a, "memory-phrase replies:", len(hits), "defective", sum(D[i] for i in hits), "| REJECT among them", sum(rej(a,i) for i in hits))
hits=[i for i in ids if pat.search(reply("claude",i))]
for i in hits: print("  ", i, by_id[i]["date"], "REJ" if rej("claude",i) else "app", pat.search(reply("claude",i)).group(0))
