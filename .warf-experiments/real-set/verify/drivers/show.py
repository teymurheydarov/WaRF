import sys
from load import *
clean = [it["id"] for it in items if it["kind"]=="clean"]
fa = [i for i in clean if rej("claude", i)]
a,b = int(sys.argv[1]), int(sys.argv[2])
for n,i in enumerate(fa[a:b], a):
    it = by_id[i]
    print(f"######## [{n}] {i} {it['file']} {it['commit']}")
    print(it["code"])
    if it.get("context"): print("--- CONTEXT ---\n"+str(it["context"])[:3000])
    print("=== CLAUDE REPLY ===")
    print(reply("claude", i))
