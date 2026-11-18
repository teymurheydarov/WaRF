"""Score the commit-context test (README.md "Primary analysis", "Secondary") from stored answers; no Jev call.

WaRF's run_review is replayed with the agent call stubbed (as ../../pp-set/score_pp.py): `logodds`, calibration by
stratified 10-fold cross-validation within each set (seed 300 + repetition) from the arm's own answers.
PANEL3 = the stored answers of the fresh runs; PANEL3+CC = the answers of run_cc.py where the item has a commit
context, else the stored ones (the same input).

    python score_cc.py      # writes score_cc.log, score_cc.json"""
import importlib.util
import json
import math
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf import orchestrator  # noqa: E402
from warf.calibration import Calibrator  # noqa: E402
from warf.state import save_profiles  # noqa: E402

SETS = {"DuckDB": ("ddb", EXP / "ddb-set"), "PPSSPP": ("pp", EXP / "pp-set")}
out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def load_panel(set_dir):
    spec = importlib.util.spec_from_file_location(f"panel_{set_dir.name}", set_dir / "panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def answers(path, seats):
    a = {}
    for l in Path(path).open(encoding="utf-8"):
        r = json.loads(l)
        for v in r["votes"]:
            if v["agent"] in seats:
                a[(r["artifact"], v["agent"])] = (v["vote"], v["reasoning"], v["p_reject"])
    return a


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


def mcnemar_counts(a, b, Y, ids):
    right = lambda pred, i: pred[i] == ("REJECT" if Y[i] == -1 else "APPROVE")  # noqa: E731
    return (sum(1 for i in ids if right(a, i) and not right(b, i)),
            sum(1 for i in ids if right(b, i) and not right(a, i)))


def exact_p(n10, n01):
    n = n10 + n01
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(n10, n01) + 1)) / 2 ** n) if n else 1.0


def predict(items, ids, Y, seats, ans, rep):
    by_key = {(s.persona, s.model): s.name for s in seats}
    current = [None]

    def stub(persona, code, domain, **kw):
        vote, reasoning, _ = ans[(current[0], by_key[(persona, kw["model"])])]
        return vote, reasoning, 0, 0, kw["provider"], kw["model"]

    def session(i):
        return {"session_id": i, "domain": items[i]["domain"], "oracle": {"type": "DEVELOPER", "x_star": Y[i]},
                "votes": [{"agent": s.name, "vote": ans[(i, s.name)][0], "persona": s.persona_hash, "provider": "jev",
                           "model": s.model, "reasoning": ans[(i, s.name)][1],
                           **({"question": s.question} if s.question else {})} for s in seats]}

    prof = Path(tempfile.mkdtemp()) / "panel.json"
    save_profiles(prof, seats)
    orchestrator._call_agent = stub
    rng = random.Random(300 + rep)
    P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]; rng.shuffle(P); rng.shuffle(N)
    folds = [P[k::10] + N[k::10] for k in range(10)]
    pred = {}
    for k in range(10):
        train = [i for f in folds[:k] + folds[k + 1:] for i in f]
        log = Path(tempfile.mkdtemp()) / "train.jsonl"
        log.write_text("".join(json.dumps(session(i)) + "\n" for i in train), encoding="utf-8")
        cal = Calibrator(log)
        orchestrator.Calibrator = lambda path, cal=cal: cal
        for i in folds[k]:
            current[0] = i
            pred[i] = orchestrator.run_review(items[i]["code"], items[i]["domain"], prof, verbose=False,
                                              aggregate="logodds", log_path=log).decision.value
    return pred


def ba(pred, Y, sub):
    P = [i for i in sub if Y[i] == -1]; N = [i for i in sub if Y[i] == 1]
    return (sum(pred[i] == "REJECT" for i in P) / len(P) + sum(pred[i] == "APPROVE" for i in N) / len(N)) / 2


