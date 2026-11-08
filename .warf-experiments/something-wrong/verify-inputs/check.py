"""Independent re-check of the 'inputs' audit findings. Stored data only; no git, no network.
    python -B check.py
"""
import json, re, statistics
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent.parent
JEV, LAYA, CR = EXP / "jev-five", EXP / "laya-five", EXP / "laya-near-chance" / "claude-review"

def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def auc(s, y):
    P = [a for a, b in zip(s, y) if b]; N = [a for a, b in zip(s, y) if not b]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))

# Claude items: parse with universal newlines (text mode), independent of parity.py's regex
items, pos, bat = {}, {}, {}
for bf in sorted((CR / "batches").glob("batch-*.txt")):
    txt = open(bf, encoding="utf-8", newline=None).read()
    b = int(bf.stem[-2:])
    chunks = txt.split("<<<ITEM ")[1:]
    for k, ch in enumerate(chunks):
        iid, rest = ch[:6], ch[6 + len(">>>\n"):]
        end = rest.rindex(f"\n<<<END {iid}>>>")
        items[iid] = rest[:end]; pos[iid] = k; bat[iid] = b
print("Claude items", len(items))
key = {k["id"]: k for k in json.loads((CR / "key.json").read_text(encoding="utf-8"))}
res = json.loads((EXP / "laya-near-chance/laya-probe/claude_review_result.json").read_text(encoding="utf-8"))
pc, reason = {}, {}
for b in res["reviews"]:
    for it in b["items"]:
        pc[it["id"]] = it["p_defect"]; reason[it["id"]] = it.get("reason", "")
sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]; y = [s["label"] == "REJECT" for s in sel]
print("selection", len(ids), "unique", len(set(ids)), "REJECT", sum(y), "commits unique", len({s['commit'] for s in sel}))
print("selection label == key label:", all(key[i]["label"] == s["label"] for i, s in zip(ids, sel)),
      "commit/file == key:", all(key[i]["commit"] == s["commit"] and key[i]["file"] == s["file"] for i, s in zip(ids, sel)))
print("selection p_claude == result:", sum(abs(pc[i] - s["p_claude"]) < 1e-12 for i, s in zip(ids, sel)))

cap = {r["id"]: r["state"] for r in jl(JEV / "verify/refute/states.jsonl")}
print("captured states == Claude item:", sum(cap.get(i) == items[i] for i in ids), "of", len(ids))

# per-request state lengths and token counts in the three scored arms
for arm in ("one", "five", "standard"):
    rows = jl(JEV / f"sessions_{arm}.jsonl")
    ok = tot = 0; xs, ts = [], []; r2 = []
    labs_ok = all(r["jev"]["label"] == key[r["jev"]["id"]]["label"] for r in rows)
    for r in rows:
        j = r["jev"]; L = len(items[j["id"]])
        for a, v in j["round1"].items():
            tot += 1; ok += v["state_chars"] == L
            xs.append(v["state_chars"]); ts.append(v["usage"]["input_tokens"])
        for a, v in (j.get("round2") or {}).items():
            r2.append((v["state_chars"] - L, v["usage"]["input_tokens"]))
    print(f"{arm}: rows {len(rows)} ids==sel {sorted(r['jev']['id'] for r in rows) == sorted(ids)} labels ok {labs_ok} "
          f"R1 req {tot} len-equal {ok}; chars {min(xs)}..{max(xs)} tokens {min(ts)}..{max(ts)}")
    if arm == "one":
        mx, mt = statistics.mean(xs), statistics.mean(ts)
        slope = sum((a - mx) * (b - mt) for a, b in zip(xs, ts)) / sum((a - mx) ** 2 for a in xs)
        r = slope * statistics.pstdev(xs) / statistics.pstdev(ts)
        print(f"  one: tokens = {mt - slope * mx:.0f} + {slope:.3f}*chars, r={r:.4f}")
        resid = sorted(((b - (mt - slope * mx + slope * a)), a, b) for a, b in zip(xs, ts))
        print("  largest neg residuals (truncation would show here):", [(round(e), a, b) for e, a, b in resid[:3]])
        top = sorted(zip(xs, ts))[-5:]
        print("  five longest states (chars, tokens):", top, " chars/token on top:", [round(a / (b - (mt - slope*mx)), 2) for a, b in top])
    if r2:
        print(f"  R2 extra chars {min(e for e, _ in r2)}..{max(e for e, _ in r2)}, tokens max {max(t for _, t in r2)}")

# AUCs
one = {r["jev"]["id"]: r["jev"]["round1"]["JEV"]["p_reject"] for r in jl(JEV / "sessions_one.jsonl")}
print(f"AUC Claude {auc([pc[i] for i in ids], y):.4f}  Jev one {auc([one[i] for i in ids], y):.4f}")
print("Jev one distinct p values:", sorted(set(one.values())))
added = [sum(1 for l in items[i].split("\n") if l.startswith("+") and not l.startswith("+++")) for i in ids]
print(f"AUC added lines (from Claude item text) {auc(added, y):.4f}")
print(f"AUC Claude on all 352 {auc([pc[k] for k in key], [key[k]['label']=='REJECT' for k in key]):.4f}")

# leaks
fix = re.compile(r"\b(fix(e[sd])?|bug|revert(ed)?|regression|broken|workaround|hotfix|FIXME|TODO)\b", re.I)
for lab in ("REJECT", "APPROVE"):
    g = [i for i, s in zip(ids, sel) if s["label"] == lab]
    print(f"{lab}: items with fix-ish word anywhere {sum(bool(fix.search(items[i])) for i in g)}/50; "
          f"in added lines {sum(bool(fix.search(chr(10).join(l for l in items[i].split(chr(10)) if l.startswith('+')))) for i in g)}/50")
print("sha prefix (7) in own item:", sum(s["commit"][:7] in items[s["id"]] for s in sel),
      " any selected sha prefix in any item:", sum(any(s["commit"][:7] in items[t] for s in sel) for t in ids))
print(f"AUC int(id) {auc([int(i,16) for i in ids], y):.3f}  position {auc([pos[i] for i in ids], y):.3f}  batch {auc([bat[i] for i in ids], y):.3f}")
print(f"AUC p_claude vs p_laya on 352 (key-reading would tie p to p_laya? check corr):",
      round(auc([pc[k] for k in key], [key[k]['p_laya'] > statistics.median(v['p_laya'] for v in key.values()) for k in key]), 3))
for lab in ("REJECT", "APPROVE"):
    v = [pc[i] for i, s in zip(ids, sel) if s["label"] == lab]
    print(f"p_claude {lab}: {min(v)}..{max(v)} mean {statistics.mean(v):.3f}")

# history-like reasons, broader regex than parity.py
hist = re.compile(r"(later|reverted|revert|history|known|upstream|subsequent|churn|rewritten|reorganiz|"
                  r"was fixed|eventually|follow-?up|refactored later|disabled)", re.I)
hh = [i for i in ids if hist.search(reason[i])]
print(f"history-like reasons: {len(hh)}")
for i in hh:
    print(f"   {i} [{key[i]['label']}] p={pc[i]}: {reason[i][:150]}")
keep = [k for k, i in enumerate(ids) if i not in hh]
print(f"Claude AUC without them: {auc([pc[ids[k]] for k in keep], [y[k] for k in keep]):.4f} n={len(keep)}")
# worst case: set those to the median of the rest
med = statistics.median(pc[ids[k]] for k in keep)
print(f"Claude AUC with them neutralised to median {med}: {auc([pc[i] if i not in hh else med for i in ids], y):.4f}")
