"""Independent recompute and integrity audit of ../../ (four-arms). Does not import score_four.py.
Read-only except stdout. Run from anywhere:
    python -B audit.py            # records + scores
    python -B audit.py --rebuild  # also rebuild every message with laya-five/run_five.py's prepare
"""
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOUR = HERE.parent.parent
EXP = FOUR.parent
WARF = EXP.parent
ARMS = ("claude-one", "claude-standard", "jev-one", "jev-standard")
REBUILD = "--rebuild" in sys.argv

problems = []


def bad(msg):
    problems.append(msg)


# ---------- constants, derived from the formulas, then compared with warf.engine ----------
P1, P0, AE, BE = 0.80, 0.30, 0.05, 0.10
A = math.log((1 - BE) / AE)
B = math.log(BE / (1 - AE))
LA = math.log(P1 / P0)
LR = math.log((1 - P1) / (1 - P0))
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
sys.path.insert(0, str(WARF))
import warf.engine as eng  # noqa: E402  (constants only, cross-check)
from warf.orchestrator import REPLY_FORMAT  # noqa: E402
from warf.state import default_profiles  # noqa: E402

assert (eng.A, eng.B, eng.LLR_APPROVE, eng.LLR_REJECT) == (A, B, LA, LR), "engine constants differ"
assert eng.THETA == THETA, eng.THETA
PANEL = [p.name for p in default_profiles()]
PANEL_HASH = {p.name: p.persona_hash for p in default_profiles()}
print(f"A={A:.4f} B={B:.4f} LLR+={LA:.4f} LLR-={LR:.4f}; panel {PANEL}")

