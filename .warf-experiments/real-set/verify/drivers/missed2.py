from load import *
D = [it["id"] for it in items if it["kind"]=="defective"]
ms = [i for i in D if not rej("claude-strict", i)]; mw = [i for i in D if not rej("claude-standard", i)]
for i in sorted(set(ms)|set(mw), key=lambda i: by_id[i]["date"]):
    print(f"\n### {i}")
    if rej("claude", i): print("  CLAUDE:", reply("claude", i)[:450].replace("\n"," "))
    if i in mw:
        for v in recs["claude-standard"][i]["votes"]:
            if v["label"]=="REJECT": print(f"  W1 {v['agent']}:", v["reasoning"][:300].replace("\n"," "))
