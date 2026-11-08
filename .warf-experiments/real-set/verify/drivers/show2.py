import sys, re
from load import *
clean = [it["id"] for it in items if it["kind"]=="clean"]
fa = [i for i in clean if rej("claude", i)]
a,b = int(sys.argv[1]), int(sys.argv[2])
for n,i in enumerate(fa[a:b], a):
    it = by_id[i]
    print(f"######## [{n}] {i} {it['file']} {it['commit']}")
    lines = it["code"].split("\n")
    cut = next((k for k,l in enumerate(lines) if l.startswith("# Full function context")), len(lines))
    lines = lines[:cut]
    keep = set()
    for k,l in enumerate(lines):
        if (l.startswith("+") or l.startswith("-") or l.startswith("@@")):
            keep.update(range(max(0,k-4), min(len(lines),k+5)))
    print("\n".join(lines[k] for k in sorted(keep)))
    print("=== CLAUDE REPLY ===")
    print(reply("claude", i))
