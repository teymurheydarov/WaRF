"""Claim 3: WaRF's REJECT [HIGH] gate against thresholding one agent's p (block rule)."""
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                         # noqa: E402
import boot100 as BB                                       # noqa: E402  (adds block_* systems)
from systems100 import S, P5, PS, truth, sel, five          # noqa: E402

ids = [s["id"] for s in sel]
pj = S["jev_single"]["p"]
pc = S["claude"]["p"]
psk = S["jevdef_seat_SKEPTIC"]["p"]
fixed = [t == -1 for t in truth]


def topk(p, k):
    """Indices of the k highest p and the threshold; reports ties at the cut."""
    order = sorted(range(100), key=lambda i: -p[i])
    thr = p[order[k - 1]]
    n_ge = sum(1 for x in p if x >= thr)
    return set(order[:k]), thr, n_ge


for nm, P in (("defaults", PS["r1"]), ("five-Jev R1", P5["r1"]), ("five-Jev final", P5["fin"])):
    hi = {i for i, b in enumerate(P["band"]) if b == "HIGH"}
    k = len(hi)
    nfix = sum(fixed[i] for i in hi)
    lo, up = V.cp_interval(nfix, k)
    print(f"\n{nm}: HIGH {k}, later fixed {nfix}/{k} = {nfix / k:.3f}  CP [{lo:.2f}, {up:.2f}]")
    for pname, p in (("single Jev", pj), ("Claude", pc), ("defaults SKEPTIC seat", psk)):
        for kk in (16, 17, 20):
            top, thr, nge = topk(p, kk)
            ov = len(hi & top)
            cum = V.curve([1 if f else 0 for f in fixed], p)
            print(f"   {pname:<22} top-{kk} (p >= {thr:.2f}; {nge} commits at or above): HIGH in it {ov}/{k};"
                  f" later fixed among top-{kk} (tie-averaged) {cum[kk]:.2f}")
    # every HIGH among the seat's rejections?
    rej_seat = {i for i in range(100) if S["jevdef_seat_SKEPTIC"]["d"][i] == -1}
    print(f"   defaults SKEPTIC seat rejects {len(rej_seat)} (min p among them {min(psk[i] for i in rej_seat):.2f});"
          f" HIGH inside: {len(hi & rej_seat)}/{k}")

r1 = P5["r1"]
for nrej in (5, 4, 3):
    s = [i for i in range(100) if r1["rejects"][i] == nrej]
    hi = [i for i in s if r1["band"][i] == "HIGH"]
    print(f"five-Jev R1, {nrej} of 5 REJECT: {len(s)} commits, later fixed {sum(fixed[i] for i in s)};"
          f" HIGH among them {len(hi)} (later fixed {sum(fixed[i] for i in hi)})")

# paired bootstrap: HIGH hit rate vs the block rule at the same k
for seed in (101, 202, 303):
    idxs = V.boot_indices(truth, 2000, seed)
    print(f"\nseed {seed}")
    for X, Y, hk in (("jev5_R1_band", "block_jev_single", "jev5_R1"), ("jevdef_R1_band", "block_jev_single", "jevdef_R1"),
                     ("jev5_R1_band", "block_claude", "jev5_R1"), ("jevdef_R1_band", "block_claude", "jevdef_R1")):
        res = BB.compare(X, Y, idxs, hk)
        (lo, hi_), p, nk = res["acc_hi"]
        print(f"   {X:<16} HIGH vs {Y:<18} at k = #HIGH: {res['obs']['acc_hi']:+.3f} [{lo:+.3f}, {hi_:+.3f}] p {p:.3f}")
