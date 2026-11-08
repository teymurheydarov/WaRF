"""Independent recompute of score.log and audit of the claude-standard records (does not import score_set.py).

    python -B audit.py
"""
import json
import math
import random
import re
from pathlib import Path

SET = Path(__file__).resolve().parents[2]
LOG = []


def say(s=""):
    print(s)


# ---------- WaRF vote-mode constants, written out from engine.py --------------------------------------
P1, P0, AE, BE = 0.80, 0.30, 0.05, 0.10
A = math.log((1 - BE) / AE)
B = math.log(BE / (1 - AE))
LA = math.log(P1 / P0)
LR = math.log((1 - P1) / (1 - P0))
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
SEATS = ["SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY"]
MODEL = "claude-opus-5-5"
INPUT_LABEL = "Patch under review (unified diff)"
REPLY_FORMAT = ("First line of your response must be exactly one word: APPROVE or REJECT.\n"
                "Subsequent lines: your reasoning.")

items = {}
for line in (SET / "items.jsonl").open(encoding="utf-8"):
    it = json.loads(line)
    items[it["id"]] = it
say(f"items: {len(items)}, bases {len({i['base'] for i in items.values()})}, "
    f"kinds {sorted({(i['kind'], i['answer']) for i in items.values()})}")


def load(arm):
    recs, files = {}, {}
    for p in sorted(SET.glob(f"{arm}.w*.jsonl")):
        for n, line in enumerate(p.open(encoding="utf-8")):
            r = json.loads(line)
            i = r["planted"]["id"]
            recs.setdefault(i, []).append(r)
            files.setdefault(i, []).append(f"{p.name}:{n + 1}")
    return recs, files


R1, F1 = load("claude")
R5, F5 = load("claude-standard")
say(f"claude: {sum(map(len, R1.values()))} records, {len(R1)} ids; dup ids {[i for i, v in R1.items() if len(v) > 1]}")
say(f"claude-standard: {sum(map(len, R5.values()))} records, {len(R5)} ids; dup ids {[i for i, v in R5.items() if len(v) > 1]}")
say(f"ids missing: one {sorted(set(items) - set(R1))}, five {sorted(set(items) - set(R5))}; "
    f"extra: {sorted((set(R1) | set(R5)) - set(items))}")
R1 = {i: v[0] for i, v in R1.items()}
R5 = {i: v[0] for i, v in R5.items()}
for arm, R in (("one", R1), ("five", R5)):
    bad = [i for i, r in R.items() if r["planted"]["kind"] != items[i]["kind"] or r["planted"]["base"] != items[i]["base"]
           or r["planted"].get("operator") != items[i]["operator"]
           or r["artifact"] != f"{items[i]['commit']}:{items[i]['file']}" or r["domain"] != items[i]["domain"]]
    say(f"{arm}: records whose kind/base/operator/artifact/domain disagree with items.jsonl: {bad}")

# ---------- 1. recompute score.log ----------------------------------------------------------------------
say("\n== recompute ==")
bases = sorted({it["base"] for it in items.values()})
bases = [b for b in bases if all(f"{b}:{k}" in R for R in (R1, R5) for k in ("clean", "planted"))]
say(f"bases reviewed by both arms: {len(bases)}")
rej = {"one": {i: r["decision"] == "REJECT" for i, r in R1.items()},
       "five": {i: r["decision"] == "REJECT" for i, r in R5.items()}}


def correct(arm, i):
    return rej[arm][i] == (items[i]["answer"] == "REJECT")


def ba(arm, bs):
    tp = sum(correct(arm, f"{b}:planted") for b in bs) / len(bs)
    tn = sum(correct(arm, f"{b}:clean") for b in bs) / len(bs)
    return (tp + tn) / 2


def pct(xs, q):           # same order statistic as score_set (index 49 / 1949 of 2000), plus an interpolated one
    return xs[q]


for arm in ("one", "five"):
    caught = sum(correct(arm, f"{b}:planted") for b in bases)
    passed = sum(correct(arm, f"{b}:clean") for b in bases)
    say(f"  {arm}: BA {ba(arm, bases):.4f}  planted caught {caught}/{len(bases)}  clean passed {passed}/{len(bases)}")

# bootstrap: two independent RNG schemes; seed 4 reproduces score_set's draw order, the others check stability
for label, seed in (("seed 4 (score_set's order)", 4), ("seed 12345", 12345), ("seed 2026", 2026)):
    rng = random.Random(seed)
    boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]
    for arm in ("one", "five"):
        xs = sorted(ba(arm, s) for s in boots)
        say(f"  {label}: {arm} BA 95% [{xs[49]:.3f}, {xs[1949]:.3f}] (2.5/97.5 order stats 50th/1950th of 2000)")
    ds = sorted(ba("five", s) - ba("one", s) for s in boots)
    le0 = sum(d <= 0 for d in ds) / len(ds)
    lt0 = sum(d < 0 for d in ds) / len(ds)
    say(f"  {label}: diff [{ds[49]:+.3f}, {ds[1949]:+.3f}], <=0 {le0:.2%}, <0 {lt0:.2%}")
