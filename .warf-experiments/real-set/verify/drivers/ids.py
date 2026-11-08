from load import *
clean = [it["id"] for it in items if it["kind"]=="clean"]
fa = [i for i in clean if rej("claude", i)]
for n,i in enumerate(fa): print(n, by_id[i]["commit"], by_id[i]["file"])
