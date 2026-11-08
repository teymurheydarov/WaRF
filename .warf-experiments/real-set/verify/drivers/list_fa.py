from load import *
clean = [it["id"] for it in items if it["kind"]=="clean"]
fa = [i for i in clean if rej("claude", i)]
print(len(fa))
for i in fa:
    it = by_id[i]
    print(i, it["date"], it["commit"][:10], len(it["code"]), "strict",rej("claude-strict",i),"adv",rej("claude-advocate",i),"W1",rej("claude-standard",i),"jev",rej("jev",i))
print(sorted(by_id[clean[0]].keys()))
