"""Audit the real-set records (pure Python, no warf import, read-only).

    python -B audit.py   -> prints findings; writes nothing
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SET = Path(__file__).resolve().parents[2]
ARMS = ("claude", "claude-strict", "claude-advocate", "claude-standard", "jev")
CLAUDE_ARMS = ARMS[:4]
MODEL = "claude-opus-5-5"
INPUT_LABEL = "Patch under review (unified diff)"
REPLY_FORMAT = ("First line of your response must be exactly one word: APPROVE or REJECT.\n"
                "Subsequent lines: your reasoning.")
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
LLR_A = math.log(0.8 / 0.3)
LLR_R = math.log(0.2 / 0.7)
A = math.log(0.9 / 0.05)
B = math.log(0.1 / 0.95)

problems = []


def bad(msg):
    problems.append(msg)
    print("  PROBLEM:", msg)


items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
print(f"items: {len(items)}, ids unique: {len(by_id) == len(items)}, kinds {Counter(it['kind'] for it in items)}, "
      f"answers {Counter((it['kind'], it['answer']) for it in items)}")

recs = {}          # arm -> id -> list of (file, lineno, record)
for arm in ARMS:
    recs[arm] = defaultdict(list)
    for path in sorted(SET.glob(f"{arm}.w*.jsonl")):
        for n, line in enumerate(path.open(encoding="utf-8"), 1):
            r = json.loads(line)
            recs[arm][r["planted"]["id"]].append((path.name, n, r))

print("\n== (a) one record per item per arm; labels match items.jsonl ==")
for arm in ARMS:
    cnt = Counter(len(v) for v in recs[arm].values())
    missing = [i for i in by_id if i not in recs[arm]]
    extra = [i for i in recs[arm] if i not in by_id]
    dups = [i for i, v in recs[arm].items() if len(v) > 1]
    print(f"  {arm:<16} records {sum(len(v) for v in recs[arm].values())}, items covered {len(recs[arm])}, "
          f"missing {len(missing)}, not in items {len(extra)}, duplicated {len(dups)}")
    for i in missing + extra + dups:
        bad(f"{arm}: {i} missing/extra/duplicated")
    mism = Counter()
    for i, lst in recs[arm].items():
        it = by_id.get(i)
        if it is None:
            continue
        for _, _, r in lst:
            p = r["planted"]
            if p["kind"] != it["kind"]:
                mism["kind"] += 1
            if p["base"] != it["base"]:
                mism["base"] += 1
            if r["artifact"] != f"{it['commit']}:{it['file']}":
                mism["artifact"] += 1
            if r["domain"] != it["domain"]:
                mism["domain"] += 1
            if abs(r["theta"] - THETA[it["domain"]]) > 1e-12:
                mism["theta"] += 1
            if p.get("operator") is not None:
                mism["operator not null"] += 1
    print(f"    label/base/artifact/domain/theta mismatches: {dict(mism) or 'none'}")
    for k, v in mism.items():
        bad(f"{arm}: {v} records with {k} mismatch")

print("\n== (b) errors.jsonl: each errored (item, arm) later has exactly one complete record ==")
errs = [json.loads(l) for l in (SET / "errors.jsonl").open(encoding="utf-8")]
print(f"  {len(errs)} entries; by arm {dict(Counter(e['arm'] for e in errs))}; "
      f"distinct (id, arm) {len({(e['id'], e['arm']) for e in errs})}")
msgs = Counter(e["error"].split(":", 2)[0] + ": " + e["error"].split("] ")[-1][:60] for e in errs)
print(f"  messages: {dict(msgs)}")
for e in errs:
    lst = recs[e["arm"]].get(e["id"], [])
    if len(lst) != 1:
        bad(f"error {e['arm']} {e['id']}: {len(lst)} records")
        continue
    r = lst[0][2]
    t_err = datetime.fromisoformat(e["at"])
    t_rec = datetime.fromisoformat(r["created_at"])
    if t_rec <= t_err:
        bad(f"error {e['arm']} {e['id']}: record created {r['created_at']} not after error {e['at']}")
print(f"  every errored (id, arm) has one record created after its error: "
      f"{all(len(recs[e['arm']].get(e['id'], [])) == 1 and datetime.fromisoformat(recs[e['arm']][e['id']][0][2]['created_at']) > datetime.fromisoformat(e['at']) for e in errs)}")
# records written by the first (interrupted) and the resumed run of each arm
for arm in ARMS:
    ts = sorted(datetime.fromisoformat(r["created_at"]) for lst in recs[arm].values() for _, _, r in lst)
    print(f"  {arm:<16} first record {ts[0].isoformat()[:19]}  last {ts[-1].isoformat()[:19]}")

print("\n== (c) every Claude call: model claude-opus-5-5, reply APPROVE/REJECT, vote follows reply ==")
NON_ANSWER = re.compile(r"limit|error|log ?in|credit|overloaded|unavailable|try again", re.I)


def first_word(text):
    return text.split()[0].upper().rstrip(".,:") if text.split() else ""


for arm in CLAUDE_ARMS:
    stats = Counter()
    for i, lst in recs[arm].items():
        r = lst[0][2]
        p = r["planted"]
        calls = p["calls"] if "calls" in p else [p["call"]]
        if p["provider"] != "claude_cli" or p["model"] != MODEL:
            bad(f"{arm} {i}: planted provider/model {p['provider']}/{p['model']}")
        if len(calls) != len(r["votes"]):
            bad(f"{arm} {i}: {len(calls)} calls vs {len(r['votes'])} votes")
        for c, v in zip(calls, r["votes"]):
            stats["calls"] += 1
            if c.get("model") != MODEL:
                stats["call model != opus-5-5"] += 1
            if v.get("model") != MODEL or v.get("provider") != "claude_cli":
                stats["vote provider/model wrong"] += 1
            fw = first_word(c["reply"])
            if fw not in ("APPROVE", "REJECT"):
                stats["first word not APPROVE/REJECT"] += 1
                bad(f"{arm} {i} {c.get('agent')}: reply starts {c['reply'][:80]!r}")
            first_line = c["reply"].split("\n", 1)[0].strip()
            if first_line not in ("APPROVE", "REJECT"):
                stats["first line not exactly APPROVE/REJECT"] += 1
            if not c.get("exact"):
                stats["exact flag false"] += 1
            if len(c["reply"]) < 400 and NON_ANSWER.search(c["reply"]):
                stats["short reply matching non-answer pattern"] += 1
            if fw in ("APPROVE", "REJECT") and v["label"] != fw:
                stats["vote label != reply first word"] += 1
                bad(f"{arm} {i}: vote {v['label']} vs reply {fw}")
            if c.get("agent") != v["agent"]:
                stats["call agent != vote agent"] += 1
            if v["vote"] != (1 if v["label"] == "APPROVE" else -1):
                stats["vote/label inconsistent"] += 1
            if v["omega"] != 0.5:
                stats["omega != 0.5"] += 1
        if arm != "claude-standard":
            if r["decision"] != r["votes"][0]["label"]:
                bad(f"{arm} {i}: decision {r['decision']} vs vote {r['votes'][0]['label']}")
                stats["decision != single vote"] += 1
    print(f"  {arm:<16} {dict(stats)}")

print("\n== jev records: model, choice, readout, decision ==")
stats = Counter()
for i, lst in recs["jev"].items():
    r = lst[0][2]
    body = r["planted"]["call"]["body"]
    ans = body["answers"]["verdict"]
    v = r["votes"][0]
    stats[f"body model {body.get('model')}"] += 1
    if len(r["votes"]) != 1:
        stats["votes != 1"] += 1
    if ans["choice"] != v["label"] or r["decision"] != v["label"]:
        stats["choice/vote/decision mismatch"] += 1
    pr = ans["probabilities"]
    if abs(pr["APPROVE"] + pr["REJECT"] - 1) > 0.05:
        stats["probs do not sum to 1"] += 1
    if (pr["REJECT"] - 0.5) * v["vote"] > 0:
        stats["p contradicts vote"] += 1
    if "decision model, no reasoning" not in v["reasoning"]:
        stats["no decision tag"] += 1
print(f"  {dict(stats)}")

print("\n== (d) same message per item across arms (sent_chars) ==")
suffix = len("\n\n" + REPLY_FORMAT)
stats = Counter()
for it in items:
    i = it["id"]
    ctx = f"Project context:\n{it['context']}\n\n" if it["context"] else ""
    msg = f"Domain: {it['domain']}\n\n{ctx}{INPUT_LABEL}:\n```\n{it['code']}\n```"
    want_claude = len(msg) + suffix
    seen = {}
    for arm in CLAUDE_ARMS:
        p = recs[arm][i][0][2]["planted"]
        calls = p["calls"] if "calls" in p else [p["call"]]
        seen[arm] = {c["sent_chars"] for c in calls}
    jev_sent = recs["jev"][i][0][2]["planted"]["call"]["sent_chars"]
    allc = set().union(*seen.values())
    if allc != {want_claude}:
        stats["claude sent_chars differ from the rebuilt message"] += 1
        bad(f"{i}: claude sent_chars {seen} vs rebuilt {want_claude}")
    else:
        stats["claude arms identical and equal to rebuilt message"] += 1
    if jev_sent != len(msg):
        stats["jev sent_chars != rebuilt message without reply format"] += 1
        bad(f"{i}: jev sent_chars {jev_sent} vs {len(msg)}")
    else:
        stats["jev equal to rebuilt message without reply format"] += 1
print(f"  reply-format suffix length {suffix}; {dict(stats)}")

print("\n== (e) W1 decisions follow WaRF vote mode ==")
prof = json.loads((SET / "profiles" / "claude-standard.json").read_text(encoding="utf-8"))
order = [p["name"] for p in prof]
print(f"  profile order {order}; all weights uniform: "
      f"{all(w['alpha'] == 1 and w['beta'] == 1 for p in prof for w in p['weights'].values())}, "
      f"last_updated {set(p['last_updated'] for p in prof)}")
stats = Counter()
for i, lst in recs["claude-standard"].items():
    r = lst[0][2]
    votes = r["votes"]
    names = [v["agent"] for v in votes]
    if names != order[:len(names)]:
        stats["vote order != profile order"] += 1
        bad(f"W1 {i}: order {names}")
    lam, fired, k_fire = 0.0, None, None
    for k, v in enumerate(votes, 1):
        lam += v["omega"] * (LLR_A if v["vote"] == 1 else LLR_R)
        if fired is None and lam >= A:
            fired, k_fire = "APPROVE", k
        elif fired is None and lam <= B:
            fired, k_fire = "REJECT", k
        if fired:
            break
    if fired:
        dec, conf = fired, "HIGH"
        if k_fire != len(votes):
            stats["votes after the boundary"] += 1
            bad(f"W1 {i}: boundary at {k_fire} but {len(votes)} votes")
    else:
        if len(votes) != len(order):
            stats["pool not exhausted but no boundary (missing seat)"] += 1
            bad(f"W1 {i}: {len(votes)} votes, no boundary")
        w = [v["omega"] for v in votes]
        norm = sum(wi * v["vote"] for wi, v in zip(w, votes)) / sum(w)
        th = THETA[r["domain"]]
        dec = "APPROVE" if norm >= th else "REJECT"
        conf = "MEDIUM" if abs(norm - th) >= 0.2 else "LOW"
        maj = "APPROVE" if sum(v["vote"] for v in votes) > 0 else "REJECT"
        if maj != dec:
            stats["threshold decision differs from simple majority"] += 1
    if dec != r["decision"]:
        stats["decision mismatch"] += 1
        bad(f"W1 {i}: recomputed {dec} vs stored {r['decision']}")
    else:
        stats["decision matches"] += 1
    if conf != r["confidence"]:
        stats["confidence mismatch"] += 1
    if abs(lam - r["sprt_lambda"]) > 1e-3:
        stats["lambda mismatch"] += 1
    if bool(fired) != bool(r["sprt_fired"]):
        stats["sprt_fired mismatch"] += 1
    stats[f"{len(votes)} votes"] += 1
print(f"  {dict(sorted(stats.items()))}")
print(f"  total W1 calls {sum(len(lst[0][2]['planted']['calls']) for lst in recs['claude-standard'].values())}")

print(f"\n{len(problems)} problems")
