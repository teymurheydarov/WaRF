"""
Does WaRF's panel beat a single agent in WaRF's own logs?

Stored data only: no model is asked, and nothing outside this folder is written.
Reads:
  .warf/sessions.jsonl               the labelled corpus: 62 developer labels (2026-06-20 to
                                     08-03), Claude Haiku 4.5, weights learned as it went,
                                     early stopping on, pools of 1 to 5 agents
  .warf-experiments/sessions.jsonl   the persona experiment: the 12 reference files, every agent
                                     votes, claude-haiku-4-5 through the CLI (2026-09-19/20)
  ../jev-five/sessions_five.jsonl, ../laya-five/sessions.jsonl
                                     Round-1 votes, for WaRF's clone rule only
Writes single_vs_panel.log next to this file.

    python .warf-experiments/old-logs/single_vs_panel.py
"""
import collections
import json
import math
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from _groundtruth import corpus_truth, truth_for          # noqa: E402
from compare_pools import load_pool, uniform_replay        # noqa: E402
from warf.engine import synthesis                          # noqa: E402

PERSONAS = ("AUDITOR", "ADVOCATE", "SKEPTIC", "BOUNDARY", "TEST-FOCUSED")
out = []


def say(s=""):
    out.append(s)
    print(s)


def x_of(label):
    return 1 if label == "APPROVE" else -1


def sign_p(b, c):
    """Exact two-sided sign test on b against c discordant items."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def bal(pairs):
    """Balanced accuracy of (prediction, truth) pairs: mean recall over the labels present."""
    by = collections.defaultdict(list)
    for p, t in pairs:
        by[t].append(p == t)
    rec = [sum(v) / len(v) for v in by.values()]
    return sum(rec) / len(rec)


HEAD = (f"  {'':<38}{'n':>4}{'right':>7}{'bal.acc':>9}"
        f"   | WaRF on the same: right  bal.acc  WaRF-only / agent-only right")


def row(name, pairs, panel=None):
    """pairs: (prediction, truth) per item; panel: WaRF's (prediction, truth) on the same items."""
    n, k = len(pairs), sum(p == t for p, t in pairs)
    s = f"  {name:<38}{n:>4}{k:>7}{bal(pairs):>9.2f}"
    if panel is not None:
        kp = sum(p == t for p, t in panel)
        b = sum(pp == t != p for (p, t), (pp, _) in zip(pairs, panel))     # WaRF right, agent wrong
        c = sum(p == t != pp for (p, t), (pp, _) in zip(pairs, panel))     # agent right, WaRF wrong
        s += f"   | {kp:>13}/{n:<4}{bal(panel):>7.2f}   {b:>5} / {c:<3} sign p {sign_p(b, c):.2f}"
    say(s)


