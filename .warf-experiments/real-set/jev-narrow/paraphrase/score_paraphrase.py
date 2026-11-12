"""Score the paraphrase ensemble (run_paraphrase.py) with jevscore; writes score.log in this folder.

Four scores, fixed before the results were seen (primary first):
- P21 (primary): per generic check, mean logit of hunk max over the original answer (../answers.jsonl)
  and its two paraphrases; then mean over the 7 checks.
- P14: the 14 paraphrases alone, mean logit of hunk max.
- Pa, Pb: paraphrase set a alone, set b alone (7 checks each), to show how much one rewording moves.
Diagnostics only (not scores): per-check Pearson of item logits original vs paraphrase, verdict re-ask AUC."""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as J  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s)


ow, oh = J.load(J.HERE / "answers.jsonl")
pw, ph = J.load(HERE / "answers_paraphrase.jsonl")
G = J.GENERIC
L = lambda w, h, q, i: J.lg(J.hmax(w, h, i, q))

S = {
    "P21 (primary): orig + 2 paraphrases": {i: sum((L(ow, oh, q, i) + L(pw, ph, q + "_a", i) + L(pw, ph, q + "_b", i)) / 3
                                                  for q in G) / 7 for i in J.ids},
    "P14: 14 paraphrases alone": {i: J.meanlg(pw, ph, [q + s for q in G for s in ("_a", "_b")], i) for i in J.ids},
    "Pa: paraphrase set a": {i: J.meanlg(pw, ph, [q + "_a" for q in G], i) for i in J.ids},
    "Pb: paraphrase set b": {i: J.meanlg(pw, ph, [q + "_b" for q in G], i) for i in J.ids},
}
R = J.ref_N()
cost = sum(float((json.loads(l).get("usage") or {}).get("cost") or 0)
           for l in (HERE / "answers_paraphrase.jsonl").open(encoding="utf-8"))
nrec = sum(1 for _ in (HERE / "answers_paraphrase.jsonl").open(encoding="utf-8"))
say(f"{nrec} calls, cost ${cost:.4f}; added-lines AUC {J.auc(J.A):.3f}")
say(f"{'score':<40} {'AUC':>6} {'within':>7} {'LOO':>6} {'d vs N':>7} {'95% CI':>17}")
say(f"{'ref N (generic 7, frozen)':<40} {J.auc(R):6.3f} {J.within(R):7.3f} {J.loo_size(R):6.3f}")
res = {}
for name, s in S.items():
    d, lo, hi = J.boot_diff(s, R)
    res[name] = dict(auc=J.auc(s), within=J.within(s), loo=J.loo_size(s), d=d, lo=lo, hi=hi)
    r = res[name]
    say(f"{name:<40} {r['auc']:6.3f} {r['within']:7.3f} {r['loo']:6.3f} {d:+7.3f} [{lo:+.3f}, {hi:+.3f}]")


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


say("\ndiagnostics: per-check logit(hunk max) Pearson over items, and single-question AUC")
say(f"{'check':<10} {'r(o,a)':>7} {'r(o,b)':>7} {'r(a,b)':>7} {'AUC o':>6} {'AUC a':>6} {'AUC b':>6}")
for q in G:
    o = [L(ow, oh, q, i) for i in J.ids]; a = [L(pw, ph, q + "_a", i) for i in J.ids]; b = [L(pw, ph, q + "_b", i) for i in J.ids]
    au = lambda v: J.auc(dict(zip(J.ids, v)))
    say(f"{q:<10} {pearson(o, a):7.2f} {pearson(o, b):7.2f} {pearson(a, b):7.2f} {au(o):6.3f} {au(a):6.3f} {au(b):6.3f}")
o7 = [R[i] for i in J.ids]
say(f"mean-logit N vs P14 Pearson {pearson(o7, [S['P14: 14 paraphrases alone'][i] for i in J.ids]):.2f}; "
    f"Pa vs Pb {pearson([S['Pa: paraphrase set a'][i] for i in J.ids], [S['Pb: paraphrase set b'][i] for i in J.ids]):.2f}")
say(f"verdict re-asked (whole): AUC {J.auc({i: pw[i]['verdict'] for i in J.ids}):.3f} vs original {J.auc({i: ow[i]['verdict'] for i in J.ids}):.3f}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "scores.json").write_text(json.dumps({"cost": cost, "calls": nrec, "scores": res}, indent=1), encoding="utf-8")
