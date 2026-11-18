"""Score the PPSSPP test (README.md "Primary analysis", "Secondary"), from the stored answers; no Jev call.

Every change is decided by WaRF's run_review(aggregate="logodds") with the agent call stubbed to return that
seat's stored answer, and WaRF's Calibrator fitted on the labelled sessions of the other nine folds (stratified
10-fold, seed 300 + repetition, as ../pooled-dev/warf-panel/replay_learned.py). Primary: PANEL3 against LO-ctx,
repetition 0, exact two-sided McNemar; 5-repetition means next to it.

    python score_pp.py                                   # writes score.log, score.json
    python score_pp.py --items I --sessions S --log L    # the same on other stored answers (dry run)"""
import argparse
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("WARF_HOME", tempfile.mkdtemp(prefix="warf-score-"))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent)); sys.path.insert(0, str(HERE))
from warf import orchestrator  # noqa: E402
from warf.calibration import Calibrator  # noqa: E402
from warf.state import save_profiles  # noqa: E402
import panel  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def auc(sc, P, N):
    vals = sorted([(sc[i], 1) for i in P] + [(sc[i], 0) for i in N])
    rank_sum, k = 0.0, 0
    while k < len(vals):
        j = k
        while j < len(vals) and vals[j][0] == vals[k][0]:
            j += 1
        rank_sum += (k + 1 + j) / 2 * sum(v[1] for v in vals[k:j])
        k = j
    return (rank_sum - len(P) * (len(P) + 1) / 2) / (len(P) * len(N))


