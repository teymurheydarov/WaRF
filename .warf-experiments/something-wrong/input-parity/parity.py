"""Input parity: did Jev (one, five, standard arms) see the same text as Claude's blinded review
on the 100 laya-five commits? Stored data plus a read-only rebuild through run_five.prepare
(git show / git cat-file only). Calls no model. Writes nothing outside this directory.

    python -B parity.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
JEV = EXP / "jev-five"
LAYA = EXP / "laya-five"
CR = EXP / "laya-near-chance" / "claude-review"

sys.path.insert(0, str(LAYA))
from run_five import INPUT_LABEL, PLAN, prepare  # noqa: E402  (sets WARF_HOME in this process only)
from warf.providers import DECISION_CRITERIA  # noqa: E402
from warf.state import default_profiles  # noqa: E402


def jl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- Claude's batch inputs -------------------------------------------------------------
batch_state, batch_of, batch_pos, batch_items = {}, {}, {}, {}
for bf in sorted((CR / "batches").glob("batch-*.txt")):
    raw = bf.read_bytes()
    CRLF, LF = bytes([13, 10]), bytes([10])
    crlf_lines = raw.count(CRLF)
    lf_only = raw.count(LF) - crlf_lines
    txt = raw.replace(CRLF, LF).decode("utf-8")   # undo Windows text-mode write (open(..., "w"))
    print(f"{bf.name}: CRLF line ends {crlf_lines}, bare LF {lf_only}, stray CR left {txt.count(chr(13))}")
    b = int(bf.stem.split("-")[1])
    items = re.findall(r"<<<ITEM ([0-9a-f]{6})>>>\n(.*?)\n<<<END \1>>>\n", txt, re.S)
    batch_items[b] = [i for i, _ in items]
    for pos, (i, s) in enumerate(items):
        batch_state[i] = s
        batch_of[i] = b
        batch_pos[i] = pos
    if b == 1:
        print(f"batch file BOM: {raw[:3] == bytes([0xef, 0xbb, 0xbf])}")
print(f"Claude batch items parsed: {len(batch_state)} in {len(batch_items)} batches")

key = {k["id"]: k for k in json.loads((CR / "key.json").read_text(encoding="utf-8"))}
res = json.loads((EXP / "laya-near-chance" / "laya-probe" / "claude_review_result.json").read_text(encoding="utf-8"))
p_claude = {}
dup = 0
for b in res["reviews"]:
    for it in b["items"]:
        dup += it["id"] in p_claude
        p_claude[it["id"]] = (it["p_defect"], b["batch"], it.get("reason", ""))
print(f"Claude result: {len(p_claude)} ids, {dup} duplicates; keys of result file: {sorted(res)}")

sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]
print(f"selection: {len(sel)} rows, {len(set(ids))} ids, {sum(s['label'] == 'REJECT' for s in sel)} REJECT")

# selection p_claude == result file; result batch == key batch == file batch
bad = [s["id"] for s in sel if abs(p_claude[s["id"]][0] - s["p_claude"]) > 1e-12
       or p_claude[s["id"]][1] != key[s["id"]]["batch"] or batch_of[s["id"]] != key[s["id"]]["batch"]]
print(f"p_claude in selection vs result file / batch numbers disagree: {len(bad)} {bad[:5]}")
bad = [i for i in ids if len(batch_state[i]) != key[i]["state_chars"]]
print(f"batch state length != key state_chars (sweep's Laya state): {len(bad)}")

# --- Jev states actually sent (captured by the Tap in the verification rerun) ----------
cap = {r["id"]: r for r in jl(JEV / "verify" / "refute" / "states.jsonl")}
print(f"captured Jev states (verify/refute/states.jsonl): {len(cap)}")
same = [i for i in ids if i in cap and cap[i]["state"] == batch_state[i]]
diff_ = [i for i in ids if i in cap and cap[i]["state"] != batch_state[i]]
print(f"  captured Jev state == Claude batch item, byte for byte: {len(same)} of {len(ids)}; differ: {len(diff_)} {diff_[:5]}")
bad = [i for i in ids if i in cap and hashlib.sha256(cap[i]["state"].encode("utf-8")).hexdigest() != cap[i].get("sha256")]
print(f"  stored sha256 != sha256(state): {len(bad)} (sha256 may be of another field)")

# --- Rebuild every request now, through the exact code path of run_jev.py -------------
plan = {e["sha"]: e for e in jl(PLAN)}
rebuilt, ctxs, errs, trunc = {}, set(), 0, 0
for s in sel:
    code, domain, context, enrich_error = prepare(plan[s["commit"]], s["file"])
    ctxs.add(context)
    errs += enrich_error is not None
    ctx_section = f"Project context:\n{context}\n\n" if context else ""
    state = f"Domain: {domain}\n\n{ctx_section}{INPUT_LABEL}:\n```\n{code}\n```"   # orchestrator._call_agent
    rebuilt[s["id"]] = state
    trunc += len(code) >= 50_000 - 100
print(f"rebuilt via run_five.prepare + orchestrator frame: contexts seen {ctxs}, enrich errors {errs}, near-50k truncation {trunc}")
eq = sum(rebuilt[i] == batch_state[i] for i in ids)
print(f"  rebuilt request state == Claude batch item: {eq} of {len(ids)}")
eq = sum(rebuilt[i] == cap[i]["state"] for i in ids if i in cap)
print(f"  rebuilt request state == captured Jev state: {eq} of {len(cap)}")

# --- Stored per-request state_chars of the three scored Jev arms ----------------------
personas = {p.name: p.persona for p in default_profiles()}
for arm in ("one", "five", "standard"):
    rows = jl(JEV / f"sessions_{arm}.jsonl")
    n_req = n_ok = 0
    r2_extra = []
    ids_arm = set()
    for r in rows:
        j = r["jev"]
        ids_arm.add(j["id"])
        for agent, a in j["round1"].items():
            n_req += 1
            n_ok += a["state_chars"] == len(batch_state[j["id"]])
        for agent, a in (j.get("round2") or {}).items():
            r2_extra.append(a["state_chars"] - len(batch_state[j["id"]]))
    print(f"sessions_{arm}: {len(rows)} sessions, ids == selection: {ids_arm == set(ids)}; "
          f"Round-1 requests {n_req}, state length == Claude item length: {n_ok}"
          + (f"; Round-2 requests {len(r2_extra)}, extra chars min {min(r2_extra)} max {max(r2_extra)}" if r2_extra else ""))
    labs = {r["jev"]["id"]: r["jev"]["label"] for r in rows}
    print(f"   labels in session file agree with selection: {all(labs[s['id']] == s['label'] for s in sel)}")
    mods = sorted({m for r in rows for m in r["jev"]["models"]})
    errs_ = sum(r["jev"]["enrich_error"] is not None for r in rows)
    print(f"   models answering: {mods}; enrich errors {errs_}")

# --- Jev's question text ----------------------------------------------------------------
prof_one = json.loads((JEV / "profiles" / "jev_one.json").read_text(encoding="utf-8"))
prof_five = json.loads((JEV / "profiles" / "jev_five.json").read_text(encoding="utf-8"))
print("Jev one-arm instructions:", [d["persona"] for d in prof_one], [(d.get("provider"), d.get("model")) for d in prof_one])
print("Jev five-arm personas (chars):", [(d["name"], len(d["persona"]), d.get("provider"), d.get("model")) for d in prof_five])
print("criteria:", DECISION_CRITERIA)

# --- Leak checks on what Claude (and Jev) read -----------------------------------------
sha_hits, subj_hits, meta_hits = [], [], []
for s in sel:
    st = batch_state[s["id"]]
    e = plan[s["commit"]]
    if s["commit"][:7] in st:
        sha_hits.append(s["id"])
    subj = e.get("subject") or ""
    if len(subj) > 15 and subj[:30] in st:
        subj_hits.append(s["id"])
    if re.search(r"^(Author|Date|commit [0-9a-f]{40}|From [0-9a-f]{40}|Signed-off-by)", st, re.M):
        meta_hits.append(s["id"])
print(f"leak checks on the 100 Claude items: own commit sha prefix in text {len(sha_hits)}, "
      f"commit subject in text {len(subj_hits)}, commit metadata lines {len(meta_hits)}")
fixw = re.compile(r"\b(fix(e[sd])?|bug|revert|regression|broken|workaround|hotfix)\b", re.I)
for lab in ("REJECT", "APPROVE"):
    grp = [s for s in sel if s["label"] == lab]
    n = sum(bool(fixw.search(batch_state[s["id"]])) for s in grp)
    print(f"  items whose text has a fix/bug/revert word, {lab}: {n} of {len(grp)}")

# id letters vs label (ids are secrets.token_hex(3)); position in batch vs label
def auc(score, pos):
    P = [x for x, y in zip(score, pos) if y]
    N = [x for x, y in zip(score, pos) if not y]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


y = [s["label"] == "REJECT" for s in sel]
print(f"AUC of int(id, 16) vs label: {auc([int(i, 16) for i in ids], y):.3f}; "
      f"of position within batch: {auc([batch_pos[i] for i in ids], y):.3f}; of batch number: {auc([batch_of[i] for i in ids], y):.3f}")
allkey = list(key.values())
print(f"whole 352-item Claude sample: AUC of position within batch {auc([batch_pos[k['id']] for k in allkey], [k['label'] == 'REJECT' for k in allkey]):.3f}")
for b, its in batch_items.items():
    pass
print("per batch: items, REJECT share:", [(b, len(v), sum(key[i]['label'] == 'REJECT' for i in v)) for b, v in batch_items.items()])
# where are the matched pair partners?  (pairs are consecutive rows of selection)
same_b = sum(batch_of[sel[k]["id"]] == batch_of[sel[k + 1]["id"]] for k in range(0, 100, 2))
gaps = [abs(batch_pos[sel[k]["id"]] - batch_pos[sel[k + 1]["id"]]) for k in range(0, 100, 2)
        if batch_of[sel[k]["id"]] == batch_of[sel[k + 1]["id"]]]
print(f"matched selection pairs in the same Claude batch: {same_b} of 50; adjacent (gap 1): {sum(g == 1 for g in gaps)}")

# Claude scores vs Jev on these 100
pc = [p_claude[i][0] for i in ids]
print(f"Claude AUC on the 100: {auc(pc, y):.3f}")
one = {r['jev']['id']: r['jev']['round1']['JEV']['p_reject'] for r in jl(JEV / 'sessions_one.jsonl')}
print(f"Jev one AUC on the 100 (stored): {auc([one[i] for i in ids], y):.3f}")
hist = re.compile(r"(later|was (later )?(fixed|reverted)|history|known|upstream fix|subsequent)", re.I)
hh = [i for i in ids if hist.search(p_claude[i][2])]
print(f"Claude reasons on the 100 with history-like words: {len(hh)}: " + "; ".join(f"{i}[{key[i]['label']}] {p_claude[i][2][:90]}" for i in hh))
if hh:
    keep = [k for k, i in enumerate(ids) if i not in hh]
    print(f"  Claude AUC without them: {auc([pc[k] for k in keep], [y[k] for k in keep]):.3f} (n={len(keep)})")
