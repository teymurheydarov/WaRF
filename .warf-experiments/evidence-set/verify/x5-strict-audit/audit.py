"""Independent recompute and audit of score_all.log and the claude-strict / claude-x5 arms.

Does not import score_all.py, run_planted.py or warf. Constants it needs from those files
(STRICT_PERSONA, DEFAULT_PERSONA, the engine's SPRT constants, the label classes) are read with ast
from the source text, never executed. Pure Python, read-only except this folder's audit.log.

    python -B verify/x5-strict-audit/audit.py
"""
import ast
import difflib
import hashlib
import itertools
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
EXP = SET.parent
ROOT = EXP.parent
out = []


def say(s=""):
    out.append(str(s))
    print(s)


def const(path, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def phash(text):
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


STRICT = const(EXP / "planted" / "run_planted.py", "STRICT_PERSONA")
DEFAULT = const(ROOT / "tools" / "run_laya_sweep.py", "DEFAULT_PERSONA")
P1, P0, AE, BE = (const(ROOT / "warf" / "engine.py", n) for n in ("P1", "P0", "ALPHA_ERR", "BETA_ERR"))
THETA = const(ROOT / "warf" / "engine.py", "THETA")
A, B = math.log((1 - BE) / AE), math.log(BE / (1 - AE))
LLR_A, LLR_R = math.log(P1 / P0), math.log((1 - P1) / (1 - P0))
say(f"hash(STRICT_PERSONA) {phash(STRICT)}  hash(DEFAULT_PERSONA) {phash(DEFAULT)}  A {A:.4f} B {B:.4f} "
    f"LLR +{LLR_A:.4f}/{LLR_R:.4f}")

# label classes: score_all.py vs verify/critic/rescore.py, both read as text
sa = Path(SET / "score_all.py").read_text(encoding="utf-8")
rs = Path(SET / "verify" / "critic" / "rescore.py").read_text(encoding="utf-8")
CLS = {}
for name in ("REAL", "DEBATABLE", "FALSE"):
    m1 = re.search(name + r' = set\("([^"]+)"\s*"?([^"]*)"?\.split\(\)\)', sa)
    m2 = re.search(name + r' = "([^"]+)"\.split\(\)', rs)
    s1, s2 = set((m1.group(1) + m1.group(2)).split()), set(m2.group(1).split())
    CLS[name] = s2
    say(f"class {name}: rescore.py {len(s2)}, score_all.py {len(s1)}, identical {s1 == s2}")

items = {it["id"]: it for it in map(json.loads, (SET / "items.jsonl").open(encoding="utf-8"))}
ARMS = ["claude", "claude-strict", "claude-x5", "claude-standard"]
recs = {}
for a in ARMS:
    recs[a] = {}
    for p in sorted(SET.glob(f"{a}.w*.jsonl")):
        for ln, line in enumerate(p.open(encoding="utf-8"), 1):
            r = json.loads(line)
            i = r["planted"]["id"]
            assert i not in recs[a], (a, i)
            it = items[i]
            assert (r["planted"]["base"], r["planted"]["kind"], r["planted"].get("operator")) == \
                (it["base"], it["kind"], it.get("operator")), (a, i)
            assert r["artifact"] == f"{it['commit']}:{it['file']}" and r["domain"] == it["domain"], (a, i)
            r["_file"] = f"{p.name}:{ln}"
            recs[a][i] = r
    say(f"{a}: {len(recs[a])} records, all ids in items {set(recs[a]) <= set(items)}, "
        f"all items covered {set(recs[a]) == set(items)}, profile {Counter(r['profile'] for r in recs[a].values())}")
say(f"domains in items: {Counter(it['domain'] for it in items.values())}")

ids = sorted(items)
bases = sorted({it["base"] for it in items.values()})
rej = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in ARMS}


def kind(i):
    return items[i]["kind"]


def short(i):
    return items[i]["base"].split(":")[0]


