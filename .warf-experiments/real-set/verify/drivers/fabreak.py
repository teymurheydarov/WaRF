from collections import Counter
from load import *
from verdicts import V
C = [it["id"] for it in items if it["kind"]=="clean"]
for a in ("claude","claude-strict","claude-advocate","claude-standard","jev"):
    fa=[i for i in C if rej(a,i)]
    print(a, len(fa), dict(Counter(V.get(i,"not-in-Claude's-30") for i in fa)))
D = [it["id"] for it in items if it["kind"]=="defective"]
for a in ("claude-strict","claude-standard","claude-advocate","claude"):
    print(a, "recall by visibility", {v: f"{sum(rej(a,i) for i in D if by_id[i].get('visible')==v)}/{sum(1 for i in D if by_id[i].get('visible')==v)}" for v in ("diff","needs_other_file","not_visible",None,"split")})
print(Counter(by_id[i].get("visible") for i in D))
