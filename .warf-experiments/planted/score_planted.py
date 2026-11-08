"""Claude alone against the mixed panel (Claude + Jev + Laya, WaRF's log-odds mode) on the planted set.

Right answer: REJECT for a planted item, APPROVE for its clean original (54 + 54 items, 54 bases).

  Claude alone   the claude arm's own WaRF verdict (one agent, vote mode, as run_planted.py ran it)
  mixed panel    WaRF's run_review(aggregate="logodds") on the profile CLAUDE, JEV, LAYA (the same
                 personas, providers and models as the single runs), with WaRF's default early
                 stopping. No model is asked again: every provider call returns the stored answer of
                 that seat for that item, so the panel's Claude seat is exactly Claude alone's answer.
                 Calibration is out of fold: the bases are split into 5 folds, and each fold is
                 reviewed with a session log holding only the other folds' single-seat sessions, each
                 labelled as a DEVELOPER oracle (planted = REJECT). Both items of a base share a fold.
  cold start     the same panel with an empty log: no calibration, as on a fresh WaRF install

Subset, chosen before any result was looked at (but written after Jev's run had finished): without
the relational boundary swaps (< <-> <=, > <-> >=), which change only the boundary case and may be
nearly harmless.

    python .warf-experiments/planted/score_planted.py      # writes score.log and score.json"""
import contextlib
import io
import json
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

SEATS = ("claude", "jev", "laya")
BOUNDARY = {"lt", "le", "gt", "ge"}
out = []


def say(s=""):
    out.append(s)
    print(s)


