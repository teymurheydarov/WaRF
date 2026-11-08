"""Claim 8: the 12-file persona experiment (persona_v3), stored data only."""
import math
import random
import sys
from pathlib import Path, PurePath

sys.path.insert(0, "C:/workdir/warf/WaRF")
sys.path.insert(0, "C:/workdir/warf/WaRF/tools")
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                            # noqa: E402
from _groundtruth import corpus_truth, truth_for               # noqa: E402
from compare_pools import load_pool, uniform_replay, agreement  # noqa: E402

home = Path(V.EXP)
truths = corpus_truth()
pool = load_pool(home, "persona_v3")
items = sorted(pool.items())
order = pool[items[0][0]]["_order"]
print(f"persona_v3: {len(items)} files; order {order}")


def name(a):
    return PurePath(a.replace("\\", "/")).name


def is_val(a):
    return "validation" in [p.lower() for p in PurePath(a.replace("\\", "/")).parts]


for tname, tf in (("current", lambda a, s: truth_for(a, truths).x_star if truth_for(a, truths) else s["oracle"]["x_star"]),
                  ("stored", lambda a, s: s["oracle"]["x_star"])):
    print(f"\n--- truth: {tname}")
    rows = []
    for a, s in items:
        t = tf(a, s)
        # my own uniform replay, to check compare_pools.uniform_replay
        rank = {n: i for i, n in enumerate(order)}
        vs = sorted(s["votes"], key=lambda v: rank.get(v["agent"], 99))
        d_me, b_me, lam_me, _, _ = V.warf_round([v["vote"] for v in vs], [0.5] * len(vs), s["domain"], early_stop=True)
        ud, uc, ul, uk = uniform_replay(s)
        assert (V.xv(ud), uc) == (d_me, b_me), (a, ud, uc, d_me, b_me)
        votes = {v["agent"]: v["vote"] for v in s["votes"]}
        rows.append({"a": a, "t": t, "ud": V.xv(ud), "uc": uc, "ul": ul, "rd": V.xv(s["decision"]), "rc": s["confidence"],
                     "agree": agreement(s), "votes": votes, "val": is_val(a)})
        print(f"  {name(a):<24} truth {t:+d} uniform {ud:<7} {uc:<6} as run {s['decision']:<7} {s['confidence']:<6}"
              f" agree {agreement(s):.2f} val {is_val(a)} votes " + "".join("A" if votes[n] == 1 else "R" for n in order))
    n = len(rows)
    ur = sum(r["ud"] == r["t"] for r in rows)
    rr = sum(r["rd"] == r["t"] for r in rows)
    print(f"  WaRF uniform right {ur}/{n}; as run {rr}/{n}")
    hi = [r for r in rows if r["uc"] == "HIGH"]
    hr = sum(r["ud"] == r["t"] for r in hi)
    lo, up = V.cp_interval(hr, len(hi))
    print(f"  uniform HIGH {len(hi)}: right {hr}, CP [{lo:.2f}, {up:.2f}], validation {sum(r['val'] for r in hi)}, agreement {[r['agree'] for r in hi]}")
    hm = [r for r in rows if r["uc"] in ("HIGH", "MEDIUM")]
    hmr = [r for r in rows if r["rc"] in ("HIGH", "MEDIUM")]
    print(f"  HIGH + MEDIUM uniform {sum(r['ud'] == r['t'] for r in hm)}/{len(hm)} (wrong: {[name(r['a']) for r in hm if r['ud'] != r['t']]});"
          f" as run {sum(r['rd'] == r['t'] for r in hmr)}/{len(hmr)}")
    for ag in order:
        k = sum(r["votes"][ag] == r["t"] for r in rows)
        p5 = math.comb(k, 5) / math.comb(n, 5) if k >= 5 else 0.0
        print(f"  {ag:<13} alone right {k}/{n}; P(5 random verdicts all right) = {p5:.3f}")
    # band / agreement as a trust ranking: permutation p for AURC
    cor = [1 if r["ud"] == r["t"] else 0 for r in rows]
    for kname, key in (("band,|L|", [(V.BAND_RANK[r["uc"]], round(abs(r["ul"]), 6)) for r in rows]),
                       ("agreement", [round(r["agree"], 6) for r in rows])):
        obs = V.aurc(V.curve(cor, key))
        # exact permutation distribution: all placements of the wrong verdicts
        nw = n - sum(cor)
        from itertools import combinations
        vals = []
        for wrong in combinations(range(n), nw):
            c = [0 if i in wrong else 1 for i in range(n)]
            vals.append(V.aurc(V.curve(c, key)))
        p = sum(1 for v in vals if v <= obs + 1e-12) / len(vals)
        print(f"  {kname:<10} AURC {obs:.3f} vs random {1 - sum(cor) / n:.3f}; exact permutation p {p:.3f}"
              f" ({len(vals)} placements); trust AUROC {V.trust_auroc(cor, key) if 0 < sum(cor) < n else float('nan'):.3f}")
    rest = [r for r in rows if r["uc"] != "HIGH"]
    a_, b_ = hr, len(hi) - hr
    c_ = sum(r["ud"] == r["t"] for r in rest)
    d_ = len(rest) - c_
    print(f"  HIGH vs rest Fisher p {V.fisher_two_sided(a_, b_, c_, d_):.3f} ({a_}/{a_ + b_} vs {c_}/{c_ + d_})")
