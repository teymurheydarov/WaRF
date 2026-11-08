"""My own controls on the 100 commits.
Negative: shuffled labels (curves must be flat at 0.5; the main paired interval must exclude 0 in
about 5 % of shuffles); two independent random confidences on the same verdicts.
Positive: oracle confidence; a planted trust signal of known strength on the panel's verdicts.
Tie check: exact tie averaging against random tie orders."""
import math
import random
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                    # noqa: E402
from systems100 import S, truth                        # noqa: E402

rng = random.Random(2026)
NAMES = ["jev_single", "jev_rerunA", "jev_rerunB", "laya_single", "claude", "jev5_R1_band", "jev5_R1_lam", "jev5_fin_band",
         "jevdef_R1_band", "laya5_R1_band", "laya5_fin_band", "jev5_seat_SKEPTIC", "jev5_R1_meanp"]


def corr_of(d, t):
    return [1 if a == b else 0 for a, b in zip(d, t)]


def paired_ci(X, Y, t, B, seed):
    """X, Y: (d, c) pairs; t: truth. Returns AURC(X) - AURC(Y) and its percentile interval."""
    cx, cy = corr_of(X[0], t), corr_of(Y[0], t)
    obs = V.aurc(V.curve(cx, X[1])) - V.aurc(V.curve(cy, Y[1]))
    diffs = []
    for idx in V.boot_indices(t, B, seed):
        a = V.aurc(V.curve([cx[i] for i in idx], [X[1][i] for i in idx]))
        b = V.aurc(V.curve([cy[i] for i in idx], [Y[1][i] for i in idx]))
        diffs.append(a - b)
    lo, hi = V.ci(diffs)
    return obs, lo, hi


print("A. Negative control: 1,000 label shuffles (50/50 kept); mean selective accuracy at 10/25/50/75/100 % and AURC")
acc = {n: [[0.0] * 5, 0.0] for n in NAMES}
for _ in range(1000):
    t = truth[:]
    rng.shuffle(t)
    for n in NAMES:
        cum = V.curve(corr_of(S[n]["d"], t), S[n]["c"])
        for j, k in enumerate((10, 25, 50, 75, 100)):
            acc[n][0][j] += cum[k] / k / 1000
        acc[n][1] += V.aurc(cum) / 1000
worst = 0.0
for n in NAMES:
    worst = max(worst, max(abs(a - 0.5) for a in acc[n][0]))
    print(f"   {n:<20} " + "/".join(f"{a:.3f}" for a in acc[n][0]) + f"   AURC {acc[n][1]:.3f}")
print(f"   largest |mean accuracy - 0.5| over systems and coverages: {worst:.3f}")

print("\nB. Calibration under the null: 200 label shuffles, paired 95 % interval (1,000 resamples) for"
      " AURC(five-Jev band) - AURC(single Jev); share of intervals excluding 0 should be near 0.05")
excl = 0
tot = 200
for s in range(tot):
    t = truth[:]
    rng.shuffle(t)
    obs, lo, hi = paired_ci((S["jev5_R1_band"]["d"], S["jev5_R1_band"]["c"]), (S["jev_single"]["d"], S["jev_single"]["c"]), t, 1000, 7000 + s)
    excl += (lo > 0 or hi < 0)
print(f"   excluded 0 in {excl}/{tot} = {excl / tot:.3f} (binomial 95 % range for 0.05: about 0.02 to 0.08)")

print("\nC. Negative control: the same verdicts (single Jev) with two independent random confidences, 100 draws")
excl = 0
for s in range(100):
    c1 = [rng.random() for _ in range(100)]
    c2 = [rng.random() for _ in range(100)]
    obs, lo, hi = paired_ci((S["jev_single"]["d"], c1), (S["jev_single"]["d"], c2), truth, 1000, 9000 + s)
    excl += (lo > 0 or hi < 0)
print(f"   interval excluded 0 in {excl}/100")

print("\nD. Positive controls")
o = S["jev5_R1_band"]
obs, lo, hi = paired_ci((o["d"], o["correct"]), (S["jev_single"]["d"], S["jev_single"]["c"]), truth, 2000, 11)
print(f"   oracle confidence on the five-Jev panel's verdicts minus single Jev: AURC {obs:+.3f} [{lo:+.3f}, {hi:+.3f}]")
cum = V.curve(o["correct"], o["correct"])
print(f"   oracle curve, five-Jev panel: " + "/".join(f"{cum[k] / k:.2f}" for k in (10, 25, 50, 53, 75, 100)) + " at k = 10/25/50/53/75/100")
for target in (0.70, 0.80, 0.90):
    # planted: c = right + N(0, sigma) gives trust AUROC Phi(1 / (sigma * sqrt 2)) in expectation
    z = 0.0
    lo_, hi_ = -10.0, 10.0
    for _ in range(100):
        m = (lo_ + hi_) / 2
        if 0.5 * (1 + math.erf(m / math.sqrt(2))) < target:
            lo_ = m
        else:
            hi_ = m
    sigma = 1 / ((lo_ + hi_) / 2 * math.sqrt(2))
    det_better, det_auroc, n = 0, 0, 40
    ta, ad = [], []
    for s in range(n):
        c = [o["correct"][i] + rng.gauss(0, sigma) for i in range(100)]
        ta.append(V.trust_auroc(o["correct"], c))
        obs, lo, hi = paired_ci((o["d"], c), (S["jev_single"]["d"], S["jev_single"]["c"]), truth, 1000, 12000 + s)
        ad.append(obs)
        det_better += hi < 0
    print(f"   planted trust AUROC ~{target:.2f} (sigma {sigma:.2f}) on the panel's verdicts (acc 0.53): mean trust AUROC"
          f" {sum(ta) / n:.3f}, mean AURC diff vs single {sum(ad) / n:+.3f}; panel significantly better in {det_better}/{n}")

print("\nE. Tie averaging vs 4,000 random tie orders (five-Jev band, single Jev, five-Laya band)")
for nm in ("jev5_R1_band", "jev_single", "laya5_R1_band", "jev5_R1_bandonly"):
    s = S[nm]
    exact = V.curve(s["correct"], s["c"])
    mean = [0.0] * 101
    aur = 0.0
    for _ in range(4000):
        key = [(s["c"][i], rng.random()) for i in range(100)]
        cum = V.curve(s["correct"], key)
        for k in range(101):
            mean[k] += cum[k] / 4000
        aur += V.aurc(cum) / 4000
    md = max(abs(mean[k] / k - exact[k] / k) for k in range(1, 101))
    print(f"   {nm:<18} max |accuracy difference| {md:.4f}; AURC exact {V.aurc(exact):.4f} vs random orders {aur:.4f}")