# ---------------------------------------------------------------- score_all.log recompute
def is_defect(i, defect):
    return kind(i) == "planted" or short(i) in defect


def bal(a, bs, defect):
    tp = fn = tn = fp = 0
    for b in bs:
        for k in ("clean", "planted"):
            i = f"{b}:{k}"
            if is_defect(i, defect):
                tp += rej[a][i]; fn += not rej[a][i]
            else:
                tn += not rej[a][i]; fp += rej[a][i]
    return 0.5 * (tp / (tp + fn) + tn / (tn + fp))


def binom_two_sided(k, n):
    if n == 0:
        return 1.0
    lo = min(k, n - k)
    p = sum(math.comb(n, j) for j in range(lo + 1)) / 2 ** n
    return min(1.0, 2 * p)


NAMES = {"claude": "one Claude", "claude-strict": "one Claude, strict bar", "claude-x5": "same question x5",
         "claude-standard": "WaRF five personas"}
rng = random.Random(4)                     # same seed and draw order as score_all.py, to compare intervals
boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]
REAL, DEB, FAL = CLS["REAL"], CLS["DEBATABLE"], CLS["FALSE"]
say(f"\n{len(bases)} bases")
for lname, defect in (("labels as given", set()), ("real", REAL), ("real + debatable", REAL | DEB)):
    say(f"\n== {lname} ==")
    for a in ARMS:
        cr = [b for b in bases if rej[a][f"{b}:clean"]]
        c = [sum(b.split(":")[0] in s for b in cr) for s in (REAL, DEB, FAL)]
        caught = sum(rej[a][f"{b}:planted"] for b in bases)
        say(f"  {NAMES[a]:<25} {bal(a, bases, defect):.3f}   {caught}/{len(bases)}   clean rejected {len(cr)} "
            f"({c[0]}/{c[1]}/{c[2]}/{len(cr) - sum(c)})")
    for a1, a2 in (("claude-standard", "claude"), ("claude-strict", "claude"), ("claude-x5", "claude"),
                   ("claude-standard", "claude-strict"), ("claude-standard", "claude-x5")):
        d = bal(a1, bases, defect) - bal(a2, bases, defect)
        ds = sorted(bal(a1, s, defect) - bal(a2, s, defect) for s in boots)
        ok1 = {i: rej[a1][i] == is_defect(i, defect) for i in ids}
        ok2 = {i: rej[a2][i] == is_defect(i, defect) for i in ids}
        k1 = sum(ok1[i] and not ok2[i] for i in ids)
        k2 = sum(ok2[i] and not ok1[i] for i in ids)
        le0 = sum(x <= 0 for x in ds) / len(ds)
        say(f"  {NAMES[a1]} - {NAMES[a2]}: {d:+.3f} [{ds[49]:+.3f}, {ds[1949]:+.3f}] (2.5/97.5% of 2000; "
            f"<=0 in {le0:.1%})  only first {k1}, only second {k2}, McNemar p {binom_two_sided(k1, k1 + k2):.3f}")
say("\n== clean items rejected by a new arm but never classed ==")
for a in ("claude-strict", "claude-x5"):
    say(f"  {NAMES[a]}: {[b for b in bases if rej[a][f'{b}:clean'] and b.split(':')[0] not in REAL | DEB | FAL]}")
say("\nclaude-strict clean rejects outside one Claude's 25: "
    f"{[b for b in bases if rej['claude-strict'][f'{b}:clean'] and not rej['claude'][f'{b}:clean']]}")
say("claude-x5 clean rejects outside one Claude's 25: "
    f"{[b for b in bases if rej['claude-x5'][f'{b}:clean'] and not rej['claude'][f'{b}:clean']]}")
say("planted missed per arm: " + "; ".join(f"{a} {[b for b in bases if not rej[a][f'{b}:planted']]}" for a in ARMS))


