"""Paired bootstrap (commits resampled within each label) for the 100-commit comparisons.
Usage: python boot100.py SEED [B]"""
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                        # noqa: E402
from systems100 import S, P5, PS, PL, truth, sel, five, std, lay   # noqa: E402

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 101
NB = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
ids = [s["id"] for s in sel]


def add(name, d, c):
    S[name] = {"d": d, "c": c, "correct": [1 if x == t else 0 for x, t in zip(d, truth)]}


# reruns scored with d = (p > 0.5), as the findings do (1 review in rerun_A has p = 0.50)
add("jev_rerunA_pgt", S["jev_rerunA"]["d_pgt"], S["jev_rerunA"]["c"])
# vote margin |mean vote| (no theta), the findings' definition; band then margin as an extra
for pref, m, P in (("jev5", five, P5), ("jevdef", std, PS), ("laya5", lay, PL)):
    nv = []
    for i in ids:
        vv = [v["vote"] for v in m[i]["votes"]]
        nv.append(round(abs(sum(vv) / len(vv)), 6))
    add(f"{pref}_R1_vmargin", P["r1"]["d"], nv)
    if pref != "jevdef":
        nf = []
        for i in ids:
            r = m[i]
            vv = [v["vote"] for v in (r["debate"]["votes"] if "debate" in r else r["votes"])]
            nf.append(round(abs(sum(vv) / len(vv)), 6))
        add(f"{pref}_fin_vmargin", P["fin"]["d"], nf)
# block rule: d = REJECT on every commit, ranked by p
for nm, p in (("jev_single", S["jev_single"]["p"]), ("claude", S["claude"]["p"]),
              ("jevdef_seat_SKEPTIC", S["jevdef_seat_SKEPTIC"]["p"])):
    add(f"block_{nm}", [-1] * 100, p)

high = {"jev5_R1": [1 if b == "HIGH" else 0 for b in P5["r1"]["band"]],
        "jev5_fin": [1 if b == "HIGH" else 0 for b in P5["fin"]["band"]],
        "jevdef_R1": [1 if b == "HIGH" else 0 for b in PS["r1"]["band"]],
        "laya5_R1": [1 if b == "HIGH" else 0 for b in PL["r1"]["band"]]}


def stats(sys_, idx):
    cor = [sys_["correct"][i] for i in idx]
    key = [sys_["c"][i] for i in idx]
    cum = V.curve(cor, key)
    return cum, V.aurc(cum), V.trust_auroc(cor, key), 1 - sum(cor) / len(cor)


def compare(X, Y, idxs, hk=None):
    """Differences X - Y over the resamples: AURC, trust AUROC, gain, accuracy at the HIGH share."""
    full = list(range(100))
    cx, ax, tx, ex = stats(S[X], full)
    cy, ay, ty, ey = stats(S[Y], full)
    k0 = sum(high[hk]) if hk else None
    obs = {"aurc": ax - ay, "trust": tx - ty, "gain": (ex - ax) - (ey - ay),
           "acc_hi": (V.acc_at(cx, k0) - V.acc_at(cy, k0)) if hk else None,
           "ax": ax, "ay": ay, "tx": tx, "ty": ty}
    da, dt, dg, dh, aX, aY, tX, tY = [], [], [], [], [], [], [], []
    nk0 = 0
    for idx in idxs:
        cx, ax, tx, ex = stats(S[X], idx)
        cy, ay, ty, ey = stats(S[Y], idx)
        da.append(ax - ay)
        dt.append(tx - ty)
        dg.append((ex - ax) - (ey - ay))
        aX.append(ax); aY.append(ay); tX.append(tx); tY.append(ty)
        if hk:
            k = sum(high[hk][i] for i in idx)
            if k > 0:
                dh.append(V.acc_at(cx, k) - V.acc_at(cy, k))
            else:
                nk0 += 1
    res = {"obs": obs, "aurc": (V.ci(da), V.boot_p(da)), "trust": (V.ci(dt), V.boot_p(dt)),
           "gain": (V.ci(dg), V.boot_p(dg)), "ax": V.ci(aX), "ay": V.ci(aY), "tx": V.ci(tX), "ty": V.ci(tY)}
    if hk:
        res["acc_hi"] = (V.ci(dh), V.boot_p(dh), len(dh))
    return res


def show(X, Y, res):
    o = res["obs"]
    (lo, hi), p = res["aurc"]
    (tlo, thi), tp = res["trust"]
    (glo, ghi), gp = res["gain"]
    s = (f"{X:<22} - {Y:<22} AURC {o['ax']:.3f}-{o['ay']:.3f} = {o['aurc']:+.3f} [{lo:+.3f},{hi:+.3f}] p {p:.3f} | "
         f"trust {o['trust']:+.3f} [{tlo:+.3f},{thi:+.3f}] p {tp:.3f} | gain {o['gain']:+.3f} [{glo:+.3f},{ghi:+.3f}]")
    if "acc_hi" in res:
        (hlo, hhi), hp, nk = res["acc_hi"]
        s += f" | accHI {o['acc_hi']:+.3f} [{hlo:+.3f},{hhi:+.3f}] p {hp:.3f} (k>0 in {nk})"
    print(s)