def mcnemar(a, b, Y, ids):
    right = lambda pred, i: pred[i] == ("REJECT" if Y[i] == -1 else "APPROVE")  # noqa: E731
    n10 = sum(1 for i in ids if right(a, i) and not right(b, i))
    n01 = sum(1 for i in ids if right(b, i) and not right(a, i))
    n = n10 + n01
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(n10, n01) + 1)) / 2 ** n) if n else 1.0
    return n10, n01, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=str(HERE / "items.jsonl"))
    ap.add_argument("--sessions", default=str(HERE / "sessions.jsonl"))
    ap.add_argument("--log", default=str(HERE / "score.log"))
    a = ap.parse_args()
    items = {json.loads(l)["id"]: json.loads(l) for l in Path(a.items).open(encoding="utf-8")}
    ids = list(items)
    Y = {i: (-1 if items[i]["kind"] == "defective" else 1) for i in ids}
    seats = {p.name: p for p in panel.personas() + panel.question_seats()}
    ans = {}
    for l in Path(a.sessions).open(encoding="utf-8"):
        r = json.loads(l)
        for v in r["votes"]:
            ans[(r["artifact"], v["agent"])] = (v["vote"], v["reasoning"], v["p_reject"])
    missing = [(i, s) for i in ids for s in seats if (i, s) not in ans]
    if missing:
        raise SystemExit(f"{len(missing)} answers missing, e.g. {missing[:3]}")
    by_key = {(s.persona, s.model): s.name for s in seats.values()}
    current = [None]

    def stub(persona, code, domain, **kw):
        vote, reasoning, _ = ans[(current[0], by_key[(persona, kw["model"])])]
        return vote, reasoning, 0, 0, kw["provider"], kw["model"]

    def session(i, panel_seats):
        return {"session_id": i, "domain": items[i]["domain"], "oracle": {"type": "DEVELOPER", "x_star": Y[i]},
                "votes": [{"agent": s.name, "vote": ans[(i, s.name)][0], "persona": s.persona_hash, "provider": "jev",
                           "model": s.model, "reasoning": ans[(i, s.name)][1],
                           **({"question": s.question} if s.question else {})} for s in panel_seats]}

    prof = Path(tempfile.mkdtemp()) / "panel.json"

    def predict(panel_seats, rep):
        save_profiles(prof, panel_seats)
        orchestrator._call_agent = stub
        rng = random.Random(300 + rep)
        P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]; rng.shuffle(P); rng.shuffle(N)
        folds = [P[k::10] + N[k::10] for k in range(10)]
        pred = {}
        for k in range(10):
            train = [i for f in folds[:k] + folds[k + 1:] for i in f]
            log = Path(tempfile.mkdtemp()) / "train.jsonl"
            log.write_text("".join(json.dumps(session(i, panel_seats)) + "\n" for i in train), encoding="utf-8")
            cal = Calibrator(log)
            orchestrator.Calibrator = lambda path, cal=cal: cal
            for i in folds[k]:
                current[0] = i
                pred[i] = orchestrator.run_review(items[i]["code"], items[i]["domain"], prof, verbose=False,
                                                  aggregate="logodds", log_path=log).decision.value
        return pred

    def ba(pred, sub=None):
        sub = sub or ids
        P = [i for i in sub if Y[i] == -1]; N = [i for i in sub if Y[i] == 1]
        return (sum(pred[i] == "REJECT" for i in P) / len(P) + sum(pred[i] == "APPROVE" for i in N) / len(N)) / 2

    arms = {"PANEL3": [seats[n] for n in ("BOUNDARY", "LOCATE", "CHECKLIST")],
            "LO-ctx": [seats[n] for n in ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")],
            "FIVE": [seats[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT", "LOCATE", "CHECKLIST")]}
    preds = {name: [predict(s, rep) for rep in range(5)] for name, s in arms.items()}
    P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]
    say(f"{len(ids)} changes ({len(P)} defective, {len(N)} clean)")
    say("\nBalanced accuracy, WaRF logodds, 10-fold calibration within the set (repetition 0; mean of 5)")
    res = {}
    for name, ps in preds.items():
        p0 = ps[0]
        caught = sum(p0[i] == "REJECT" for i in P); alarms = sum(p0[i] == "REJECT" for i in N)
        res[name] = {"ba0": ba(p0), "ba5": sum(ba(p) for p in ps) / 5, "caught": caught, "false_alarms": alarms}
        say(f"  {name:<7} {100 * ba(p0):5.1f}%  (mean of 5: {100 * res[name]['ba5']:.1f}%)  caught {caught}/{len(P)}, "
            f"false alarms {alarms}/{len(N)}")
    n10, n01, p = mcnemar(preds["PANEL3"][0], preds["LO-ctx"][0], Y, ids)
    verdict = ("PANEL3 WINS" if res["PANEL3"]["ba0"] > res["LO-ctx"]["ba0"] and p < 0.05 else
               "not shown" if res["PANEL3"]["ba0"] > res["LO-ctx"]["ba0"] else "no case")
    say(f"\nPRIMARY: PANEL3 vs LO-ctx: right only in PANEL3 {n10}, only in LO-ctx {n01}, exact McNemar p = {p:.4f}"
        f"  -> {verdict}")
    # Secondary fixed in README.md before mining: DuckDB's primary discordants added to PPSSPP's, one exact test
    ddb = json.loads((HERE.parent / "ddb-set" / "score.json").read_text(encoding="utf-8"))["primary"]
    t10, t01 = n10 + ddb["n10"], n01 + ddb["n01"]
    tp = min(1.0, 2 * sum(math.comb(t10 + t01, k) for k in range(min(t10, t01) + 1)) / 2 ** (t10 + t01))
    pooled = "POOLED WINS" if t10 > t01 and tp < 0.05 else "pooled not shown" if t10 > t01 else "pooled no case"
    say(f"Secondary: pooled with DuckDB ({ddb['n10']} vs {ddb['n01']}): PANEL3 {t10}, LO-ctx {t01}, exact McNemar "
        f"p = {tp:.4f}  -> {pooled}")
    m10, m01, q = mcnemar(preds["FIVE"][0], preds["LO-ctx"][0], Y, ids)
    say(f"Secondary: FIVE vs LO-ctx: {m10} vs {m01}, p = {q:.4f}")
    vis = [i for i in ids if Y[i] == 1 or items[i].get("visible") == "diff"]
    if any(Y[i] == -1 for i in vis):
        say(f"Secondary: on the defects visible from the diff (with every clean change): PANEL3 "
            f"{100 * ba(preds['PANEL3'][0], vis):.1f}%, LO-ctx {100 * ba(preds['LO-ctx'][0], vis):.1f}%")
    # Secondary added before any Jev call (README 2026-11-15): pairs whose control came from the defect's own bin
    sys.path.insert(0, str(HERE.parent / "rdb-set")); sys.path.insert(0, str(HERE.parent / "kpx-set"))
    from build_clean_matched import bin_of
    from freeze import added
    defect_of = {it["base"]: it for it in items.values() if it["kind"] == "defective"}
    same = []
    for i, it in items.items():
        if it["kind"] == "clean":
            d = defect_of[it["matched_to"]]
            if bin_of(added(d["code"])) == bin_of(added(it["code"])):
                same += [d["id"], i]
    s10, s01, sp = mcnemar(preds["PANEL3"][0], preds["LO-ctx"][0], Y, same)
    say(f"Secondary: the {len(same) // 2} pairs matched in their own added-line bin: PANEL3 "
        f"{100 * ba(preds['PANEL3'][0], same):.1f}%, LO-ctx {100 * ba(preds['LO-ctx'][0], same):.1f}%; "
        f"{s10} vs {s01}, p = {sp:.4f}")
    say("\nAUC of each seat's p(REJECT); the added-line count alone for comparison")
    say(f"  {'added lines':<13} {auc({i: added(items[i]['code']) for i in ids}, P, N):.3f}")
    for s in seats:
        say(f"  {s:<13} {auc({i: ans[(i, s)][2] for i in ids}, P, N):.3f}")
    Path(a.log).write_text("\n".join(out) + "\n", encoding="utf-8")
    Path(a.log).with_suffix(".json").write_text(json.dumps({"primary": {"n10": n10, "n01": n01, "p": p, "verdict": verdict},
                                                             "pooled": {"n10": t10, "n01": t01, "p": tp, "verdict": pooled},
                                                             "arms": res}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
