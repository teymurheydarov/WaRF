import json, re, collections
from pathlib import Path
S = Path(__file__).resolve().parents[2]
prof = {p["name"]: p["persona_hash"] for p in json.load(open(S/"profiles/claude-standard.json", encoding="utf-8"))}
p1 = {p["name"]: p["persona_hash"] for p in json.load(open(S/"profiles/claude.json", encoding="utf-8"))}
bad_hash, intent, doms = [], [], collections.Counter()
for arm, pr in (("claude-standard", prof), ("claude", p1)):
    for f in sorted(S.glob(f"{arm}.w*.jsonl")):
        for l in f.open(encoding="utf-8"):
            r = json.loads(l); doms[(arm, r["domain"])] += 1
            calls = r["planted"].get("calls") or [r["planted"]["call"]]
            for v, c in zip(r["votes"], calls):
                if v["persona"] != pr.get(v["agent"]): bad_hash.append((arm, r["planted"]["id"], v["agent"], v["persona"]))
                w = re.sub(r"[^A-Z]", "", c["reply"].split()[0].upper())
                iv = {"APPROVE": 1, "REJECT": -1}.get(w)
                if iv != v["vote"]: intent.append((arm, r["planted"]["id"], v["agent"], w, v["vote"]))
print("persona hash mismatches:", bad_hash[:5], len(bad_hash))
print("first-word (markup stripped) vs recorded vote mismatches:", intent)
print("domains:", dict(doms))
print("profile hashes five:", prof); print("one:", p1)
