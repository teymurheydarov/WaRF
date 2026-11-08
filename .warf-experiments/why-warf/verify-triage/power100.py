"""Power of the trust-AUROC and AURC comparisons: plant a trust signal of known strength on the
five-Jev panel's verdicts and count how often the paired interval against the single Jev agent
shows the panel better. Also the excess-AURC (AURC minus oracle AURC) difference with an interval."""
import math
import random
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                    # noqa: E402
from systems100 import S, truth                        # noqa: E402

rng = random.Random(77)
o = S["jev5_R1_band"]
sj = S["jev_single"]


def sigma_for(target):
    lo_, hi_ = -10.0, 10.0
    for _ in range(100):
        m = (lo_ + hi_) / 2
        if 0.5 * (1 + math.erf(m / math.sqrt(2))) < target:
            lo_ = m
        else:
            hi_ = m
    return 1 / ((lo_ + hi_) / 2 * math.sqrt(2))


for target in (0.65, 0.70, 0.75, 0.80):
    sigma = sigma_for(target)
    n, det_t, det_a, ta = 40, 0, 0, []
    for s in range(n):
        c = [o["correct"][i] + rng.gauss(0, sigma) for i in range(100)]
        ta.append(V.trust_auroc(o["correct"], c))
        dt, da = [], []
        for idx in V.boot_indices(truth, 1000, 500 + s):
            co = [o["correct"][i] for i in idx]
            cc = [c[i] for i in idx]
            cs = [sj["correct"][i] for i in idx]
            ks = [sj["c"][i] for i in idx]
            dt.append(V.trust_auroc(co, cc) - V.trust_auroc(cs, ks))
            da.append(V.aurc(V.curve(co, cc)) - V.aurc(V.curve(cs, ks)))
        det_t += V.ci(dt)[0] > 0
        det_a += V.ci(da)[1] < 0
    print(f"planted trust AUROC ~{target:.2f}: realised mean {sum(ta) / n:.3f} (single Jev 0.601); panel significantly better"
          f" on trust AUROC in {det_t}/{n}, on AURC in {det_a}/{n}", flush=True)

# excess AURC: AURC minus the oracle AURC at the system's own accuracy
for X, Y in (("jev5_R1_band", "jev_single"), ("jev5_R1_band", "jev5_seat_SKEPTIC"), ("laya5_R1_band", "laya_single")):
    def ex(sys_, idx):
        co = [S[sys_]["correct"][i] for i in idx]
        return V.aurc(V.curve(co, [S[sys_]["c"][i] for i in idx])) - V.aurc(V.curve(co, co))
    full = list(range(100))
    obs = ex(X, full) - ex(Y, full)
    d = [ex(X, idx) - ex(Y, idx) for idx in V.boot_indices(truth, 2000, 5)]
    lo, hi = V.ci(d)
    print(f"excess AURC {X} - {Y}: {obs:+.3f} [{lo:+.3f}, {hi:+.3f}] p {V.boot_p(d):.3f}")