def main():
    total = [0, 0]
    res = {}
    for name, (short, set_dir) in SETS.items():
        items = {json.loads(l)["id"]: json.loads(l) for l in (set_dir / "items.jsonl").open(encoding="utf-8")}
        ids = list(items)
        Y = {i: (-1 if items[i]["kind"] == "defective" else 1) for i in ids}
        seats = load_panel(set_dir).panel3()
        names = {s.name for s in seats}
        stored = answers(set_dir / "sessions.jsonl", names)
        cc_rows = {json.loads(l)["id"]: json.loads(l) for l in (HERE / f"cc_{short}.jsonl").open(encoding="utf-8")}
        new = answers(HERE / f"sessions_cc_{short}.jsonl", names)
        with_cc = [i for i in ids if cc_rows[i]["commit_context"]]
        missing = [(i, s) for i in with_cc for s in names if (i, s) not in new]
        if missing:
            say(f"{name}: {len(missing)} answers with commit context missing, the stored answer is used: "
                f"{missing[:4]}")
        ans_cc = {**stored, **{k: v for k, v in new.items() if k[0] in set(with_cc)}}
        arms = {"PANEL3": stored, "PANEL3+CC": ans_cc}
        preds = {arm: [predict(items, ids, Y, seats, a, rep) for rep in range(5)] for arm, a in arms.items()}
        say(f"\n{name}: {len(ids)} changes, {len(with_cc)} with a commit context")
        r = {}
        for arm in arms:
            p0 = preds[arm][0]
            r[arm] = {"ba0": ba(p0, Y, ids), "ba5": sum(ba(p, Y, ids) for p in preds[arm]) / 5}
            say(f"  {arm:<10} {100 * r[arm]['ba0']:5.1f}%  (mean of 5: {100 * r[arm]['ba5']:.1f}%)")
        n10, n01 = mcnemar_counts(preds["PANEL3+CC"][0], preds["PANEL3"][0], Y, ids)
        total[0] += n10; total[1] += n01
        say(f"  right only with CC {n10}, only without {n01}, exact McNemar p = {exact_p(n10, n01):.4f}")
        for vis in ("diff", "needs_other_file"):
            sub = [i for i in ids if Y[i] == -1 and items[i].get("visible") == vis]
            say(f"  defects {vis:<17} {len(sub):3d}: caught " + ", ".join(
                f"{arm} {sum(preds[arm][0][i] == 'REJECT' for i in sub)}" for arm in arms))
        N = [i for i in ids if Y[i] == 1]
        say("  clean changes: false alarms " + ", ".join(
            f"{arm} {sum(preds[arm][0][i] == 'REJECT' for i in N)}" for arm in arms))
        say("  on the items with a commit context: " + ", ".join(
            f"{arm} {100 * ba(preds[arm][0], Y, with_cc):.1f}%" for arm in arms))
        P = [i for i in ids if Y[i] == -1]
        say("  seat AUC without / with commit context: " + ", ".join(
            f"{s} {auc({i: stored[(i, s)][2] for i in ids}, P, N):.3f} / {auc({i: ans_cc[(i, s)][2] for i in ids}, P, N):.3f}"
            for s in sorted(names)))
        res[name] = {**r, "n10": n10, "n01": n01, "p": exact_p(n10, n01)}
    p = exact_p(*total)
    verdict = "CC WINS" if total[0] > total[1] and p < 0.05 else "not shown" if total[0] > total[1] else "no case"
    say(f"\nPRIMARY (both projects): right only with CC {total[0]}, only without {total[1]}, exact McNemar "
        f"p = {p:.4f}  -> {verdict}")
    (HERE / "score_cc.log").write_text("\n".join(out) + "\n", encoding="utf-8")
    (HERE / "score_cc.json").write_text(json.dumps({"primary": {"n10": total[0], "n01": total[1], "p": p,
                                                                "verdict": verdict}, "sets": res}, indent=1),
                                        encoding="utf-8")


if __name__ == "__main__":
    main()