# ---------------------------------------------------------------- claude-x5 record audit
def first_word(t):
    """WaRF's _parse_vote (orchestrator.py) replayed: the first word, else any APPROVE in the text."""
    w = t.split()[0].upper().rstrip(".,:")
    if w in ("APPROVE", "REJECT"):
        return w
    return "APPROVE" if re.search(r"\bAPPROVE\b", t, re.IGNORECASE) else "REJECT"


say("\n== claude-x5 records ==")
problems = []
for i in ids:
    r = recs["claude-x5"][i]
    v, c = r["votes"], r["planted"]["calls"]
    n = len(v)
    names = [x["agent"] for x in v]
    if len(c) != n:
        problems.append((i, "calls != votes"))
    if names != [f"CLAUDE-{k}" for k in range(1, 6)][:n] and n == 5:
        problems.append((i, f"seat order {names}"))
    if [x["agent"] for x in c] != names:
        problems.append((i, "call agent names != vote names"))
    if {x["persona"] for x in v} != {phash(DEFAULT)}:
        problems.append((i, f"persona {set(x['persona'] for x in v)}"))
    if {(x["provider"], x["model"]) for x in v} | {("claude_cli", x["model"]) for x in c} != {("claude_cli", "claude-opus-5-5")}:
        problems.append((i, "provider/model"))
    if {x["omega"] for x in v} != {0.5}:
        problems.append((i, f"omega {set(x['omega'] for x in v)}"))
    if len({x["sent_chars"] for x in c}) != 1:
        problems.append((i, f"sent_chars differ between seats {[x['sent_chars'] for x in c]}"))
    for x, y in zip(v, c):
        fw = first_word(y["reply"])
        if fw != x["label"] or (x["vote"] == 1) != (x["label"] == "APPROVE"):
            problems.append((i, f"{x['agent']} reply starts {fw!r}, vote {x['label']}, exact {y['exact']}"))
    # WaRF vote mode replayed: sequential SPRT, stop at the first boundary, else weighted mean vs theta
    lam, fired, stop_at = 0.0, None, None
    for k, x in enumerate(v, 1):
        lam += x["omega"] * (LLR_A if x["vote"] == 1 else LLR_R)
        if lam >= A - 1e-12:
            fired, stop_at = "APPROVE", k; break
        if lam <= B + 1e-12:
            fired, stop_at = "REJECT", k; break
    if stop_at is not None and stop_at != n:
        problems.append((i, f"boundary at seat {stop_at} but {n} seats asked"))
    if fired:
        want, conf = fired, "HIGH"
    else:
        th = THETA[r["domain"]]
        norm = sum(x["omega"] * x["vote"] for x in v) / sum(x["omega"] for x in v)
        want = "APPROVE" if norm >= th else "REJECT"
        conf = "MEDIUM" if abs(norm - th) >= 0.2 else "LOW"
        if r["normalised_score"] is None or abs(r["normalised_score"] - norm) > 1e-3:
            problems.append((i, f"normalised {r['normalised_score']} vs {norm}"))
        if n != 5:
            say(f"  {i}: {n} seats {names}, no boundary (lambda {lam:+.4f}), synthesis {want}/{conf}, "
                f"record {r['decision']}/{r['confidence']}, seconds {r['planted']['seconds']}, {r['_file']}, "
                f"created {r['created_at']}")
    if (want, conf) != (r["decision"], r["confidence"]) or abs(round(lam, 4) - r["sprt_lambda"]) > 1e-4 \
            or r["sprt_fired"] != bool(fired) or r["theta"] != THETA[r["domain"]]:
        problems.append((i, f"decision {r['decision']}/{r['confidence']} lam {r['sprt_lambda']} vs {want}/{conf} {lam:.4f}"))
