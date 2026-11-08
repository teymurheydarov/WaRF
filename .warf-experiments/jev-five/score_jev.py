"""Score Jev (sessions_one, sessions_five, controls_*, repeat_one) against the git-history labels
of ../laya-five/selection.jsonl, side by side with Laya and Claude on the same 100 commits.
Pure Python: numpy's BLAS crashes in gs\\cf\\python.exe.

    python .warf-experiments/jev-five/score_jev.py"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAYA = HERE.parent / "laya-five"
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def load(path):
    return [json.loads(line) for line in path.open(encoding="utf-8")] if path.exists() else []


sel = [json.loads(line) for line in (LAYA / "selection.jsonl").open(encoding="utf-8")]
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
one = {r["jev"]["id"]: r for r in load(HERE / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in load(HERE / "sessions_five.jsonl")}
lfive = {r["five"]["id"]: r for r in load(LAYA / "sessions.jsonl")}
std = {r["jev"]["id"]: r for r in load(HERE / "sessions_standard.jsonl")}   # WaRF defaults, every agent on Jev


def auc(score, pos):
    P = [s for s, t in zip(score, pos) if t]
    N = [s for s, t in zip(score, pos) if not t]
    a = sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return a, math.sqrt(max(0.0, a * (1 - a) + (len(P) - 1) * (q1 - a * a) + (len(N) - 1) * (q2 - a * a)) / (len(P) * len(N)))


def paired_diff(s1, s2, pos, n=2000, seed=5):
    """AUC(s1) - AUC(s2) on the same items, 95 % interval from resampling items within each label."""
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        yy = [pos[i] for i in idx]
        d.append(auc([s1[i] for i in idx], yy)[0] - auc([s2[i] for i in idx], yy)[0])
    d.sort()
    return auc(s1, pos)[0] - auc(s2, pos)[0], d[int(0.025 * n)], d[int(0.975 * n) - 1]


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def sign_test(k, n):
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def pairs_won(score):
    """Matched pairs (rows 2k, 2k+1 = later fixed, never fixed) where the later-fixed change
    scores higher; a tie counts half."""
    return sum((score[2 * k] > score[2 * k + 1]) + 0.5 * (score[2 * k] == score[2 * k + 1]) for k in range(len(score) // 2))


def pj(r, rnd, agent):
    return r["jev"][rnd][agent]["p_reject"]


def final(block, agent):
    a = block["round2"].get(agent) or block["round1"][agent]
    return a["p_reject"], a["choice"]


rows = []          # (name, score list) for the summary table
print(f"\n  {len(sel)} commits, {sum(y)} later fixed (the five-Laya selection)")
if len(one) == len(sel):
    p1 = [pj(one[i], "round1", "JEV") for i in ids]
    rows.append(("Jev, one question", p1))
    models = sorted({m for r in one.values() for m in r["jev"]["models"]})
    print(f"  Jev answered as {', '.join(models)}; {len(set(p1))} distinct p(REJECT) values; "
          f"REJECT votes {sum(one[i]['jev']['round1']['JEV']['choice'] == 'REJECT' for i in ids)} of {len(ids)}")
if len(five) == len(sel):
    for a in AGENTS:
        rows.append((f"Jev {a}, Round 1", [pj(five[i], "round1", a) for i in ids]))
    rows.append(("Jev panel, mean p, Round 1", [sum(pj(five[i], "round1", a) for a in AGENTS) / 5 for i in ids]))
    rows.append(("Jev panel, mean p, final", [sum(final(five[i]["jev"], a)[0] for a in AGENTS) / 5 for i in ids]))
    rows.append(("Jev panel, REJECT votes, final", [sum(final(five[i]["jev"], a)[1] == "REJECT" for a in AGENTS) for i in ids]))
if len(std) == len(sel):
    rows.append(("Jev standard panel, mean p of agents asked", [sum(a["p_reject"] for a in std[i]["jev"]["round1"].values())
                                                              / len(std[i]["jev"]["round1"]) for i in ids]))
    rows.append(("Jev standard panel, WaRF's Lambda", [-std[i]["sprt_lambda"] for i in ids]))
    rows.append(("Jev standard panel, WaRF's decision", [float(std[i]["decision"] == "REJECT") for i in ids]))
laya1 = [s["p_single_laya"] for s in sel]
rows.append(("Laya, one question (sweep)", laya1))
if len(lfive) == len(sel):
    rows.append(("Laya panel, mean p, Round 1", [sum(lfive[i]["five"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids]))
    rows.append(("Laya panel, mean p, final", [sum(final(lfive[i]["five"], a)[0] for a in AGENTS) / 5 for i in ids]))
rows.append(("Claude, blinded", [s["p_claude"] for s in sel]))
rows.append(("patch characters", [s["patch_chars"] for s in sel]))

print(f"\n  {'':<34} {'AUC':>14} {'pairs won (of 50)':>18}")
out = {"auc": {}}
for name, score in rows:
    a, se = auc(score, y)
    out["auc"][name] = [a, se]
    print(f"  {name:<34} {a:>7.3f} ±{se:.3f} {pairs_won(score):>14.1f}")

score = dict(rows)
print("\n  paired differences, same commits (95 % interval, resampling commits within each label)")
out["diff"] = {}
for a_name, b_name in (("Jev, one question", "Laya, one question (sweep)"),
                       ("Jev panel, mean p, Round 1", "Laya panel, mean p, Round 1"),
                       ("Jev panel, mean p, final", "Laya panel, mean p, final"),
                       ("Jev panel, mean p, Round 1", "Jev, one question"),
                       ("Jev panel, mean p, final", "Jev panel, mean p, Round 1"),
                       ("Claude, blinded", "Jev, one question"),
                       ("Jev standard panel, mean p of agents asked", "Jev, one question"),
                       ("Jev standard panel, mean p of agents asked", "Jev panel, mean p, Round 1"),
                       ("Jev standard panel, mean p of agents asked", "Laya, one question (sweep)"),
                       ("Claude, blinded", "Jev standard panel, mean p of agents asked")):
    if a_name in score and b_name in score:
        d, lo, hi = paired_diff(score[a_name], score[b_name], y)
        out["diff"][f"{a_name} - {b_name}"] = [d, lo, hi]
        print(f"  {a_name + '  minus  ' + b_name:<70} {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")

for name, rs in (("Jev, one question", one), ("Jev panel", five), ("Jev standard panel", std)):
    if len(rs) == len(sel):
        dec = [rs[i]["decision"] == "REJECT" for i in ids]
        tp = sum(d and t for d, t in zip(dec, y))
        print(f"\n  WaRF's decision, {name}: REJECT on {sum(dec)} of {len(ids)} ({tp} later fixed, {sum(dec) - tp} never fixed); "
              f"balanced accuracy {auc([float(d) for d in dec], y)[0]:.3f}")
        conf = {}
        for i in ids:
            conf[(rs[i]["decision"], rs[i]["confidence"])] = conf.get((rs[i]["decision"], rs[i]["confidence"]), 0) + 1
        print(f"    by confidence: {', '.join(f'{d} {c}: {k}' for (d, c), k in sorted(conf.items()))}")

if "Jev, one question" in score:
    rng = random.Random(3)
    perm = []
    for _ in range(400):
        yy = y[:]
        rng.shuffle(yy)
        perm.append(auc(score["Jev, one question"], yy)[0])
    print(f"\n  shuffled labels: Jev one question, AUC {sum(perm) / len(perm):.3f} over {len(perm)} shuffles")
    print("  correlation of scores across the 100 commits:")
    names = [n for n in ("Jev, one question", "Jev panel, mean p, Round 1", "Laya, one question (sweep)",
                         "Laya panel, mean p, Round 1", "Claude, blinded") if n in score]
    print("  " + " " * 30 + "".join(f"{n[:12]:>14}" for n in names))
    for n1 in names:
        print(f"  {n1[:30]:<30}" + "".join(f"{corr(score[n1], score[n2]):>14.2f}" for n2 in names))

if len(five) == len(sel):
    D = [i for i in ids if len(five[i]["jev"]["round2"]) == 5]
    yd = [five[i]["jev"]["label"] == "REJECT" for i in D]
    m1 = [sum(pj(five[i], "round1", a) for a in AGENTS) / 5 for i in D]
    m2 = [sum(pj(five[i], "round2", a) for a in AGENTS) / 5 for i in D]
    print(f"\n  Jev debate, {len(D)} debated commits ({len(ids) - len(D)} stopped by the SPRT in Round 1):")
    if D:
        d, lo, hi = paired_diff(m2, m1, yd)
        print(f"    AUC of the mean p {auc(m1, yd)[0]:.3f} -> {auc(m2, yd)[0]:.3f} ({d:+.3f} [{lo:+.3f}, {hi:+.3f}])")
        toward = changed = 0
        for a in AGENTS:
            ch = [i for i in D if five[i]["jev"]["round1"][a]["choice"] != five[i]["jev"]["round2"][a]["choice"]]
            t = sum((five[i]["jev"]["round2"][a]["choice"] == "REJECT") == (five[i]["jev"]["label"] == "REJECT") for i in ch)
            toward, changed = toward + t, changed + len(ch)
            shift = sum(pj(five[i], "round2", a) - pj(five[i], "round1", a) for i in D) / len(D)
            print(f"    {a:<14} changed {len(ch):>3} votes ({t} toward the label), mean p shift {shift:+.3f}")
        if changed:
            print(f"    all agents: {toward} of {changed} changed votes toward the label, sign test p = {sign_test(toward, changed):.2g}")
    for a in AGENTS:
        v1 = sum(five[i]["jev"]["round1"][a]["choice"] == "REJECT" for i in ids)
        print(f"    {a:<14} REJECT votes Round 1 {v1}, mean p {sum(pj(five[i], 'round1', a) for i in ids) / len(ids):.3f}")

for arm, base, agents in (("one", one, ("JEV",)), ("five", five, AGENTS)):
    C = load(HERE / f"controls_{arm}.jsonl")
    if not C or len(base) != len(sel):
        continue
    print(f"\n  control, Jev {arm}: one line planted after the first added line of the never-fixed changes (Round 1)")
    for plant in ("null dereference", "BUG comment"):
        pairs = [(sum(pj(base[c["jev"]["id"]], "round1", a) for a in agents) / len(agents),
                  sum(pj(c, "round1", a) for a in agents) / len(agents)) for c in C if c["jev"]["plant"] == plant]
        if pairs:
            up = sum(after > before for before, after in pairs)
            down = sum(after < before for before, after in pairs)
            print(f"    {plant:<17} p(REJECT) {sum(b for b, _ in pairs) / len(pairs):.3f} -> {sum(x for _, x in pairs) / len(pairs):.3f}; "
                  f"rose in {up}, fell in {down}, same in {len(pairs) - up - down} of {len(pairs)}; "
                  f"sign test p = {sign_test(up, up + down) if up + down else 1:.2g}")
    if arm == "five":
        for plant in ("null dereference", "BUG comment"):
            cells = []
            for a in agents:
                pr = [(pj(base[c["jev"]["id"]], "round1", a), pj(c, "round1", a)) for c in C if c["jev"]["plant"] == plant]
                cells.append(f"{a} {sum(b for b, _ in pr) / len(pr):.2f}->{sum(x for _, x in pr) / len(pr):.2f}")
            print(f"    {plant:<17} " + ", ".join(cells))

R = {r["jev"]["id"]: r for r in load(HERE / "repeat_one.jsonl")}
if R and one:
    same = [(pj(one[i], "round1", "JEV"), pj(R[i], "round1", "JEV")) for i in R if i in one]
    exact = sum(a == b for a, b in same)
    flips = sum(one[i]["jev"]["round1"]["JEV"]["choice"] != R[i]["jev"]["round1"]["JEV"]["choice"] for i in R if i in one)
    print(f"\n  repeat: {exact} of {len(same)} answers identical when asked again; mean |difference| "
          f"{sum(abs(a - b) for a, b in same) / len(same):.3f}; votes flipped {flips}")
    out["repeat"] = {"identical": exact, "n": len(same), "flips": flips}

if len(std) == len(sel):
    asked = [len(std[i]["votes"]) for i in ids]
    print(f"\n  Jev standard panel (WaRF's default profile and review: no debate, early stopping on): agents asked per "
          f"review {', '.join(f'{k}: {asked.count(k)}' for k in sorted(set(asked)))}; "
          f"models {sorted({v['provider'] + '/' + v['model'] for i in ids for v in std[i]['votes']})}")
    first = [std[i]["votes"][0]["agent"] for i in ids]
    print(f"    first agent asked: {sorted(set(first))}; debate rounds: {sum(bool(std[i].get('debate')) for i in ids)}")

cost = sum(r["jev"]["cost"] for f in ("sessions_one", "sessions_five", "sessions_standard", "controls_one", "controls_five", "repeat_one")
           for r in load(HERE / f"{f}.jsonl"))
print(f"\n  OpenRouter cost of all recorded Jev requests: ${cost:.4f}")
(HERE / "score.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
