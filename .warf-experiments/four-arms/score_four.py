"""Score the four arms of run_four.py against the git-history labels (REJECT = later fixed).

For every arm: WaRF's verdict (balanced accuracy, REJECT rate, HIGH-confidence verdicts) and a
ranking score (AUC):
  - jev-one: Jev's p(REJECT) at full precision;
  - jev-standard: mean p(REJECT) of the agents WaRF asked, and WaRF's Lambda;
  - claude-one: only a vote, so its AUC equals its balanced accuracy;
  - claude-standard: WaRF's Lambda, and the share of REJECT votes.

Two label sets:
  all 100      as selected (50 later fixed, 50 never fixed, size-matched pairs)
  without 18   drops the 18 never-fixed changes that add no line B-SZZ could ever blame
               (deletion-only, comment-only), so they can never be labelled REJECT
               (../something-wrong/verify-labels-metrics/v2_data.json, `t18`)

Intervals: 2000 bootstrap resamples, drawn within each label class, paired across arms.

    python .warf-experiments/four-arms/score_four.py        # writes score.log and score.json"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("claude-one", "claude-standard", "jev-one", "jev-standard")
T18 = set(json.loads((HERE.parent / "something-wrong" / "verify-labels-metrics" / "v2_data.json")
                     .read_text(encoding="utf-8"))["t18"])
selection = [json.loads(line) for line in (HERE.parent / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
ids = [s["id"] for s in selection]
defect = {s["id"]: s["label"] == "REJECT" for s in selection}
out = []


def say(s=""):
    out.append(s)
    print(s)


def load(arm):
    recs = {}
    for path in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["four"]["id"] in recs:
                raise SystemExit(f"{arm}: {r['four']['id']} twice")
            if r["four"]["label"] != selection[ids.index(r["four"]["id"])]["label"]:
                raise SystemExit(f"{arm}: {r['four']['id']} label mismatch")
            recs[r["four"]["id"]] = r
    return recs


def auc(score, sample):
    P = [score[i] for i in sample if defect[i]]
    N = [score[i] for i in sample if not defect[i]]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def ba(reject, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(reject[i] for i in P) / len(P) + sum(not reject[i] for i in N) / len(N)) / 2


recs = {arm: load(arm) for arm in ARMS}
missing = {arm: [i for i in ids if i not in recs[arm]] for arm in ARMS}
common = [i for i in ids if all(i in recs[arm] for arm in ARMS)]
say(f"Reviews per arm: " + ", ".join(f"{a} {len(recs[a])}" for a in ARMS) + f"; scored on the {len(common)} all four have.")
if any(missing.values()):
    say("Missing: " + "; ".join(f"{a}: {m}" for a, m in missing.items() if m))

reject = {arm: {i: recs[arm][i]["decision"] == "REJECT" for i in common} for arm in ARMS}
scores = {
    "Claude, one agent (vote)": {i: float(reject["claude-one"][i]) for i in common},
    "WaRF Claude, -Lambda": {i: -recs["claude-standard"][i]["sprt_lambda"] for i in common},
    "WaRF Claude, REJECT-vote share": {i: sum(v["vote"] == -1 for v in recs["claude-standard"][i]["votes"])
                                       / len(recs["claude-standard"][i]["votes"]) for i in common},
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


def interval(f, name):
    xs = sorted(f(b) for b in boots[name])
    return xs[49], xs[1949]


result = {"n": {k: len(v) for k, v in samples.items()}, "verdict": {}, "ranking": {}, "differences": {}}
for name, sample in samples.items():
    nP = sum(defect[i] for i in sample)
    say(f"\n== {name}: {len(sample)} changes, {nP} later fixed, {len(sample) - nP} never fixed ==")
    say("WaRF's verdict: balanced accuracy [95 %], REJECTs (later fixed), HIGH verdicts right")
    for arm in ARMS:
        b = ba(reject[arm], sample)
        lo, hi = interval(lambda s: ba(reject[arm], s), name)
        nr = sum(reject[arm][i] for i in sample)
        nrd = sum(reject[arm][i] and defect[i] for i in sample)
        high = [i for i in sample if recs[arm][i]["confidence"] == "HIGH"]
        hr = sum(reject[arm][i] == defect[i] for i in high)
        say(f"  {NAMES[arm]:<28} {b:.3f} [{lo:.3f}, {hi:.3f}]   REJECT {nr} ({nrd})   HIGH {hr}/{len(high)}")
        result["verdict"].setdefault(name, {})[arm] = {"ba": round(b, 4), "ci": [round(lo, 4), round(hi, 4)],
                                                       "reject": nr, "reject_defect": nrd,
                                                       "high": len(high), "high_right": hr}
    say("Ranking: AUC [95 %]")
    for sname, sc in scores.items():
        a = auc(sc, sample)
        lo, hi = interval(lambda s: auc(sc, s), name)
        say(f"  {sname:<42} {a:.3f} [{lo:.3f}, {hi:.3f}]")
        result["ranking"].setdefault(name, {})[sname] = {"auc": round(a, 4), "ci": [round(lo, 4), round(hi, 4)]}
    say("Differences in balanced accuracy, paired [95 %], share of resamples <= 0")
    for a1, a2 in (("claude-one", "jev-one"), ("claude-standard", "jev-standard"),
                   ("claude-standard", "claude-one"), ("jev-standard", "jev-one"), ("claude-one", "jev-standard")):
        d = ba(reject[a1], sample) - ba(reject[a2], sample)
        xs = sorted(ba(reject[a1], s) - ba(reject[a2], s) for s in boots[name])
        le0 = sum(x <= 0 for x in xs) / len(xs)
        say(f"  {NAMES[a1]} - {NAMES[a2]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  {le0:.3f}")
        result["differences"].setdefault(name, {})[f"{a1} - {a2}"] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                                                      "share_le0": round(le0, 4)}

say("\n== The panels' seats (all 100) ==")
for arm in ("claude-standard", "jev-standard"):
    seats = {}
    for i in common:
        for v in recs[arm][i]["votes"]:
            seats.setdefault(v["agent"], {})[i] = v["vote"] == -1
    stops = sum(len(recs[arm][i]["votes"]) < 5 for i in common)
    say(f"  {NAMES[arm]}: {stops} reviews stopped early; REJECT votes per seat (of the reviews it voted on): "
        + ", ".join(f"{a} {sum(s.values())}/{len(s)}" for a, s in seats.items()))
    agree = sum(reject[arm][i] == reject[arm.replace("standard", "one")][i] for i in common)
    say(f"    verdict equals the same model's one agent on {agree} of {len(common)}")
cost = sum(recs[a][i]["four"].get("cost") or 0 for a in ("jev-one", "jev-standard") for i in common)
say(f"\nJev cost: ${cost:.4f}. Claude calls: "
    + ", ".join(f"{a} {sum(len(recs[a][i]['four']['calls']) for i in common)}" for a in ("claude-one", "claude-standard")))
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
