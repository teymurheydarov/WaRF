"""Item-by-item comparison of my log-odds implementation (mine.jsonl) with WaRF's replay (warf.jsonl),
plus the leakage and seat-equality checks."""
import difflib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
SEATS = ("claude", "jev", "laya")
SEP = "\n\n" + "─" * 60 + "\n"
mine = {r["id"]: r for r in map(json.loads, (HERE / "mine.jsonl").open(encoding="utf-8"))}
warf = {r["id"]: r for r in map(json.loads, (HERE / "warf.jsonl").open(encoding="utf-8"))}
items = [json.loads(l) for l in (EXP / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
recs = {s: {} for s in SEATS}
for s in SEATS:
    for p in sorted(EXP.glob(f"{s}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            recs[s][r["planted"]["id"]] = r

print("== (2) my log-odds vs WaRF replay ==")
for mode in ("cal", "cold"):
    dd = dc = da = 0
    maxlam = maxev = 0.0
    tagdiff = 0
    for i in mine:
        m, w = mine[i][mode], warf[i][mode]
        dd += m["decision"] != w["decision"]
        dc += m["confidence"] != w["confidence"]
        da += m["asked"] != len(w["votes"])
        maxlam = max(maxlam, abs(m["lambda"] - w["lambda"]))
        for e, t, v in zip(m["ev"], m["tags"], w["votes"]):
            maxev = max(maxev, abs(e - v["evidence"]))
            tagdiff += t != v["tag"]
    print(f"  {mode}: decision diffs {dd}, confidence diffs {dc}, seats-asked diffs {da}, tag diffs {tagdiff}, "
          f"max |dLambda| {maxlam:.2e}, max |d evidence| {maxev:.2e}")

print("\n== (3a) Claude's message: panel seat vs Claude alone; Jev/Laya readouts ==")
neq = {s: 0 for s in SEATS}
for i in warf:
    for v in warf[i]["cal"]["votes"] + warf[i]["cold"]["votes"]:
        s = v["agent"].lower()
        st = recs[s][i]["votes"][0]
        if (v["reasoning"], v["vote"], v["provider"], v["model"]) != (st["reasoning"], st["vote"], st["provider"], st["model"]):
            neq[s] += 1
print("  votes differing from the single-seat record (reasoning, vote, provider, model):", neq)
print("  Claude-alone decision == its single vote on all items:",
      all((recs["claude"][i]["decision"] == "REJECT") == (recs["claude"][i]["votes"][0]["vote"] == -1) for i in recs["claude"]))
print("  provider calls per review: cal", sorted({tuple(warf[i]['cal']['calls']) for i in warf}),
      " cold", sorted({tuple(warf[i]['cold']['calls']) for i in warf}))

print("\n== (3b) calibration logs: does item i's log contain i or its twin? ==")
fold_of = {i: mine[i]["fold"] for i in mine}
sid = {s: {i: recs[s][i]["session_id"] for i in recs[s]} for s in SEATS}
art = {i: recs["claude"][i]["artifact"] for i in recs["claude"]}
for k in range(5):
    log = [json.loads(l) for l in (HERE / f"train{k}.jsonl").open(encoding="utf-8")]
    sids = {r["session_id"] for r in log}
    arts = {r["artifact"] for r in log}
    test = [i for i in mine if fold_of[i] == k]
    own = sum(sid[s][i] in sids for s in SEATS for i in test)
    twin_art = sum(art[i] in arts for i in test)
    print(f"  fold {k}: {len(test)} test items, log {len(log)} sessions; test sessions in log {own}; "
          f"test artifacts (commit:file, shared by twins) in log {twin_art}")
commits = {}
files = {}
for it in items:
    commits.setdefault(it["commit"], set()).add(it["base"])
    files.setdefault(it["file"], set()).add(it["base"])
print("  commits with >1 base:", sum(len(v) > 1 for v in commits.values()),
      "; files with >1 base:", {f: sorted(v) for f, v in files.items() if len(v) > 1})
cross = [(f, sorted({fold_of[b + ':clean'] for b in v})) for f, v in files.items() if len(v) > 1]
print("  same file in several bases -> folds:", cross)

print("\n== (3c) clean vs planted: what differs ==")
n_extra = n_ctx = n_dom = 0
lens, sent = [], []
block_mismatch = 0
for b in sorted({it["base"] for it in items}):
    c, p = by_id[b + ":clean"], by_id[b + ":planted"]
    if c["context"] != p["context"]:
        n_ctx += 1
    if c["domain"] != p["domain"]:
        n_dom += 1
    cl, pl = c["code"].split("\n"), p["code"].split("\n")
    if len(cl) != len(pl):
        n_extra += 1
        continue
    diff = [(x, y) for x, y in zip(cl, pl) if x != y]
    exp = (p["original"], p["mutated"])
    ok = all(x.lstrip("+") .strip() == exp[0][1:].strip() and y.lstrip("+").strip() == exp[1][1:].strip() for x, y in diff)
    if not ok:
        n_extra += 1
        print("   unexpected diff in", b, diff[:3])
    cpatch, _, cblock = c["code"].partition(SEP)
    ppatch, _, pblock = p["code"].partition(SEP)
    # the function body block should carry the mutation wherever the patch line's code occurs
    if cblock and exp[0][1:].strip() in cblock and exp[0][1:].strip() in pblock:
        block_mismatch += 1
        print("   original line still in planted block:", b)
    lens.append(len(p["code"]) - len(c["code"]))
    sent.append({s: recs[s][b + ":planted"]["planted"]["call"]["sent_chars"] - recs[s][b + ":clean"]["planted"]["call"]["sent_chars"]
                 for s in SEATS})
    nd = len(diff)
    if nd != 1:
        print(f"   {b}: {nd} lines differ ({sum(1 for x,_ in diff if x.startswith('+'))} in patch)")
print(f"  bases with a difference beyond the planted line: {n_extra}; context differs: {n_ctx}; domain differs: {n_dom}; "
      f"planted block still holds the original: {block_mismatch}")
print("  code length planted - clean:", {d: lens.count(d) for d in sorted(set(lens))})
print("  sent_chars planted - clean equals code-length difference for every seat:",
      all(all(v == l for v in s.values()) for s, l in zip(sent, lens)))
pos = []
for b in sorted({it["base"] for it in items}):
    p = by_id[b + ":planted"]
    patch = p["code"].split(SEP)[0].split("\n")
    idx = patch.index(p["mutated"])
    pos.append(idx / max(1, len(patch) - 1))
print(f"  relative position of the planted line in the patch: min {min(pos):.2f}, median {sorted(pos)[len(pos)//2]:.2f}, max {max(pos):.2f}")