# larger bootstrap
rng = random.Random(7)
boots = [[rng.choice(bases) for _ in bases] for _ in range(20000)]
ds = sorted(ba("five", s) - ba("one", s) for s in boots)
say(f"  20000 resamples seed 7: diff [{ds[499]:+.3f}, {ds[19499]:+.3f}], <=0 {sum(d <= 0 for d in ds) / len(ds):.2%}")

d = ba("five", bases) - ba("one", bases)
ids = [f"{b}:{k}" for b in bases for k in ("clean", "planted")]
only5 = [i for i in ids if correct("five", i) and not correct("one", i)]
only1 = [i for i in ids if correct("one", i) and not correct("five", i)]
n = len(only5) + len(only1)
k = min(len(only5), len(only1))
p = min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0
say(f"  five minus one {d:+.4f}; only five right {len(only5)}, only one right {len(only1)}, exact McNemar p {p:.4f}")
say(f"    only five: {only5}")
say(f"    only one:  {only1}")

say("  per plant kind (one / five):")
for op in sorted({items[f"{b}:planted"]["operator"] for b in bases}):
    bs = [b for b in bases if items[f"{b}:planted"]["operator"] == op]
    say(f"    {op:<12} {sum(correct('one', f'{b}:planted') for b in bs)}/{len(bs)}  "
        f"{sum(correct('five', f'{b}:planted') for b in bs)}/{len(bs)}")


def vstr(r):
    return "".join("R" if v["vote"] == -1 else "A" for v in r["votes"])


say("  missed plants:")
for b in bases:
    i = f"{b}:planted"
    if not (correct("one", i) and correct("five", i)):
        say(f"    {b:<34} {items[i]['operator']:<12} one {R1[i]['decision']}  five {R5[i]['decision']} {vstr(R5[i])}")
say("  clean rejected:")
for b in bases:
    i = f"{b}:clean"
    if rej["one"][i] or rej["five"][i]:
        say(f"    {b:<34} one {R1[i]['decision']:<8} five {R5[i]['decision']:<8} {vstr(R5[i])}")
splits = {}
for i in ids:
    key = (items[i]["kind"], len(R5[i]["votes"]), sum(v["vote"] == -1 for v in R5[i]["votes"]))
    splits[key] = splits.get(key, 0) + 1
say("  splits: " + ", ".join(f"{k}: {v}" for k, v in sorted(splits.items())))
say(f"  calls: one {sum(1 for i in ids if 'call' in R1[i]['planted'])}, five {sum(len(R5[i]['planted']['calls']) for i in ids)}")

# ---------- 2. audit claude-standard ---------------------------------------------------------------------


def parse(text):
    w = text.split()[0].upper().rstrip(".,:")
    if w == "APPROVE":
        return 1
    if w == "REJECT":
        return -1
    return 1 if re.search(r"\bAPPROVE\b", text, re.I) else -1


def expect_msg(it):
    ctx = f"Project context:\n{it['context']}\n\n" if it["context"] else ""
    return len(f"Domain: {it['domain']}\n\n{ctx}{INPUT_LABEL}:\n```\n{it['code']}\n```\n\n{REPLY_FORMAT}")


say("\n== audit claude-standard ==")
prob = {k: [] for k in ("decision", "lambda", "fired", "confidence", "norm", "theta", "order", "omega", "model",
                        "calls", "parse", "reasoning", "inexact", "short", "sent", "sent_vs_one", "provider")}