say(f"  x5 problems: {len(problems)} {problems[:10]}")
say(f"  x5 shapes (kind, seats, REJECTs, decision): "
    f"{sorted(Counter((kind(i), len(recs['claude-x5'][i]['votes']), sum(x['vote'] == -1 for x in recs['claude-x5'][i]['votes']), recs['claude-x5'][i]['decision']) for i in ids).items())}")
say(f"  x5 calls total {sum(len(recs['claude-x5'][i]['planted']['calls']) for i in ids)}; "
    f"standard calls {sum(len(recs['claude-standard'][i]['planted']['calls']) for i in ids)}")
say(f"  x5 errors in errors.jsonl: {sum(json.loads(l)['arm'] == 'claude-x5' for l in (SET / 'errors.jsonl').open(encoding='utf-8'))}, "
    f"strict errors: {sum(json.loads(l)['arm'] == 'claude-strict' for l in (SET / 'errors.jsonl').open(encoding='utf-8'))}")

# where would a single 5th seat take the 4-seat no-boundary records?
for i in ids:
    v = recs["claude-x5"][i]["votes"]
    lam = sum(x["omega"] * (LLR_A if x["vote"] == 1 else LLR_R) for x in v)
    if len(v) == 4 and B < lam < A:
        for extra in (1, -1):
            vv = [x["vote"] for x in v] + [extra]
            norm = sum(vv) / 5
            say(f"  {i}: 5th seat {'APPROVE' if extra == 1 else 'REJECT'} -> mean {norm:+.2f} -> "
                f"{'APPROVE' if norm >= THETA[recs['claude-x5'][i]['domain']] else 'REJECT'}")
        sec = sorted((recs['claude-x5'][j]['planted']['seconds'], j) for j in ids)
        say(f"  its seconds {recs['claude-x5'][i]['planted']['seconds']} (rank {[j for _, j in sec].index(i) + 1} of 100); "
            f"x5 seconds median {sec[50][0]}, max {sec[-1]}")
        # per-seat time for the other 5-seat records of the same worker, for scale
        f = recs['claude-x5'][i]['_file'].split(':')[0]
        same = [recs['claude-x5'][j] for j in ids if recs['claude-x5'][j]['_file'].startswith(f) and j != i]
        per = sorted(x['planted']['seconds'] / len(x['votes']) for x in same)
        say(f"  same worker file {f}: seconds per seat median {per[len(per) // 2]:.1f}, max {per[-1]:.1f}")
        # neighbouring records in time on the same worker
        order = sorted(same + [recs['claude-x5'][i]], key=lambda x: x['created_at'])
        k = [x['planted']['id'] for x in order].index(i)
        for x in order[max(0, k - 2):k + 3]:
            say(f"    {x['created_at']} {x['planted']['id']} seats {len(x['votes'])} seconds {x['planted']['seconds']}")

# ---------------------------------------------------------------- claude-strict record audit
say("\n== claude-strict records ==")
sp = []
for i in ids:
    r = recs["claude-strict"][i]
    v, c = r["votes"], r["planted"].get("call")
    if len(v) != 1 or c is None or "calls" in r["planted"]:
        sp.append((i, "shape")); continue
    if v[0]["persona"] != phash(STRICT):
        sp.append((i, f"persona {v[0]['persona']}"))
    if (v[0]["provider"], v[0]["model"], c["model"]) != ("claude_cli", "claude-opus-5-5", "claude-opus-5-5"):
        sp.append((i, "model"))
    if first_word(c["reply"]) != r["decision"] or v[0]["label"] != r["decision"]:
        sp.append((i, f"reply {first_word(c['reply'])} vs decision {r['decision']}"))
    norm = v[0]["vote"]
    want = "APPROVE" if norm >= THETA[r["domain"]] else "REJECT"
    if want != r["decision"]:
        sp.append((i, "synthesis"))
say(f"  strict problems: {len(sp)} {sp[:10]}; persona hashes {Counter(recs['claude-strict'][i]['votes'][0]['persona'] for i in ids)}")
say(f"  claude arm persona hashes {Counter(recs['claude'][i]['votes'][0]['persona'] for i in ids)}")

