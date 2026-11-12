"""Score the "beforeafter" lever with ../jevscore.py. Four scores, fixed before the results were seen:
  BA7   (primary) mean logit of the 7 generic checks on the before/after state
  BAV   P(REJECT) of the verdict on the before/after state
  BA7+W7  mean of BA7 and the 7-check mean logit on the whole-diff state (../answers.jsonl, whole only)
  BA7+N   mean of BA7 and the frozen reference ref_N()
Comparators (not new scores): W7, WV (whole-diff checks / verdict, ../answers.jsonl), ref_N, added lines.

    python score_beforeafter.py > score.log"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as J  # noqa: E402

G = J.GENERIC
bw, bh = J.load(HERE / "answers_beforeafter.jsonl")
ww, wh = J.load(HERE.parent / "answers.jsonl")
N = J.ref_N()
BA7 = {i: J.meanlg(bw, {}, G, i) for i in J.ids}
BAV = {i: bw[i]["verdict"] for i in J.ids}
W7 = {i: J.meanlg(ww, {}, G, i) for i in J.ids}
WV = {i: ww[i]["verdict"] for i in J.ids}
scores = [("BA7 (primary)", BA7), ("BAV", BAV),
          ("BA7+W7", {i: (BA7[i] + W7[i]) / 2 for i in J.ids}),
          ("BA7+N", {i: (BA7[i] + N[i]) / 2 for i in J.ids})]
refs = [("W7 whole diff (ref)", W7), ("WV whole diff verdict (ref)", WV), ("ref_N", N),
        ("added lines", {i: float(J.A[i]) for i in J.ids})]

print(f"{'score':28s} {'AUC':>6s} {'within':>6s} {'LOOsz':>6s} {'LOOraw':>6s}   d vs ref_N [95%]        d vs W7 [95%]")
for name, s in scores + refs:
    d, lo, hi = J.boot_diff(s, N)
    d2, lo2, hi2 = J.boot_diff(s, W7)
    raw = J.loo([J.size, (lambda i, s=s: s[i])])   # score used as is (no logit), a check on loo_size's [0,1] rule
    print(f"{name:28s} {J.auc(s):6.3f} {J.within(s):6.3f} {J.loo_size(s):6.3f} {raw:6.3f}   "
          f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]   {d2:+.3f} [{lo2:+.3f}, {hi2:+.3f}]")

# per check, before/after vs whole diff
print("\nper check: AUC / within, before/after vs whole diff")
for q in ["verdict"] + G:
    a = {i: bw[i][q] for i in J.ids}; b = {i: ww[i][q] for i in J.ids}
    print(f"  {q:10s} BA {J.auc(a):.3f} / {J.within(a):.3f}   W {J.auc(b):.3f} / {J.within(b):.3f}")


def spearman(x, y):
    def rk(s):
        o = sorted(J.ids, key=lambda i: s[i]); r = {}
        k = 0
        while k < len(o):
            m = k
            while m + 1 < len(o) and s[o[m + 1]] == s[o[k]]:
                m += 1
            for t in range(k, m + 1):
                r[o[t]] = (k + m) / 2
            k = m + 1
        return r
    rx, ry = rk(x), rk(y); n = len(J.ids); mx = (n - 1) / 2
    num = sum((rx[i] - mx) * (ry[i] - mx) for i in J.ids)
    den = (sum((rx[i] - mx) ** 2 for i in J.ids) * sum((ry[i] - mx) ** 2 for i in J.ids)) ** 0.5
    return num / den


print(f"\nSpearman BA7 vs W7 {spearman(BA7, W7):.3f}, BA7 vs ref_N {spearman(BA7, N):.3f}")
nin = sum(0 <= s[i] <= 1 for s in (BA7, W7, N) for i in J.ids)
print(f"mean-logit values inside [0,1] (where loo_size takes a logit of them): BA7 {sum(0 <= BA7[i] <= 1 for i in J.ids)}, "
      f"W7 {sum(0 <= W7[i] <= 1 for i in J.ids)}, ref_N {sum(0 <= N[i] <= 1 for i in J.ids)}")
cost = sum(float((__import__('json').loads(l).get('usage') or {}).get('cost') or 0)
           for l in (HERE / "answers_beforeafter.jsonl").open(encoding="utf-8"))
print(f"calls {len(bw)}, cost ${cost:.4f}")