if __name__ == "__main__":
    idxs = V.boot_indices(truth, NB, SEED)
    print(f"seed {SEED}, {NB} resamples within labels\n")
    pairs = [
        ("jev5_R1_band", "jev_single", "jev5_R1"),
        ("jev5_R1_lam", "jev_single", "jev5_R1"),
        ("jev5_R1_vmargin", "jev_single", "jev5_R1"),
        ("jev5_R1_margin", "jev_single", "jev5_R1"),
        ("jev5_fin_band", "jev_single", "jev5_fin"),
        ("jev5_fin_lam", "jev_single", None),
        ("jev5_fin_vmargin", "jev_single", None),
        ("jevdef_R1_band", "jev_single", "jevdef_R1"),
        ("jevdef_R1_lam", "jev_single", None),
        ("jevdef_R1_vmargin", "jev_single", None),
        ("jev5_R1_band", "jev_rerunA_pgt", "jev5_R1"),
        ("jev5_R1_band", "jev_rerunA", None),
        ("jev5_R1_band", "jev_rerunB", "jev5_R1"),
        ("jev_rerunA_pgt", "jev_single", None),
        ("jev_rerunB", "jev_single", None),
        ("jev5_R1_band", "jev5_seat_SKEPTIC", "jev5_R1"),
        ("jev5_R1_lam", "jev5_seat_SKEPTIC", None),
        ("jev5_R1_vmargin", "jev5_seat_SKEPTIC", None),
        ("jevdef_R1_band", "jevdef_seat_SKEPTIC", "jevdef_R1"),
        ("jevdef_R1_lam", "jevdef_seat_SKEPTIC", None),
        ("jevdef_R1_vmargin", "jevdef_seat_SKEPTIC", None),
        ("jev5_R1_band", "jev5_seat_ADVOCATE", None),
        ("jev5_R1_band", "jev5_seat_AUDITOR", None),
        ("jev5_R1_band", "jev5_seat_TEST-FOCUSED", None),
        ("jev5_R1_band", "jev5_seat_BOUNDARY", None),
        ("jev5_R1_meanp", "jev_single", "jev5_R1"),
        ("jev5_meanp_verdict", "jev_single", None),
        ("claude", "jev_single", None),
        ("block_jev_single", "block_claude", None),
        ("laya5_R1_band", "laya_single", "laya5_R1"),
        ("laya5_R1_lam", "laya_single", None),
        ("laya5_R1_vmargin", "laya_single", None),
        ("laya5_fin_band", "laya_single", None),
        ("laya5_fin_lam", "laya_single", None),
        ("laya5_fin_vmargin", "laya_single", None),
        ("laya5_R1_band", "laya5_seat_SKEPTIC", None),
        ("laya5_R1_lam", "laya5_seat_SKEPTIC", None),
        ("laya5_R1_vmargin", "laya5_seat_SKEPTIC", None),
        ("laya5_R1_band", "laya5_seat_ADVOCATE", None),
        ("laya5_R1_band", "laya5_seat_AUDITOR", None),
        ("laya5_R1_band", "laya5_seat_TEST-FOCUSED", None),
        ("laya5_R1_band", "laya5_seat_BOUNDARY", None),
        ("laya5_R1_meanp", "laya_single", None),
    ]
    out = {}
    for X, Y, hk in pairs:
        res = compare(X, Y, idxs, hk)
        out[(X, Y)] = res
        show(X, Y, res)
    print("\nSingle-system intervals (percentile, same resamples):")
    for X in ("jev_single", "jev5_R1_band", "jevdef_R1_band", "jev5_R1_meanp", "claude", "laya_single", "laya5_R1_band"):
        r = out.get((X, "jev_single")) or out.get((X, "laya_single")) or compare(X, "jev_single", idxs)
        if X in ("jev_single",):
            r = out[("jev5_R1_band", "jev_single")]
            print(f"  {X:<22} AURC [{r['ay'][0]:.3f},{r['ay'][1]:.3f}]  trust AUROC [{r['ty'][0]:.3f},{r['ty'][1]:.3f}]")
        elif X == "laya_single":
            r = out[("laya5_R1_band", "laya_single")]
            print(f"  {X:<22} AURC [{r['ay'][0]:.3f},{r['ay'][1]:.3f}]  trust AUROC [{r['ty'][0]:.3f},{r['ty'][1]:.3f}]")
        else:
            print(f"  {X:<22} AURC [{r['ax'][0]:.3f},{r['ax'][1]:.3f}]  trust AUROC [{r['tx'][0]:.3f},{r['tx'][1]:.3f}]")