# ---------------------------------------------------------------- same message across arms
say("\n== same message (sent_chars) across arms ==")
sc = {}
for i in ids:
    sc[i] = {"claude": recs["claude"][i]["planted"]["call"]["sent_chars"],
             "strict": recs["claude-strict"][i]["planted"]["call"]["sent_chars"],
             "x5": {x["sent_chars"] for x in recs["claude-x5"][i]["planted"]["calls"]},
             "standard": {x["sent_chars"] for x in recs["claude-standard"][i]["planted"]["calls"]}}
say(f"  strict == claude on {sum(s['strict'] == s['claude'] for s in sc.values())}/100; "
    f"x5 seats == claude on {sum(s['x5'] == {s['claude']} for s in sc.values())}/100; "
    f"standard seats == claude on {sum(s['standard'] == {s['claude']} for s in sc.values())}/100")
# the expected length from the item: Domain/context/label/code + REPLY_FORMAT, rebuilt from WaRF's template
INPUT_LABEL = const(ROOT / "tools" / "run_laya_sweep.py", "INPUT_LABEL")
REPLY_FORMAT = const(ROOT / "warf" / "orchestrator.py", "REPLY_FORMAT")
match = 0
for i in ids:
    it = items[i]
    ctx = f"Project context:\n{it['context']}\n\n" if it["context"] else ""
    msg = f"Domain: {it['domain']}\n\n{ctx}{INPUT_LABEL}:\n```\n{it['code']}\n```\n\n{REPLY_FORMAT}"
    match += len(msg) == sc[i]["claude"] == sc[i]["strict"] and sc[i]["x5"] == {len(msg)}
say(f"  INPUT_LABEL {INPUT_LABEL!r}; rebuilt message length == claude == strict == every x5 seat on {match}/100")

# ---------------------------------------------------------------- agreement and repeat variation
say("\n== agreement ==")
x5v = {i: [x["vote"] for x in recs["claude-x5"][i]["votes"]] for i in ids}
say(f"  x5 unanimous among seats asked: {sum(len(set(v)) == 1 for v in x5v.values())}/100")
say(f"  x5 unanimous, items with all 5 seats asked: {sum(len(set(v)) == 1 for v in x5v.values() if len(v) == 5)}"
    f"/{sum(len(v) == 5 for v in x5v.values())}; with 4 seats: {sum(len(set(v)) == 1 for v in x5v.values() if len(v) == 4)}"
    f"/{sum(len(v) == 4 for v in x5v.values())}")
pair = Counter()
pairn = Counter()
for i in ids:
    for s1, s2 in itertools.combinations(range(len(x5v[i])), 2):
        pairn[(s1, s2)] += 1
        pair[(s1, s2)] += x5v[i][s1] == x5v[i][s2]
say(f"  x5 pairwise seat agreement over pairs asked: {sum(pair.values())}/{sum(pairn.values())} "
    f"= {sum(pair.values()) / sum(pairn.values()):.3f}")
for kk in ("clean", "planted"):
    a_ = n_ = 0
    for i in ids:
        if kind(i) != kk:
            continue
        for s1, s2 in itertools.combinations(range(len(x5v[i])), 2):
            n_ += 1; a_ += x5v[i][s1] == x5v[i][s2]
    say(f"    {kk}: {a_}/{n_} = {a_ / n_:.3f}")
one = {i: -1 if rej["claude"][i] else 1 for i in ids}
seat = {i: {x["agent"]: x["vote"] for x in recs["claude-x5"][i]["votes"]} for i in ids}
named = [i for i in ids if "CLAUDE-1" in seat[i]]
say(f"  CLAUDE-1 (by name) == one Claude: {sum(seat[i]['CLAUDE-1'] == one[i] for i in named)}/{len(named)} items where CLAUDE-1 voted; "
    f"differ on {[i for i in named if seat[i]['CLAUDE-1'] != one[i]]}")
