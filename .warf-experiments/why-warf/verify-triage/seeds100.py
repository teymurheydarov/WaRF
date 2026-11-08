"""How stable are the borderline intervals? Ten seeds of 2,000 resamples and one of 20,000."""
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                       # noqa: E402
import boot100 as BB                     # noqa: E402
from systems100 import truth             # noqa: E402

pairs = [("jev5_R1_band", "jev_single", "jev5_R1"),
         ("jevdef_R1_band", "jev_single", "jevdef_R1"),
         ("jev5_R1_band", "jev5_seat_ADVOCATE", None),
         ("jev5_R1_band", "jev5_seat_AUDITOR", None),
         ("jev5_R1_band", "jev5_seat_TEST-FOCUSED", None),
         ("laya5_R1_band", "laya5_seat_AUDITOR", None),
         ("laya5_R1_band", "laya5_seat_SKEPTIC", None)]

if __name__ == "__main__":
    for seed in list(range(1, 11)):
        idxs = V.boot_indices(truth, 2000, seed)
        line = [f"seed {seed:>2}"]
        for X, Y, hk in pairs:
            r = BB.compare(X, Y, idxs, hk)
            (lo, hi), p = r["aurc"]
            s = f"{Y[-10:]}:AURC[{lo:+.3f},{hi:+.3f}]p{p:.3f}"
            if hk:
                (hlo, hhi), hp, nk = r["acc_hi"]
                s += f" accHI[{hlo:+.3f},{hhi:+.3f}]p{hp:.3f}"
            line.append(s)
        print(" | ".join(line), flush=True)
    idxs = V.boot_indices(truth, 20000, 999)
    print("\n20,000 resamples (seed 999):")
    for X, Y, hk in pairs:
        r = BB.compare(X, Y, idxs, hk)
        (lo, hi), p = r["aurc"]
        s = f"  {X} - {Y}: AURC {r['obs']['aurc']:+.3f} [{lo:+.3f},{hi:+.3f}] p {p:.3f}"
        (tlo, thi), tp = r["trust"]
        s += f"; trust {r['obs']['trust']:+.3f} [{tlo:+.3f},{thi:+.3f}] p {tp:.3f}"
        if hk:
            (hlo, hhi), hp, nk = r["acc_hi"]
            s += f"; acc at HIGH share {r['obs']['acc_hi']:+.3f} [{hlo:+.4f},{hhi:+.4f}] p {hp:.3f}"
        print(s, flush=True)
