"""Freeze the threshold of the two-version WaRF Jev score on the dev set, the same rule as ../freeze.py:
the cut with the best in-sample balanced accuracy on the 132 dev items (ties: lowest cut).
Score M = mean of N(jev-1.13) and N(jev-1.14), N = mean logit of the 7 checks' hunk max.

    python freeze_mix.py      # writes frozen_mix.json"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from jevscore import D, GENERIC, ids, load, meanlg, ref_N  # noqa: E402

w13, h13 = load(HERE / "answers_jev-1.13.jsonl")
N14 = ref_N()
M = {i: (meanlg(w13, h13, GENERIC, i) + N14[i]) / 2 for i in ids}
P = [i for i in ids if D[i]]; Q = [i for i in ids if not D[i]]


def ba(t):
    return (sum(M[i] >= t for i in P) / len(P) + sum(M[i] < t for i in Q) / len(Q)) / 2


t = max(sorted(set(M.values())), key=lambda t: (ba(t), -t))
out = {"mix": {"threshold": t, "dev_ba": round(ba(t), 4)}}
print(out)
(HERE / "frozen_mix.json").write_text(json.dumps(out, indent=1))