for k in range(1, 6):
    nm = f"CLAUDE-{k}"
    asked = [i for i in ids if nm in seat[i]]
    say(f"  {nm} == one Claude on {sum(seat[i][nm] == one[i] for i in asked)}/{len(asked)} asked")
say("  (score_all.py's 'first x5 seat' is votes[0], which on the 4-seat no-boundary item is CLAUDE-2)")
s1eq = sum(x5v[i][0] == one[i] for i in ids)
say(f"  votes[0] == one Claude: {s1eq}/100; differ on {[(i, x5v[i][0], one[i]) for i in ids if x5v[i][0] != one[i]]}")
say(f"  x5 verdict == one Claude: {sum(rej['claude-x5'][i] == rej['claude'][i] for i in ids)}/100; "
    f"x5 verdict == strict: {sum(rej['claude-x5'][i] == rej['claude-strict'][i] for i in ids)}/100; "
    f"strict == one Claude: {sum(rej['claude-strict'][i] == rej['claude'][i] for i in ids)}/100")
# Cohen's kappa seat 1 vs one Claude
po = s1eq / 100
pa1 = sum(x5v[i][0] == -1 for i in ids) / 100
pa2 = sum(one[i] == -1 for i in ids) / 100
pe = pa1 * pa2 + (1 - pa1) * (1 - pa2)
say(f"  votes[0] vs one Claude kappa {(po - pe) / (1 - pe):.3f} (seat1 REJECT rate {pa1:.2f}, one Claude {pa2:.2f})")
# probability of reject per clean item (pooling x5 seats + one Claude)
mixed = [i for i in ids if len(set(x5v[i] + [one[i]])) > 1]
say(f"  items where the 5 x5 seats + one Claude are not all the same: {len(mixed)}: "
    + ", ".join(f"{i} x5={''.join('R' if x == -1 else 'A' for x in x5v[i])} one={'R' if one[i] == -1 else 'A'}" for i in mixed))

say("\n== do repeated identical calls differ at all? (reply texts) ==")
replies = {i: [x["reply"] for x in recs["claude-x5"][i]["planted"]["calls"]] for i in ids}
ident_pairs = sum(a == b for i in ids for a, b in itertools.combinations(replies[i], 2))
npairs = sum(1 for i in ids for _ in itertools.combinations(replies[i], 2))
say(f"  byte-identical reply pairs within an item: {ident_pairs}/{npairs}")
same1 = sum(replies[i][0] == recs["claude"][i]["planted"]["call"]["reply"] for i in ids)
say(f"  x5 seat 1 reply byte-identical to one Claude's reply: {same1}/100")
anyseat = sum(recs["claude"][i]["planted"]["call"]["reply"] in replies[i] for i in ids)
say(f"  one Claude's reply byte-identical to any x5 seat: {anyseat}/100")
ratios = []
for i in ids:
    for a, b in itertools.combinations(replies[i], 2):
        ratios.append(difflib.SequenceMatcher(None, a, b, autojunk=False).quick_ratio())
ratios.sort()
say(f"  difflib quick_ratio between seat replies of one item: min {ratios[0]:.2f}, median {ratios[len(ratios) // 2]:.2f}, "
    f"max {ratios[-1]:.2f} (quick_ratio is an upper bound on character overlap)")
lens = [len(t) for i in ids for t in replies[i]]
say(f"  reply length chars: min {min(lens)}, median {sorted(lens)[len(lens) // 2]}, max {max(lens)}")
fl = Counter(len({t.splitlines()[2] if len(t.splitlines()) > 2 else '' for t in replies[i]}) for i in ids)
say(f"  distinct third lines across an item's seats (count of items by #distinct): {sorted(fl.items())}")

(HERE / "audit.log").write_text("\n".join(out) + "\n", encoding="utf-8")