items = [json.loads(line) for line in (HERE / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "planted" for it in items}
recs = {}
for seat in SEATS:
    recs[seat] = {}
    for path in sorted(HERE.glob(f"{seat}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs[seat]:
                raise SystemExit(f"{seat}: {r['planted']['id']} twice")
            recs[seat][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[s] for s in SEATS)]
bases = sorted({by_id[i]["base"] for i in ids if all(f"{by_id[i]['base']}:{k}" in ids for k in ("clean", "planted"))})
ids = [i for i in ids if by_id[i]["base"] in bases]
say(f"{len(bases)} bases with all six answers ({len(ids)} items); answers per seat: "
    + ", ".join(f"{s} {len(recs[s])}" for s in SEATS))

# ── replayed providers: every call returns the stored answer of that seat for the current item ──
current = {"id": None}
providers.find_claude_exe = lambda: Path(sys.executable)      # construct the CLI provider; never run


def _claude(provider, system, user, model, timeout):
    return Completion(text=recs["claude"][current["id"]]["planted"]["call"]["reply"])


def _post(provider, request, timeout):
    return recs[provider.name][current["id"]]["planted"]["call"]["body"]


ClaudeCLIProvider.complete = _claude
SystemOneProvider._post = _post

panel_path = HERE / "profiles" / "panel.json"
seats = [load_profiles(HERE / "profiles" / f"{s}.json")[0] for s in SEATS]
save_profiles(panel_path, seats)

rng = random.Random(7)
order = bases[:]
rng.shuffle(order)
fold = {b: k % 5 for k, b in enumerate(order)}


def write_log(train_bases: set, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for seat in SEATS:
            for i in ids:
                if by_id[i]["base"] in train_bases:
                    r = {k: v for k, v in recs[seat][i].items() if k != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")


def panel(log_for) -> dict:
    """{id: ReviewResult} of the mixed panel, each item reviewed with log_for(fold)."""
    res = {}
    for k in range(5):
        log = log_for(k)
        for i in (i for i in ids if fold[by_id[i]["base"]] == k):
            current["id"] = i
            it = by_id[i]
            with contextlib.redirect_stdout(io.StringIO()):
                res[i] = run_review(it["code"], it["domain"], panel_path, verbose=False, debate=False,
                                    input_label=INPUT_LABEL, context=it["context"], aggregate="logodds",
                                    log_path=log)
    return res


tmp = Path(tempfile.mkdtemp(prefix="warf-planted-score-"))


def oof_log(k):
    path = tmp / f"train{k}.jsonl"
    write_log({b for b in bases if fold[b] != k}, path)
    return path


empty = tmp / "empty.jsonl"
empty.write_text("", encoding="utf-8")
calibrated = panel(oof_log)
cold = panel(lambda k: empty)

reject = {
    "Claude alone": {i: recs["claude"][i]["decision"] == "REJECT" for i in ids},
    "Mixed panel, log-odds (calibrated out of fold)": {i: calibrated[i].decision.value == "REJECT" for i in ids},
    "Mixed panel, log-odds (cold start)": {i: cold[i].decision.value == "REJECT" for i in ids},
    "  member: Jev alone": {i: recs["jev"][i]["decision"] == "REJECT" for i in ids},
    "  member: Laya alone": {i: recs["laya"][i]["decision"] == "REJECT" for i in ids},
}
score = {
    "Claude alone (vote)": {i: float(reject["Claude alone"][i]) for i in ids},
    "Mixed panel, -Lambda (calibrated)": {i: -calibrated[i].sprt_lambda for i in ids},
    "Mixed panel, -Lambda (cold start)": {i: -cold[i].sprt_lambda for i in ids},
    "  member: Jev p(REJECT)": {i: recs["jev"][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"] for i in ids},
    "  member: Laya p(REJECT)": {i: recs["laya"][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"] for i in ids},
}


def ba(rj, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(rj[i] for i in P) / len(P) + sum(not rj[i] for i in N) / len(N)) / 2


def auc(sc, sample):
    P = [sc[i] for i in sample if defect[i]]
    N = [sc[i] for i in sample if not defect[i]]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def items_of(bs):
    """Both items of every base in bs, once per occurrence: a base drawn twice counts twice."""
    return [f"{b}:{k}" for b in bs for k in ("clean", "planted")]


subsets = {"all": bases,
           "without boundary swaps": [b for b in bases if by_id[f"{b}:planted"]["operator"] not in BOUNDARY]}
brng = random.Random(4)
result = {}
for name, bs in subsets.items():
    sample = items_of(bs)
    boots = [items_of([brng.choice(bs) for _ in bs]) for _ in range(2000)]
    say(f"\n== {name}: {len(bs)} bases, {len(sample)} items ==")
    say("Verdict: balanced accuracy [95 %, bootstrap over bases], planted caught, clean passed, pairs fully right")
    for arm, rj in reject.items():
        b = ba(rj, sample)
        xs = sorted(ba(rj, s) for s in boots)
        caught = sum(rj[f"{x}:planted"] for x in bs)
        passed = sum(not rj[f"{x}:clean"] for x in bs)
        pairs = sum(rj[f"{x}:planted"] and not rj[f"{x}:clean"] for x in bs)
        say(f"  {arm:<48} {b:.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]   {caught}/{len(bs)}   {passed}/{len(bs)}   {pairs}/{len(bs)}")
        result.setdefault(name, {})[arm] = {"ba": round(b, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                            "caught": caught, "passed": passed, "pairs": pairs, "n": len(bs)}
    say("Ranking: AUC")
    for arm, sc in score.items():
        say(f"  {arm:<48} {auc(sc, sample):.3f}")
    say("Panel minus Claude alone, balanced accuracy, paired over bases [95 %]; items only one gets right")
    for arm in ("Mixed panel, log-odds (calibrated out of fold)", "Mixed panel, log-odds (cold start)"):
        d = ba(reject[arm], sample) - ba(reject["Claude alone"], sample)
        xs = sorted(ba(reject[arm], s) - ba(reject["Claude alone"], s) for s in boots)
        right = {a: {i: reject[a][i] == defect[i] for i in sample} for a in (arm, "Claude alone")}
        only_p = sum(right[arm][i] and not right["Claude alone"][i] for i in sample)
        only_c = sum(right["Claude alone"][i] and not right[arm][i] for i in sample)
        say(f"  {arm}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]   only panel {only_p}, only Claude {only_c}")
        result[name][f"{arm} - Claude alone"] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                                 "only_panel": only_p, "only_claude": only_c}

say("\n== The calibrated panel ==")
bands = {}
for i in ids:
    c = calibrated[i].confidence.value
    n, k = bands.get(c, (0, 0))
    bands[c] = (n + 1, k + (reject["Mixed panel, log-odds (calibrated out of fold)"][i] == defect[i]))
say("  right per confidence band: " + ", ".join(f"{c} {k}/{n}" for c, (n, k) in sorted(bands.items())))
asked = [len(calibrated[i].votes) for i in ids]
say(f"  seats asked: " + ", ".join(f"{k} {asked.count(k)}" for k in (1, 2, 3)))
tags = {}
for i in ids:
    for v in calibrated[i].votes:
        tags.setdefault(v.agent_name, set()).add(v.calibration)
say("  calibration used: " + "; ".join(f"{a} {sorted(t)}" for a, t in tags.items()))
flips = sum(reject["Mixed panel, log-odds (calibrated out of fold)"][i] != reject["Claude alone"][i] for i in ids)
say(f"  verdict differs from Claude alone on {flips} of {len(ids)} items")
cost = sum(float((recs["jev"][i]["planted"]["call"]["body"].get("usage") or {}).get("cost") or 0) for i in ids)
say(f"\nJev cost ${cost:.4f}; Laya truncated: {sum(bool((recs['laya'][i]['planted']['call']['body'].get('usage') or {}).get('truncated')) for i in ids)} of {len(ids)}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
