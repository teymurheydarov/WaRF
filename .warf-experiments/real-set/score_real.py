"""Score the preregistered arms on the real-defect set (README.md) and apply the preregistered rule.

Arms: claude, claude-strict, claude-advocate (single calls); W1 claude-standard (WaRF's five personas);
W2 = CLAUDE + JEV in WaRF's log-odds mode: the stored answers of the claude and jev arms replayed through
run_review(aggregate="logodds") with default early stopping, calibration out of fold (5 folds stratified
by class, seed 7; each fold reviewed with a session log of the other folds' single-seat sessions labelled
as DEVELOPER oracles).

Primary: balanced accuracy. Tests: exact two-sided McNemar (items only one arm gets right) and a bootstrap
stratified by class (2000, seed 4), paired by item. WaRF wins if W1 or W2 beats each single-call arm with
McNemar p under the Holm threshold across the two WaRF arms and a bootstrap lower bound above 0.

    python .warf-experiments/real-set/score_real.py     # writes score.log and score.json"""
import contextlib
import io
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["TYPESAFE_API_KEY"] = "replay-no-network"   # the jev provider insists on a key; no call is made
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import INPUT_LABEL  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, Completion, SystemOneProvider  # noqa: E402
from warf.state import load_profiles, save_profiles  # noqa: E402

SINGLE = {"claude": "one Claude", "claude-strict": "one Claude, strict bar", "claude-advocate": "ADVOCATE alone"}
WARF = {"claude-standard": "W1 WaRF five personas", "mixed": "W2 WaRF Claude+Jev log-odds"}
out = []


def say(s=""):
    out.append(s)
    print(s)


items = [json.loads(line) for line in (HERE / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for arm in (*SINGLE, "claude-standard", "jev"):
    recs[arm] = {}
    for path in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs[arm]:
                raise SystemExit(f"{arm}: {r['planted']['id']} twice")
            recs[arm][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in recs)]
say(f"{len(ids)} of {len(items)} items answered by every arm "
    f"({sum(defect[i] for i in ids)} defective, {sum(not defect[i] for i in ids)} clean)")

# ── W2: replay CLAUDE + JEV through WaRF's log-odds mode ──
current = {"id": None}
providers.find_claude_exe = lambda: Path(sys.executable)      # construct the CLI provider; never run it
ClaudeCLIProvider.complete = lambda self, system, user, model, timeout: Completion(
    text=recs["claude"][current["id"]]["planted"]["call"]["reply"])
SystemOneProvider._post = lambda self, request, timeout: recs["jev"][current["id"]]["planted"]["call"]["body"]
panel = HERE / "profiles" / "mixed.json"
save_profiles(panel, [load_profiles(HERE / "profiles" / f"{s}.json")[0] for s in ("claude", "jev")])
rng = random.Random(7)
fold = {}
for cls in (True, False):
    members = [i for i in ids if defect[i] == cls]
    rng.shuffle(members)
    for k, i in enumerate(members):
        fold[i] = k % 5
tmp = Path(tempfile.mkdtemp(prefix="warf-real-score-"))
mixed = {}
for k in range(5):
    log = tmp / f"train{k}.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seat in ("claude", "jev"):
            for i in ids:
                if fold[i] != k:
                    r = {key: v for key, v in recs[seat][i].items() if key != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for i in (i for i in ids if fold[i] == k):
        current["id"] = i
        it = by_id[i]
        with contextlib.redirect_stdout(io.StringIO()):
            mixed[i] = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                                  context=it["context"], aggregate="logodds", log_path=log)

reject = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in (*SINGLE, "claude-standard", "jev")}
reject["mixed"] = {i: mixed[i].decision.value == "REJECT" for i in ids}
NAMES = {**SINGLE, **WARF, "jev": "Jev alone (W2's seat)"}


def ba(arm, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(reject[arm][i] for i in P) / len(P) + sum(not reject[arm][i] for i in N) / len(N)) / 2


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


brng = random.Random(4)
P_ids = [i for i in ids if defect[i]]
N_ids = [i for i in ids if not defect[i]]
boots = [[brng.choice(P_ids) for _ in P_ids] + [brng.choice(N_ids) for _ in N_ids] for _ in range(2000)]
result = {"n": len(ids), "arms": {}, "comparisons": {}}

for title, sample in (("all items", ids), ("defects both judges call visible from the diff, with all clean items",
                                           [i for i in ids if not defect[i] or by_id[i].get("visible") == "diff"])):
    say(f"\n== {title}: {sum(defect[i] for i in sample)} defective, {sum(not defect[i] for i in sample)} clean ==")
    say("  arm                              BA      recall     false alarms")
    for arm in (*SINGLE, *WARF, "jev"):
        P = [i for i in sample if defect[i]]
        N = [i for i in sample if not defect[i]]
        say(f"  {NAMES[arm]:<32} {ba(arm, sample):.3f}   {sum(reject[arm][i] for i in P)}/{len(P)}"
            f"      {sum(reject[arm][i] for i in N)}/{len(N)}")
        if sample is ids:
            result["arms"][arm] = {"ba": round(ba(arm, ids), 4), "recall": sum(reject[arm][i] for i in P),
                                   "false_alarms": sum(reject[arm][i] for i in N)}

say("\n== Preregistered comparisons (all items): WaRF arm minus single-call arm ==")
pvals = {}
for w in WARF:
    for s in SINGLE:
        d = ba(w, ids) - ba(s, ids)
        xs = sorted(ba(w, b) - ba(s, b) for b in boots)
        k1 = sum((reject[w][i] == defect[i]) and (reject[s][i] != defect[i]) for i in ids)
        k2 = sum((reject[s][i] == defect[i]) and (reject[w][i] != defect[i]) for i in ids)
        p = mcnemar(k1, k1 + k2)
        pvals[(w, s)] = (d, xs[49], xs[1949], k1, k2, p)
        say(f"  {NAMES[w]} - {NAMES[s]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  only WaRF {k1}, only single {k2}, McNemar p {p:.3f}")
        result["comparisons"][f"{w} - {s}"] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                                "only_warf": k1, "only_single": k2, "p": round(p, 4)}

# Holm across the two WaRF arms: each arm's worst (largest) p over the single-call arms is its p
arm_p = {w: max(pvals[(w, s)][5] for s in SINGLE) for w in WARF}
order = sorted(WARF, key=lambda w: arm_p[w])
holm = {order[0]: 0.025, order[1]: 0.05}
say("\n== Preregistered verdict ==")
won = []
for w in WARF:
    beats_all = all(pvals[(w, s)][0] > 0 and pvals[(w, s)][1] > 0 for s in SINGLE)
    sig = arm_p[w] < holm[w]
    say(f"  {NAMES[w]}: worst p over single arms {arm_p[w]:.3f} (Holm threshold {holm[w]}), "
        f"bootstrap lower bound > 0 against all: {beats_all}")
    if beats_all and sig:
        won.append(w)
if won:
    verdict = "WaRF wins: " + ", ".join(NAMES[w] for w in won)
elif any(all(pvals[(w, s)][0] > 0 for s in SINGLE) for w in WARF):
    verdict = "favours WaRF, not shown"
else:
    verdict = "no case for WaRF"
say(f"  VERDICT: {verdict}")
result["verdict"] = verdict
calls = {a: sum(len(recs[a][i]["planted"].get("calls", [0])) for i in ids) for a in (*SINGLE, "claude-standard")}
say("\n  calls: " + ", ".join(f"{NAMES[a]} {c}" for a, c in calls.items()) + f"; W2 uses claude + jev ({len(ids)} each)")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
