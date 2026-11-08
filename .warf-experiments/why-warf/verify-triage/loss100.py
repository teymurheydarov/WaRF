"""Claim 5 extra: same verdicts, WaRF's band vs |mean p - 0.5| as the confidence (paired, seed 5)."""
import sys
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                       # noqa: E402
import boot100 as BB                     # noqa: E402
from systems100 import truth             # noqa: E402

idxs = V.boot_indices(truth, 2000, 5)
for X, Y in (("jev5_R1_band", "jev5_R1_meanp"), ("laya5_R1_band", "laya5_R1_meanp"), ("jevdef_R1_band", "jevdef_R1_meanp")):
    r = BB.compare(X, Y, idxs)
    (lo, hi), p = r["aurc"]
    (tlo, thi), tp = r["trust"]
    print(f"{X} - {Y}: AURC {r['obs']['aurc']:+.3f} [{lo:+.3f}, {hi:+.3f}] p {p:.3f}; trust {r['obs']['trust']:+.3f} [{tlo:+.3f}, {thi:+.3f}] p {tp:.3f}")
