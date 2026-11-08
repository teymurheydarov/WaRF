import re
from load import *
P = {"43d4274":r"empty|0 columns","9366184":r"return 0","7eccbe3":r"conservativeResize","e05b6b0":r"numInnerKnot","f5c66ad":r"rhs|right-hand|single column|one column","640ac27":r"basis\(i\)","090f874":r"d-1"}
for i in [it["id"] for it in items if it["kind"]=="defective"]:
    c = i.split(":")[0]
    if c not in P: continue
    for arm in ("claude","claude-strict"):
        t = reply(arm, i)
        for m in list(re.finditer(P[c], t))[:2]:
            print(c, arm, "...", t[max(0,m.start()-200):m.end()+200].replace("\n"," "), "\n")