def read(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


truths = corpus_truth()

# ---------------------------------------------------------------------------------------------
corpus = read(ROOT / ".warf" / "sessions.jsonl")
lab = [s for s in corpus if s.get("oracle")]
assert {s["decision"] for s in lab} <= {"APPROVE", "REJECT"}
say("=" * 110)
say("1. The labelled corpus (.warf/sessions.jsonl): the sessions behind the README's evidence")
say("=" * 110)
say(f"  {len(lab)} sessions with a developer label "
    f"({sum(s['oracle']['x_star'] == 1 for s in lab)} APPROVE, {sum(s['oracle']['x_star'] == -1 for s in lab)} REJECT), "
    f"{min(s['created_at'] for s in lab)[:10]} to {max(s['created_at'] for s in lab)[:10]}; pool sizes "
    + ", ".join(f"{k} agents x{v}" for k, v in sorted(collections.Counter(len(s['votes']) for s in lab).items())))
say("  Agents are asked heaviest omega first, so the first agent asked is the specification's")
say("  'single highest-weighted agent'. An agent asked later voted only where the review had not stopped.")


def current(s):
    t = truth_for(s["artifact"], truths)
    return t.x_star if t else s["oracle"]["x_star"]


for tname, truth in (("the label stored with each session (as the README scores it)", lambda s: s["oracle"]["x_star"]),
                     ("the current label per file (tools/_groundtruth.py)", current)):
    say(f"\n  Truth: {tname}")
    say(HEAD)
    panel = {s["session_id"]: (x_of(s["decision"]), truth(s)) for s in lab}
    row("WaRF's decision", list(panel.values()))
    row("first agent asked", [(s["votes"][0]["vote"], truth(s)) for s in lab],
        [panel[s["session_id"]] for s in lab])
    for a in PERSONAS:
        ss = [s for s in lab if any(v["agent"] == a for v in s["votes"])]
        row(f"{a}, where it voted", [(next(v["vote"] for v in s["votes"] if v["agent"] == a), truth(s)) for s in ss],
            [panel[s["session_id"]] for s in ss])
    row("always APPROVE", [(1, truth(s)) for s in lab])
    uni = [(x_of(uniform_replay(dict(s))[0]), truth(s)) for s in lab]
    row("WaRF, same votes, uniform weights", uni, list(panel.values()))

say("\n  By WaRF's confidence (stored labels): sessions, WaRF right, first agent asked right")
for band in ("HIGH", "MEDIUM", "LOW"):
    ss = [s for s in lab if s["confidence"] == band]
    say(f"    {band:<7}{len(ss):>4}{sum(x_of(s['decision']) == s['oracle']['x_star'] for s in ss):>6}"
        f"{sum(s['votes'][0]['vote'] == s['oracle']['x_star'] for s in ss):>6}")

say("\n  Debate sessions (Round 1 = the votes WaRF logged first; truth = current label per file)")
for s in corpus:
    if not s.get("debate"):
        continue
    t = truth_for(s["artifact"], truths)
    r1 = synthesis([v["vote"] for v in s["votes"]], [v["omega"] for v in s["votes"]], s["domain"])[0].value
    r2 = s["decision"]
    tl = t.label if t else "unlabelled"
    say(f"    {Path(s['artifact'].replace(chr(92), '/')).name:<26} truth {tl:<10} Round 1 {r1:<8} final {r2:<8}"
        f" changed {','.join(s['debate'].get('vote_changes') or []) or '-'}")

# ---------------------------------------------------------------------------------------------
say("\n" + "=" * 110)
say("2. The persona experiment (.warf-experiments/sessions.jsonl): 12 reference files, every agent votes")
say("=" * 110)
home = ROOT / ".warf-experiments"
for prof in ("persona_v3", "h2h_auditor5", "h2h_skeptic5"):
    pool = load_pool(home, prof)
    items = sorted(pool.items())
    tr = {a: (truth_for(a, truths).x_star if truth_for(a, truths) else s["oracle"]["x_star"]) for a, s in items}
    uni = [(x_of(uniform_replay(s)[0]), tr[a]) for a, s in items]
    say(f"\n  {prof}: {len(items)} files ({sum(v == 1 for v in tr.values())} clean, "
        f"{sum(v == -1 for v in tr.values())} defective); order {', '.join(pool[items[0][0]]['_order'])}")
    say(HEAD)
    row("WaRF, uniform weights (README's view)", uni)
    row("WaRF, as run (weights moved)", [(x_of(s["decision"]), tr[a]) for a, s in items], uni)
    row("unweighted majority of five", [(1 if sum(v["vote"] for v in s["votes"]) > 0 else -1, tr[a]) for a, s in items], uni)
    for name in pool[items[0][0]]["_order"]:
        row(f"{name} alone", [(next(v["vote"] for v in s["votes"] if v["agent"] == name), tr[a]) for a, s in items], uni)
    if prof == "persona_v3":
        order = pool[items[0][0]]["_order"]
        say(f"\n    {'file':<26}{'truth':<9}" + "".join(f"{n[:4]:<6}" for n in order) + "WaRF (uniform)")
        for (a, s), (u, _) in zip(items, uni):
            vv = {v["agent"]: v["vote"] for v in s["votes"]}
            say(f"    {Path(a.replace(chr(92), '/')).name:<26}{'APPROVE' if tr[a] == 1 else 'REJECT':<9}"
                + "".join(f"{'A' if vv[n] == 1 else 'R':<6}" for n in order)
                + f"{'APPROVE' if u == 1 else 'REJECT'}{'' if u == tr[a] else '  (wrong)'}")

# ---------------------------------------------------------------------------------------------
say("\n" + "=" * 110)
say("3. WaRF's clone rule (SPECIFICATION 3.1.2): every pair must disagree on >= 15 % of reviews")
say("=" * 110)
say("  Two agents of different strictness disagree at least as often as their REJECT rates differ, even if")
say("  they rank the reviews alike. 'Crossed' counts the disagreements where the laxer agent of the pair")
say("  rejects and the stricter approves: 0 means one judgement at two thresholds. For scale, the count")
say("  expected if the agents erred independently given the truth, as the SPRT assumes.")


def clone(name, rows, labels):
    """rows: one {agent: vote} per review, every agent voting; labels: the truth per review."""
    agents = sorted(set.intersection(*(set(r) for r in rows)))
    n = len(rows)
    rate = {a: sum(r[a] == -1 for r in rows) / n for a in agents}
    pairs = [(i, j) if rate[i] <= rate[j] else (j, i) for i, j in combinations(agents, 2)]   # (laxer, stricter)
    rho, crossed, dis, expected = [], 0, 0, 0.0
    for lax, strict in pairs:
        d = sum(r[lax] != r[strict] for r in rows)
        rho.append(d / n)
        dis += d
        crossed += sum(r[lax] == -1 and r[strict] == 1 for r in rows)
    for c in set(labels):
        idx = [k for k, t in enumerate(labels) if t == c]
        rc = {a: sum(rows[k][a] == -1 for k in idx) / len(idx) for a in agents}
        expected += sum(len(idx) * rc[lax] * (1 - rc[strict]) for lax, strict in pairs)
    say(f"\n  {name}: {n} reviews; REJECT share " + ", ".join(f"{a} {rate[a]:.2f}" for a in agents))
    say(f"    rho min {min(rho):.2f}, mean {sum(rho) / len(rho):.2f}; pairs under 0.15: "
        f"{sum(r < 0.15 for r in rho)} of {len(rho)}; crossed {crossed} of {dis} disagreements "
        f"({crossed / dis if dis else 0:.0%}); independent given the truth: {expected:.0f}")


for prof in ("persona_v3", "h2h_auditor5", "h2h_skeptic5"):
    pool = load_pool(home, prof)
    clone(f"{prof} (Claude Haiku 4.5)", [{v["agent"]: v["vote"] for v in s["votes"]} for s in pool.values()],
          [truth_for(a, truths).x_star if truth_for(a, truths) else s["oracle"]["x_star"] for a, s in pool.items()])
for name, path, key in (("Jev, five personas, Round 1", HERE.parent / "jev-five" / "sessions_five.jsonl", "jev"),
                        ("Laya, five personas, Round 1", HERE.parent / "laya-five" / "sessions.jsonl", "five")):
    sessions = read(path)
    rows = [{v["agent"]: v["vote"] for v in s["votes"]} for s in sessions]
    assert all(len(r) == 5 for r in rows), name
    clone(name, rows, [x_of(s[key]["label"]) for s in sessions])     # git history: REJECT = later fixed

(HERE / "single_vs_panel.log").write_text("\n".join(out) + "\n", encoding="utf-8")
