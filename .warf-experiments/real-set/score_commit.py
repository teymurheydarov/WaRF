"""Score the second preregistration (README.md, "the whole-commit reader"): W3, WaRF's evidence panel,
against every single-call arm on the same 132 items.

W3 = two seats with STRICT_PERSONA in WaRF's log-odds mode with default early stopping: CLAUDE (the
claude-strict arm, single file) and CLAUDE-COMMIT (the claude-commit-strict arm, whole commit,
evidence="whole-commit", so it pools as its own source). Their stored answers are replayed through
run_review(aggregate="logodds") in profile order; calibration is out of fold with the folds of
score_real.py (5, stratified by class, seed 7), from session logs of the other folds' answers of the
two arms, labelled as DEVELOPER oracles.

W3 wins if it beats each single-call arm (claude, claude-strict, claude-advocate, claude-commit,
claude-commit-strict) in balanced accuracy with exact McNemar p < 0.05 and a bootstrap lower bound
above 0 (stratified by class, 2000, seed 4). The decisive comparison is against claude-commit-strict.

    python .warf-experiments/real-set/score_commit.py     # writes score_commit.log and score_commit.json"""
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
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import INPUT_LABEL  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, Completion  # noqa: E402
from warf.state import load_profiles, save_profiles  # noqa: E402

SINGLE = {"claude": "one Claude", "claude-strict": "one Claude, strict", "claude-advocate": "ADVOCATE alone",
          "claude-commit": "one Claude, whole commit", "claude-commit-strict": "one Claude, whole commit, strict"}
SEATS = ("claude-strict", "claude-commit-strict")       # W3's seats, in asking order
out = []


def say(s=""):
    out.append(s)
    print(s)


items = [json.loads(line) for line in (HERE / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for arm in SINGLE:
    recs[arm] = {}
    for path in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs[arm]:
                raise SystemExit(f"{arm}: {r['planted']['id']} twice")
            recs[arm][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in SINGLE)]
say(f"{len(ids)} of {len(items)} items answered by every arm")

# ── W3: replay the two strict seats; both share one persona text, so answers are served in seat order ──
queue = []
providers.find_claude_exe = lambda: Path(sys.executable)      # construct the CLI provider; never run it
ClaudeCLIProvider.complete = lambda self, system, user, model, timeout: Completion(text=queue.pop(0))
panel = HERE / "profiles" / "evidence-panel.json"
seats = [load_profiles(HERE / "profiles" / f"{a}.json")[0] for a in SEATS]
assert seats[0].evidence is None and seats[1].evidence == "whole-commit" and seats[0].name != seats[1].name
save_profiles(panel, seats)
rng = random.Random(7)
fold = {}
for cls in (True, False):
    members = [i for i in ids if defect[i] == cls]
    rng.shuffle(members)
    for k, i in enumerate(members):
        fold[i] = k % 5
tmp = Path(tempfile.mkdtemp(prefix="warf-commit-score-"))
whole = {r["id"]: r["code"] for r in map(json.loads, (HERE / "commit_inputs.jsonl").open(encoding="utf-8"))}
w3 = {}
for k in range(5):
    log = tmp / f"train{k}.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for arm in SEATS:
            for i in ids:
                if fold[i] != k:
                    r = {key: v for key, v in recs[arm][i].items() if key != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    # the arms ran before WaRF logged evidence_source; the whole-commit seat's votes carry it now
                    src = load_profiles(HERE / "profiles" / f"{arm}.json")[0].evidence
                    r["votes"] = [{**v, **({"evidence_source": src} if src else {})} for v in r["votes"]]
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for i in (i for i in ids if fold[i] == k):
        queue[:] = [recs[a][i]["planted"]["call"]["reply"] for a in SEATS]
        it = by_id[i]
        with contextlib.redirect_stdout(io.StringIO()):
            w3[i] = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                               context=it["context"], aggregate="logodds", log_path=log,
                               seat_inputs={"whole-commit": whole[i]})
        names = [v.agent_name for v in w3[i].votes]
        if names != [s.name for s in seats][:len(names)]:
            raise SystemExit(f"{i}: seats answered out of order {names}")

reject = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in SINGLE}
reject["w3"] = {i: w3[i].decision.value == "REJECT" for i in ids}
NAMES = {**SINGLE, "w3": "W3 WaRF evidence panel"}


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
                                           [i for i in ids if not defect[i] or by_id[i].get("visible") == "diff"]),
                      ("defects that need another file, with all clean items",
                       [i for i in ids if not defect[i] or by_id[i].get("visible") == "needs_other_file"])):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    say(f"\n== {title}: {len(P)} defective, {len(N)} clean ==")
    say("  arm                                  BA      recall     false alarms")
    for arm in (*SINGLE, "w3"):
        say(f"  {NAMES[arm]:<36} {ba(arm, sample):.3f}   {sum(reject[arm][i] for i in P)}/{len(P)}"
            f"      {sum(reject[arm][i] for i in N)}/{len(N)}")
        if sample is ids:
            result["arms"][arm] = {"ba": round(ba(arm, ids), 4), "recall": sum(reject[arm][i] for i in P),
                                   "false_alarms": sum(reject[arm][i] for i in N)}

say("\n== Preregistered comparisons (all items): W3 minus single-call arm ==")
rows = {}
for s in SINGLE:
    d = ba("w3", ids) - ba(s, ids)
    xs = sorted(ba("w3", b) - ba(s, b) for b in boots)
    k1 = sum((reject["w3"][i] == defect[i]) and (reject[s][i] != defect[i]) for i in ids)
    k2 = sum((reject[s][i] == defect[i]) and (reject["w3"][i] != defect[i]) for i in ids)
    p = mcnemar(k1, k1 + k2)
    rows[s] = (d, xs[49], xs[1949], p)
    say(f"  W3 - {NAMES[s]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  only W3 {k1}, only single {k2}, McNemar p {p:.3f}")
    result["comparisons"][s] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                "only_w3": k1, "only_single": k2, "p": round(p, 4)}
won = all(r[1] > 0 and r[3] < 0.05 for r in rows.values())
favours = all(r[0] > 0 for r in rows.values())
verdict = ("W3 wins" if won else "favours W3, not shown" if favours else "no case for W3")
d = rows["claude-commit-strict"]
say(f"\n  decisive (W3 - one Claude given the whole commit, strict): {d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}], p {d[3]:.3f}")
say(f"  VERDICT: {verdict}")
result["verdict"] = verdict
seats_asked = [len(w3[i].votes) for i in ids]
say(f"\n  W3 seats asked: 1 seat {seats_asked.count(1)}, 2 seats {seats_asked.count(2)}; "
    f"calibration: {sorted({v.calibration for i in ids for v in w3[i].votes})}")
(HERE / "score_commit.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score_commit.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