selection = [json.loads(l) for l in (EXP / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
ids = [s["id"] for s in selection]
sel = {s["id"]: s for s in selection}
assert len(set(ids)) == 100
defect = {i: sel[i]["label"] == "REJECT" for i in ids}
T18 = set(json.loads((EXP / "something-wrong" / "verify-labels-metrics" / "v2_data.json").read_text(encoding="utf-8"))["t18"])
assert len(T18) == 18 and T18 <= set(ids)
assert all(not defect[i] for i in T18), "a t18 change is labelled REJECT"

# ---------- load ----------
recs = {}
for arm in ARMS:
    recs[arm] = {}
    files = sorted(FOUR.glob(f"{arm}.w*.jsonl"))
    for path in files:
        for ln, line in enumerate(path.open(encoding="utf-8"), 1):
            r = json.loads(line)
            f = r["four"]
            i = f["id"]
            if i in recs[arm]:
                bad(f"{arm}: {i} twice ({path.name}:{ln})")
            if i not in sel:
                bad(f"{arm}: unknown id {i}")
                continue
            s = sel[i]
            for k in ("commit", "file", "label"):
                if f[k] != s[k]:
                    bad(f"{arm} {i}: four.{k} {f[k]!r} != selection {s[k]!r}")
            if r["artifact"] != f"{s['commit']}:{s['file']}":
                bad(f"{arm} {i}: artifact {r['artifact']}")
            if r["domain"] != s["domain"]:
                bad(f"{arm} {i}: domain {r['domain']} vs {s['domain']}")
            if f["arm"] != arm or r["profile"] != arm:
                bad(f"{arm} {i}: arm/profile {f['arm']}/{r['profile']}")
            recs[arm][i] = r
    print(f"{arm}: {sum(1 for p in files for _ in p.open(encoding='utf-8'))} lines in {[p.name for p in files]}, "
          f"{len(recs[arm])} distinct ids, missing {[i for i in ids if i not in recs[arm]]}")
    if (FOUR / "errors.jsonl").exists():
        bad("errors.jsonl exists")

# ---------- SPRT / synthesis re-derivation ----------
n_checked = 0
for arm in ARMS:
    standard = arm.endswith("standard")
    claude = arm.startswith("claude")
    for i, r in recs[arm].items():
        votes = r["votes"]
        th = THETA[r["domain"]]
        if r["theta"] != th:
            bad(f"{arm} {i}: theta {r['theta']} vs {th}")
        names = [v["agent"] for v in votes]
        want_names = PANEL if standard else (["CLAUDE"] if claude else ["JEV"])
        if names != want_names[:len(names)]:
            bad(f"{arm} {i}: agent order {names}")
        for v in votes:
            if v["omega"] != 0.5:
                bad(f"{arm} {i}: omega {v['omega']}")
            if v["label"] != ("APPROVE" if v["vote"] == 1 else "REJECT") or v["vote"] not in (1, -1):
                bad(f"{arm} {i}: label/vote {v['label']}/{v['vote']}")
            prov, mod = ("claude_cli", "claude-opus-5-5") if claude else ("jev", "jev-latest")
            if (v["provider"], v["model"]) != (prov, mod):
                bad(f"{arm} {i}: {v['agent']} {v['provider']}/{v['model']}")
            want_hash = PANEL_HASH.get(v["agent"], "30698a20810c")
            if v["persona"] != want_hash:
                bad(f"{arm} {i}: persona hash {v['persona']}")
        lam, fired = 0.0, None
        for k, v in enumerate(votes):
            lam += v["omega"] * (LA if v["vote"] == 1 else LR)
            if fired is None and (lam >= A or lam <= B):
                fired = (k, "APPROVE" if lam >= A else "REJECT")
        # expected number of votes
        if standard:
            want_n = fired[0] + 1 if fired else 5
        else:
            want_n = 1
        if len(votes) != want_n:
            bad(f"{arm} {i}: {len(votes)} votes, boundary says {want_n} (fired={fired})")
        if fired:
            dec, conf, norm = fired[1], "HIGH", None
        else:
            w = [v["omega"] for v in votes]
            norm = sum(wi * v["vote"] for wi, v in zip(w, votes)) / sum(w)
            dec = "APPROVE" if norm >= th else "REJECT"
            conf = "MEDIUM" if abs(norm - th) >= 0.2 else "LOW"
        got = (r["decision"], r["confidence"], r["normalised_score"], r["sprt_lambda"], r["sprt_fired"])
        want = (dec, conf, None if norm is None else round(norm, 4), round(lam, 4), conf == "HIGH")
        if got != want:
            bad(f"{arm} {i}: record {got} vs recomputed {want}")
        n_checked += 1
print(f"SPRT/synthesis re-derived for {n_checked} records")


# ---------- Claude calls ----------
def parse_vote(text):
    fw = text.split()[0].upper().rstrip(".,:")
    if fw == "APPROVE":
        return 1
    if fw == "REJECT":
        return -1
    return 1 if re.search(r"\bAPPROVE\b", text, re.I) else -1


TAIL = "\n\n" + REPLY_FORMAT
models_seen, first_words, n_calls = {}, {}, {}
sha_by_id = {}
SUSPECT = re.compile(r"\b(git log|git show|blame|later (commit|fix)|subsequent commit|I (ran|searched|opened|read the file|checked the repo)|"
                     r"grep|tool|bash|the repository'?s? history|fixed (later|in a later))\b", re.I)
suspects = []
for arm in ("claude-one", "claude-standard"):
    n_calls[arm] = 0
    for i, r in recs[arm].items():
        calls = r["four"]["calls"]
        n_calls[arm] += len(calls)
        if r["four"]["provider"] != "claude_cli" or r["four"]["model"] != "claude-opus-5-5":
            bad(f"{arm} {i}: four provider/model {r['four']['provider']}/{r['four']['model']}")
        if any("error" in c for c in calls):
            bad(f"{arm} {i}: call with error {[c.get('error') for c in calls]}")
        if [c["agent"] for c in calls] != [v["agent"] for v in r["votes"]]:
            bad(f"{arm} {i}: calls {[c['agent'] for c in calls]} vs votes")
        for c, v in zip(calls, r["votes"]):
            models_seen[c["model"]] = models_seen.get(c["model"], 0) + 1
            reply = c["reply"]
            fw = reply.split()[0]
            first_words[fw] = first_words.get(fw, 0) + 1
            if fw not in ("APPROVE", "REJECT"):
                bad(f"{arm} {i} {c['agent']}: first word {fw!r}")
            if c["first_line"] != reply.split("\n", 1)[0][:200]:
                bad(f"{arm} {i} {c['agent']}: first_line mismatch")
            if not c.get("exact"):
                bad(f"{arm} {i} {c['agent']}: exact False")
            pv = parse_vote(reply)
            if not (pv == c["vote"] == v["vote"]):
                bad(f"{arm} {i} {c['agent']}: reply->{pv}, call {c['vote']}, record {v['vote']}")
            if c["chars"] != len(reply) and c["chars"] <= 2000:
                bad(f"{arm} {i} {c['agent']}: chars {c['chars']} vs reply {len(reply)}")
            reasoning = reply[reply.index("\n"):].strip() if "\n" in reply else ""
            if c["chars"] <= 2000:
                if reasoning != v["reasoning"]:
                    bad(f"{arm} {i} {c['agent']}: reasoning differs from reply")
            elif not v["reasoning"].startswith(reasoning[:1500]):
                bad(f"{arm} {i} {c['agent']}: reasoning prefix differs (truncated reply)")
            m = SUSPECT.search(v["reasoning"])
            if m:
                suspects.append((arm, i, c["agent"], m.group(0)))
            sha_by_id.setdefault(i, {}).setdefault((c["sent_sha"], c["sent_chars"]), []).append(f"{arm}/{c['agent']}")
print(f"Claude calls: {n_calls}; models {models_seen}; first words {first_words}")
multi = {i: v for i, v in sha_by_id.items() if len(v) != 1}
print(f"ids where Claude calls got more than one distinct message: {len(multi)} {list(multi)[:5]}")
for i, v in multi.items():
    bad(f"{i}: Claude messages differ across calls {list(v)}")
print(f"replies matching tool/history words: {len(suspects)}")
for s in suspects[:40]:
    print("   ", s)

# ---------- Jev ----------
RX = re.compile(r"^p\(APPROVE\)=(\d\.\d\d)  p\(REJECT\)=(\d\.\d\d)  confidence=(\d\.\d\d)  \[(.+?): decision model, no reasoning\]$")
state_chars = {}
decimals, argmax_off, cost = {}, [], 0.0
for arm in ("jev-one", "jev-standard"):
    for i, r in recs[arm].items():
        f = r["four"]
        cost += f.get("cost") or 0
        if f["models"] != ["typesafe/jev-1.14-20261014"]:
            bad(f"{arm} {i}: models {f['models']}")
        if sorted(f["round1"]) != sorted(v["agent"] for v in r["votes"]):
            bad(f"{arm} {i}: round1 {sorted(f['round1'])} vs votes")
        csum = 0.0
        for v in r["votes"]:
            a = f["round1"][v["agent"]]
            m = RX.match(v["reasoning"])
            if not m:
                bad(f"{arm} {i} {v['agent']}: reasoning {v['reasoning']!r}")
                continue
            pa, pr, cf, mdl = m.groups()
            if f"{a['p_reject']:.2f}" != pr:
                bad(f"{arm} {i} {v['agent']}: stored p_reject {a['p_reject']} vs text {pr}")
            if a["confidence"] is not None and f"{a['confidence']:.2f}" != cf:
                bad(f"{arm} {i} {v['agent']}: confidence {a['confidence']} vs {cf}")
            if a["choice"] != v["label"]:
                bad(f"{arm} {i} {v['agent']}: choice {a['choice']} vs vote {v['label']}")
            if abs(float(pa) + float(pr) - 1) > 0.011:
                bad(f"{arm} {i} {v['agent']}: p sum {pa}+{pr}")
            if (float(pr) > 0.5) != (a["choice"] == "REJECT"):
                argmax_off.append((arm, i, v["agent"], pr, a["choice"]))
            if mdl != "typesafe/jev-1.14-20261014":
                bad(f"{arm} {i}: text model {mdl}")
            u = a["usage"] or {}
            if (u.get("input_tokens"), u.get("output_tokens")) != (v["tokens_in"], v["tokens_out"]):
                bad(f"{arm} {i} {v['agent']}: tokens {u} vs {v['tokens_in']}/{v['tokens_out']}")
            csum += float(u.get("cost") or 0)
            nd = len(repr(a["p_reject"]).split(".")[-1]) if "." in repr(a["p_reject"]) else 0
            decimals[nd] = decimals.get(nd, 0) + 1
            state_chars.setdefault(i, set()).add(a["state_chars"])
        if abs(round(csum, 8) - f["cost"]) > 1e-9:
            bad(f"{arm} {i}: cost {f['cost']} vs sum {csum}")
print(f"Jev: decimals of stored p_reject {decimals}; choice != (p_reject>0.5): {len(argmax_off)} {argmax_off[:5]}")
for i, sc in state_chars.items():
    if len(sc) != 1:
        bad(f"{i}: Jev state_chars differ across seats {sc}")
# Claude message length = Jev state + reply format
for i in ids:
    if i in sha_by_id and i in state_chars:
        (sha, n), = sha_by_id[i].keys() if len(sha_by_id[i]) == 1 else [(None, None)]
        js = next(iter(state_chars[i]))
        if n != js + len(TAIL):
            bad(f"{i}: Claude sent {n} chars, Jev state {js} + {len(TAIL)}")
print(f"len(reply-format tail) = {len(TAIL)}")

# enrich_error / seconds agreement across arms
for i in ids:
    errs = {arm: recs[arm][i]["four"]["enrich_error"] for arm in ARMS if i in recs[arm]}
    if len(set(map(str, errs.values()))) != 1:
        bad(f"{i}: enrich_error differs {errs}")

# ---------- rebuild messages ----------
if REBUILD:
    import os
    sys.path.insert(0, str(EXP / "laya-five"))
    from run_five import INPUT_LABEL, PLAN, prepare  # noqa: E402  (sets WARF_HOME=laya-five)
    plan = {e["sha"]: e for e in map(json.loads, PLAN.open(encoding="utf-8"))}
    ok = 0
    for i in ids:
        s = sel[i]
        code, domain, context, err = prepare(plan[s["commit"]], s["file"])
        ctx = f"Project context:\n{context}\n\n" if context else ""
        state = f"Domain: {domain}\n\n{ctx}{INPUT_LABEL}:\n```\n{code}\n```"
        msg = state + TAIL
        sha = hashlib.sha256(msg.encode("utf-8")).hexdigest()[:16]
        (csha, cn), = sha_by_id[i].keys()
        js = next(iter(state_chars[i]))
        rec_err = recs["jev-one"][i]["four"]["enrich_error"]
        checks = {"domain": domain == s["domain"], "claude sha": sha == csha, "claude chars": len(msg) == cn,
                  "jev state chars": len(state) == js, "enrich_error": err == rec_err,
                  "state ends with fence": state.endswith("\n```")}
        if all(checks.values()):
            ok += 1
        else:
            bad(f"rebuild {i}: {checks}")
        if i in ids[:3]:
            print(f"  rebuild {i}: state {len(state)} chars, msg sha {sha}; record sha {csha}; tail ok {msg.endswith(REPLY_FORMAT)}")
    print(f"rebuild: {ok}/100 messages identical in sha256[:16] and length (Claude) and length (Jev)")
    print(f"WARF_HOME during rebuild: {os.environ.get('WARF_HOME')}")

# ---------- scores ----------
common = [i for i in ids if all(i in recs[a] for a in ARMS)]
reject = {a: {i: recs[a][i]["decision"] == "REJECT" for i in common} for a in ARMS}


def auc(score, sample):
    """Mann-Whitney via midranks (a different computation from the pair count)."""
    xs = sorted((score[i], i) for i in sample)
    ranks, k = {}, 0
    while k < len(xs):
        j = k
        while j + 1 < len(xs) and xs[j + 1][0] == xs[k][0]:
            j += 1
        for t in range(k, j + 1):
            ranks[xs[t][1]] = (k + j) / 2 + 1
        k = j + 1
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(ranks[i] for i in P) - len(P) * (len(P) + 1) / 2) / (len(P) * len(N))


def ba(rej, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(rej[i] for i in P) / len(P) + sum(not rej[i] for i in N) / len(N)) / 2


def rshare(r):
    return sum(v["vote"] == -1 for v in r["votes"]) / len(r["votes"])


scores = {
    "Claude, one agent (vote)": {i: float(reject["claude-one"][i]) for i in common},
    "WaRF Claude, -Lambda": {i: -recs["claude-standard"][i]["sprt_lambda"] for i in common},
    "WaRF Claude, REJECT-vote share": {i: rshare(recs["claude-standard"][i]) for i in common},
    "Jev, one agent, p(REJECT)": {i: recs["jev-one"][i]["four"]["round1"]["JEV"]["p_reject"] for i in common},
    "WaRF Jev, -Lambda": {i: -recs["jev-standard"][i]["sprt_lambda"] for i in common},
    "WaRF Jev, mean p(REJECT) of agents asked": {
        i: sum(a["p_reject"] for a in recs["jev-standard"][i]["four"]["round1"].values())
        / len(recs["jev-standard"][i]["four"]["round1"]) for i in common},
}
NAMES = {"claude-one": "Claude, one agent", "claude-standard": "WaRF Claude (5 personas)",
         "jev-one": "Jev, one agent", "jev-standard": "WaRF Jev (5 personas)"}
samples = {"all": common, "without 18": [i for i in common if i not in T18]}
rng = random.Random(4)
boots = {}
for name, sample in samples.items():
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    boots[name] = [[rng.choice(P) for _ in P] + [rng.choice(N) for _ in N] for _ in range(2000)]

out = [f"Reviews per arm: " + ", ".join(f"{a} {len(recs[a])}" for a in ARMS) + f"; scored on the {len(common)} all four have."]
for name, sample in samples.items():
    nP = sum(defect[i] for i in sample)
    out += ["", f"== {name}: {len(sample)} changes, {nP} later fixed, {len(sample) - nP} never fixed ==",
            "WaRF's verdict: balanced accuracy [95 %], REJECTs (later fixed), HIGH verdicts right"]
    for arm in ARMS:
        xs = sorted(ba(reject[arm], s) for s in boots[name])
        high = [i for i in sample if recs[arm][i]["confidence"] == "HIGH"]
        out.append(f"  {NAMES[arm]:<28} {ba(reject[arm], sample):.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]   "
                   f"REJECT {sum(reject[arm][i] for i in sample)} ({sum(reject[arm][i] and defect[i] for i in sample)})   "
                   f"HIGH {sum(reject[arm][i] == defect[i] for i in high)}/{len(high)}")
    out.append("Ranking: AUC [95 %]")
    for sn, sc in scores.items():
        xs = sorted(auc(sc, s) for s in boots[name])
        out.append(f"  {sn:<42} {auc(sc, sample):.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]")
    out.append("Differences in balanced accuracy, paired [95 %], share of resamples <= 0")
    for a1, a2 in (("claude-one", "jev-one"), ("claude-standard", "jev-standard"),
                   ("claude-standard", "claude-one"), ("jev-standard", "jev-one"), ("claude-one", "jev-standard")):
        xs = sorted(ba(reject[a1], s) - ba(reject[a2], s) for s in boots[name])
        d = ba(reject[a1], sample) - ba(reject[a2], sample)
        out.append(f"  {NAMES[a1]} - {NAMES[a2]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  {sum(x <= 0 for x in xs) / 2000:.3f}")
out += ["", "== The panels' seats (all 100) =="]
for arm in ("claude-standard", "jev-standard"):
    seats = {}
    for i in common:
        for v in recs[arm][i]["votes"]:
            seats.setdefault(v["agent"], []).append(v["vote"] == -1)
    stops = sum(len(recs[arm][i]["votes"]) < 5 for i in common)
    out.append(f"  {NAMES[arm]}: {stops} reviews stopped early; REJECT votes per seat (of the reviews it voted on): "
               + ", ".join(f"{a} {sum(s)}/{len(s)}" for a, s in seats.items()))
    one = arm.replace("standard", "one")
    out.append(f"    verdict equals the same model's one agent on {sum(reject[arm][i] == reject[one][i] for i in common)} of {len(common)}")
out += ["", f"Jev cost: ${cost:.4f}. Claude calls: " + ", ".join(f"{a} {n_calls[a]}" for a in ("claude-one", "claude-standard"))]

logged = (FOUR / "score.log").read_text(encoding="utf-8").rstrip("\n").split("\n")
diff = [(k, a, b) for k, (a, b) in enumerate(zip(out, logged)) if a != b]
print(f"\nscore.log: {len(logged)} lines, recomputed {len(out)}; differing lines: {len(diff)}")
for k, a, b in diff:
    print(f"  line {k + 1}\n    log:  {b}\n    mine: {a}")

# robustness: same intervals with another seed (not in score.log)
rng2 = random.Random(12345)
print("\nSeed check (seed 12345, 2000 resamples), all 100:")
P = [i for i in common if defect[i]]
N = [i for i in common if not defect[i]]
b2 = [[rng2.choice(P) for _ in P] + [rng2.choice(N) for _ in N] for _ in range(2000)]
for arm in ARMS:
    xs = sorted(ba(reject[arm], s) for s in b2)
    print(f"  BA {arm:<16} [{xs[49]:.3f}, {xs[1949]:.3f}]")
for sn, sc in scores.items():
    xs = sorted(auc(sc, s) for s in b2)
    print(f"  AUC {sn:<42} [{xs[49]:.3f}, {xs[1949]:.3f}]")

# score.json
sj = json.loads((FOUR / "score.json").read_text(encoding="utf-8"))
print(f"\nscore.json n = {sj['n']}")

print(f"\nPROBLEMS: {len(problems)}")
for p in problems[:200]:
    print("  ", p)
