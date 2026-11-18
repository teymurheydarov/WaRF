"""Paired comparison of WaRF decisions (development): the same folds as replay_learned.py (repetition 0),
the predictions of two configurations per change, and an exact McNemar test on the changes where they differ.

    python paired.py      # writes paired.log"""
import math
import random
import tempfile
import json
from pathlib import Path

import replay_learned as R

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def predict(panel, aggregate, rep=0):
    R.save_profiles(R.PANEL, panel)
    R.orchestrator._call_agent = R.stub
    rng = random.Random(300 + rep)
    Pd = [i for i in R.ids if R.Y[i] == -1]; N = [i for i in R.ids if R.Y[i] == 1]; rng.shuffle(Pd); rng.shuffle(N)
    folds = [Pd[k::10] + N[k::10] for k in range(10)]
    pred = {}
    for k in range(10):
        train = [i for f in folds[:k] + folds[k + 1:] for i in f]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write("".join(json.dumps(R.session(i, panel)) + "\n" for i in train)); log = Path(f.name)
        cal = R.FoldCalibrator(log)
        R.orchestrator.Calibrator = lambda path, cal=cal: cal
        for i in folds[k]:
            R.CURRENT[0] = i
            pred[i] = R.orchestrator.run_review(R.items[i]["code"], R.items[i]["domain"], R.PANEL, verbose=False,
                                                aggregate=aggregate, log_path=log).decision.value
        log.unlink()
    return pred


def right(pred, i):
    return pred[i] == ("REJECT" if R.Y[i] == -1 else "APPROVE")


def mcnemar(a, b):
    """Exact two-sided McNemar: changes a gets right and b wrong, the reverse, and p."""
    n10 = sum(1 for i in R.ids if right(a, i) and not right(b, i))
    n01 = sum(1 for i in R.ids if right(b, i) and not right(a, i))
    n = n10 + n01
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(n10, n01) + 1)) / 2 ** n) if n else 1.0
    return n10, n01, p


if __name__ == "__main__":
    P = {("5 personas", "logodds"): predict(R.personas, "logodds"), ("14 seats", "logodds"): predict(R.seats, "logodds"),
         ("14 seats", "learned"): predict(R.seats, "learned")}
    say("Exact McNemar on 800 RocksDB changes, repetition 0 of replay_learned.py's folds")
    for a, b in ((("14 seats", "learned"), ("14 seats", "logodds")), (("14 seats", "logodds"), ("5 personas", "logodds")),
                 (("14 seats", "learned"), ("5 personas", "logodds"))):
        n10, n01, p = mcnemar(P[a], P[b])
        say(f"  {' '.join(a):<20} vs {' '.join(b):<20}: {n10} vs {n01} changes, p = {p:.3f}")
    (Path(__file__).resolve().parent / "paired.log").write_text("\n".join(out) + "\n", encoding="utf-8")
