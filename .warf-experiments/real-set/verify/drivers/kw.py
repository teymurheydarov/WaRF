import re
from load import *
K = {"090f874":r"d-1|d - 1|<0|d==1|d = 1|zero-dim|0-dim|d=1", "1dc79db":r"\band\b.*MSVC|MSVC|alternative token|`and`", "43d4274":r"no free|empty|zero rows|freeSize\(\) *== *0|cols\(\) *== *0|0 columns",
     "9366184":r"return 0|C\+\+98|emulat", "f5c66ad":r"rhs|right-hand|column", "e05b6b0":r"numInnerKnot|m_p-1-m_r|m_p - 1 - m_r|== *1", "d729485":r"invert|rho_k/|corner|more than two|three patches",
     "7eccbe3":r"conservativeResize", "640ac27":r"static_cast|basis\(i\)", "fcd9e3c":r"static_cast|basis\(i\)", "99b2161":r"ambig", "87f74c2":r"typename", "f104284":r"int\b|unsigned|index_t"}
for i in [it["id"] for it in items if it["kind"]=="defective"]:
    c = i.split(":")[0]
    if c not in K: continue
    for arm in ("claude","claude-strict","claude-advocate"):
        t = reply(arm, i); m = re.findall(K[c], t)
        print(c, arm, "REJ" if rej(arm,i) else "app", len(m), m[:4])
    for v in recs["claude-standard"][i]["votes"]:
        m = re.findall(K[c], v["reasoning"]); print(c, "  W1", v["agent"], v["label"], len(m), m[:3])