for i, r in sorted(R5.items()):
    it = items[i]
    votes, calls = r["votes"], r["planted"]["calls"]
    lam, dec, fired_at = 0.0, None, None
    for k_, v in enumerate(votes):
        lam += v["omega"] * (LA if v["vote"] == 1 else LR)
        if dec is None and (lam >= A or lam <= B):
            dec, fired_at = ("APPROVE" if lam >= A else "REJECT"), k_ + 1
    if dec is None:
        norm = sum(v["omega"] * v["vote"] for v in votes) / sum(v["omega"] for v in votes)
        dec = "APPROVE" if norm >= THETA[it["domain"]] else "REJECT"
        conf = "MEDIUM" if abs(norm - THETA[it["domain"]]) >= 0.2 else "LOW"
        if r.get("normalised_score") is None or abs(r["normalised_score"] - norm) > 1e-3:
            prob["norm"].append(i)
    else:
        conf = "HIGH"
        if fired_at != len(votes):
            prob["fired"].append((i, "boundary at", fired_at, "but", len(votes), "votes"))
    if dec != r["decision"]:
        prob["decision"].append((i, dec, r["decision"]))
    if conf != r["confidence"]:
        prob["confidence"].append((i, conf, r["confidence"]))
    if abs(lam - r["sprt_lambda"]) > 1e-3:
        prob["lambda"].append((i, round(lam, 4), r["sprt_lambda"]))
    if r["sprt_fired"] != (fired_at is not None):
        prob["fired"].append((i, "sprt_fired", r["sprt_fired"]))
    if r["theta"] != THETA[it["domain"]]:
        prob["theta"].append(i)
    names = [v["agent"] for v in votes]
    if names != SEATS[:len(names)]:
        prob["order"].append((i, names))
    if any(abs(v["omega"] - 0.5) > 1e-12 for v in votes):
        prob["omega"].append(i)
    if any(v["model"] != MODEL for v in votes) or any(c["model"] != MODEL for c in calls) \
            or r["planted"]["model"] != MODEL:
        prob["model"].append(i)
    if any(v["provider"] != "claude_cli" for v in votes) or r["planted"]["provider"] != "claude_cli":
        prob["provider"].append(i)
    if [c["agent"] for c in calls] != names:
        prob["calls"].append((i, [c["agent"] for c in calls], names))
    for v, c in zip(votes, calls):
        if parse(c["reply"]) != v["vote"]:
            prob["parse"].append((i, v["agent"]))
        rs = c["reply"][c["reply"].index("\n"):].strip() if "\n" in c["reply"] else ""
        if rs != v["reasoning"]:
            prob["reasoning"].append((i, v["agent"]))
        if not c["exact"]:
            prob["inexact"].append((i, v["agent"], c["reply"][:80]))
    # a seat skipped (timeout) leaves a review with < 5 votes that did not stop on a boundary
    if len(votes) < 5 and fired_at is None:
        prob["short"].append((i, len(votes)))
    if len(votes) == 5 and fired_at is not None and fired_at < 5:
        prob["short"].append((i, "5 votes after early boundary"))
    sc = {c["sent_chars"] for c in calls}
    if sc != {expect_msg(it)}:
        prob["sent"].append((i, sorted(sc), expect_msg(it)))
    if sc != {R1[i]["planted"]["call"]["sent_chars"]}:
        prob["sent_vs_one"].append((i, sorted(sc), R1[i]["planted"]["call"]["sent_chars"]))
for k_, v in prob.items():
    say(f"  {k_:<12} {len(v):>3}  {v[:6]}")

say("\n== audit one-Claude arm ==")
p1 = {"decision": [], "parse": [], "inexact": [], "model": [], "sent": [], "votes": []}
for i, r in sorted(R1.items()):
    c = r["planted"]["call"]
    if len(r["votes"]) != 1:
        p1["votes"].append(i)
    v = r["votes"][0]
    if parse(c["reply"]) != v["vote"]:
        p1["parse"].append(i)
    if r["decision"] != ("APPROVE" if v["vote"] == 1 else "REJECT"):
        p1["decision"].append(i)
    if not c["exact"]:
        p1["inexact"].append((i, c["reply"][:80]))
    if c["model"] != MODEL or v["model"] != MODEL or c["agent"] != "CLAUDE":
        p1["model"].append(i)
    if c["sent_chars"] != expect_msg(items[i]):
        p1["sent"].append((i, c["sent_chars"], expect_msg(items[i])))
for k_, v in p1.items():
    say(f"  {k_:<12} {len(v):>3}  {v[:6]}")

# ---------- 3. errors and the resume --------------------------------------------------------------------
say("\n== errors / resume ==")
errs = [json.loads(l) for l in (SET / "errors.jsonl").open(encoding="utf-8")]
say(f"errors.jsonl: {len(errs)} entries, arms {sorted({e['arm'] for e in errs})}, "
    f"times {min(e['at'] for e in errs)} .. {max(e['at'] for e in errs)}")
for e in errs:
    r = R5.get(e["id"])
    if r is None:
        say(f"  {e['id']}: NO RECORD")
        continue
    say(f"  {e['id']:<42} record {F5[e['id']]} created {r['created_at']} after error: {r['created_at'] > e['at']}  "
        f"votes {vstr(r)} calls {len(r['planted']['calls'])} decision {r['decision']} secs {r['planted']['seconds']}")
# chronology per file
for p in sorted(SET.glob("claude-standard.w*.jsonl")):
    ts = [json.loads(l)["created_at"] for l in p.open(encoding="utf-8")]
    later = [t for t in ts if t > max(e["at"] for e in errs)]
    say(f"  {p.name}: {len(ts)} records, first {ts[0]}, last {ts[-1]}, monotone {ts == sorted(ts)}, "
        f"after last error {len(later)}")
for p in sorted(SET.glob("claude.w*.jsonl")):
    ts = [json.loads(l)["created_at"] for l in p.open(encoding="utf-8")]
    say(f"  {p.name}: {len(ts)} records, first {ts[0]}, last {ts[-1]}, monotone {ts == sorted(ts)}")
# early records (before the main runs)
all5 = sorted((r["created_at"], i) for i, r in R5.items())
all1 = sorted((r["created_at"], i) for i, r in R1.items())
say(f"  five earliest: {all5[:10]}")
say(f"  one earliest: {all1[:8]}")
secs = sorted((r["planted"]["seconds"], i, len(r["votes"])) for i, r in R5.items())
say(f"  five slowest reviews: {secs[-5:]}")
say(f"  five records with < 5 votes: {sorted(collections_count := {})}" if False else "")
cnt = {}
for r in R5.values():
    cnt[len(r["votes"])] = cnt.get(len(r["votes"]), 0) + 1
say(f"  five: votes per record {cnt}")
