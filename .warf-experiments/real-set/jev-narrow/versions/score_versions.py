"""Score jev-1.13 against jev-1.14 and the two as WaRF seats (development). Fixed before scoring:
primary = the mean of the two versions' N (each: mean logit of the 7 checks' hunk max); also each version
alone, the verdicts, and Spearman between the versions next to Spearman between two runs of 1.14.

    python score_versions.py     # writes score_versions.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from jevscore import GENERIC, auc, boot_diff, ids, load, loo_size, meanlg, ref_N, within  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s)


models = {json.loads(l)["model"] for l in (HERE / "answers_jev-1.13.jsonl").open(encoding="utf-8")}
w13, h13 = load(HERE / "answers_jev-1.13.jsonl")
w14, h14 = load(HERE.parent / "answers.jsonl")
w14b, h14b = load(HERE.parent / "repeat" / "run2.jsonl")
N14 = ref_N(); N13 = {i: meanlg(w13, h13, GENERIC, i) for i in ids}
N14b = {i: meanlg(w14b, h14b, GENERIC, i) for i in ids}
V14 = {i: w14[i]["verdict"] for i in ids}; V13 = {i: w13[i]["verdict"] for i in ids}


def rank(d):
    return {k: r for r, k in enumerate(sorted(d, key=d.get))}


def spear(a, b):
    ra, rb, n = rank(a), rank(b), len(a)
    return 1 - 6 * sum((ra[i] - rb[i]) ** 2 for i in ids) / (n * (n * n - 1))


S = {"N jev-1.14 (reference)": N14, "N jev-1.13": N13,
     "WaRF seats: mean N of 1.13 and 1.14 (PRIMARY)": {i: (N13[i] + N14[i]) / 2 for i in ids},
     "V jev-1.14": V14, "V jev-1.13": V13, "V mean of both": {i: (V13[i] + V14[i]) / 2 for i in ids}}
say(f"jev-1.13 answers from {sorted(models)}")
say(f"Spearman N: 1.13 vs 1.14 {spear(N13, N14):.3f}; two runs of 1.14 {spear(N14b, N14):.3f}")
say(f"Spearman V: 1.13 vs 1.14 {spear(V13, V14):.3f}")
say(f"{'score':<46} {'AUC':>6} {'within':>7} {'LOO size':>9}  d vs N 1.14 [95%]")
for name, s in S.items():
    d, lo, hi = boot_diff(s, N14)
    say(f"{name:<46} {auc(s):6.3f} {within(s):7.3f} {loo_size(s):9.3f}  {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
(HERE / "score_versions.log").write_text("\n".join(out) + "\n", encoding="utf-8")
