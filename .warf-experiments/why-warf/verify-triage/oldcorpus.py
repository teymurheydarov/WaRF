"""Claims 6 and 7: WaRF's band as a trust signal in the old labelled corpus (.warf/sessions.jsonl,
read only), with stored and current per-file labels, whole corpus and real code only."""
import collections
import random
import sys
from pathlib import PurePath

sys.path.insert(0, "C:/workdir/warf/WaRF")
sys.path.insert(0, "C:/workdir/warf/WaRF/tools")
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                      # noqa: E402
from _groundtruth import corpus_truth, truth_for         # noqa: E402
from warf import engine as E                             # noqa: E402

rows = V.load(f"{V.ROOT}/.warf/sessions.jsonl")
lab = [r for r in rows if isinstance(r.get("oracle"), dict) and r["oracle"].get("x_star") in (1, -1)]
truths = corpus_truth()


def is_validation(r):
    parts = [p.lower() for p in PurePath(r["artifact"].replace("\\", "/")).parts]
    return "validation" in parts


def current(r):
    t = truth_for(r["artifact"], truths)
    return t.x_star if t else r["oracle"]["x_star"]


# ---------------------------------------------------------------- recomputation of logged verdicts
mism = []
for r in lab + [x for x in rows if x not in lab]:
    vv = [v["vote"] for v in r["votes"]]
    ww = [v["omega"] for v in r["votes"]]
    if "debate" in r:
        dv = [v["vote"] for v in r["debate"]["votes"]]
        dw = [v["omega"] for v in r["debate"]["votes"]]
        d, b, lam, norm, k = V.warf_round(dv, dw, r["domain"], early_stop=True)
        lam_log = r["debate"]["sprt_lambda"]
    else:
        d, b, lam, norm, k = V.warf_round(vv, ww, r["domain"], early_stop=True)
        lam_log = r["sprt_lambda"]
        if k != len(vv):
            mism.append((r["session_id"][:8], "votes after a crossing"))
    ok = (V.xv(r["decision"]) == d, r["confidence"] == b, abs(round(lam, 4) - lam_log) < 2e-4)
    if not all(ok):
        mism.append((r["session_id"][:8], PurePath(r["artifact"].replace("\\", "/")).name, r["decision"], r["confidence"],
                     "recomputed", d, b, round(lam, 4), lam_log, "norm", norm, r["domain"], r in lab))
print(f"Recomputed {len(rows)} sessions ({len(lab)} labelled); mismatches: {len(mism)}")
for m in mism:
    print("   ", m)


# ---------------------------------------------------------------- systems
def lam_used(r):
    return r["debate"]["sprt_lambda"] if "debate" in r else r["sprt_lambda"]


def build(sessions, truthf):
    t = [truthf(r) for r in sessions]
    d = [V.xv(r["decision"]) for r in sessions]
    f = [r["votes"][0]["vote"] for r in sessions]
    band = [r["confidence"] for r in sessions]
    key = [(V.BAND_RANK[b], round(abs(lam_used(r)), 6)) for r, b in zip(sessions, band)]
    keyb = [V.BAND_RANK[b] for b in band]
    keyl = [round(abs(lam_used(r)), 6) for r in sessions]
    cw = [1 if a == b else 0 for a, b in zip(d, t)]
    cf = [1 if a == b else 0 for a, b in zip(f, t)]
    return {"t": t, "d": d, "f": f, "band": band, "key": key, "keyb": keyb, "keyl": keyl, "cw": cw, "cf": cf}


def perm_aurc(correct, key, n=4000, seed=3):
    obs = V.aurc(V.curve(correct, key))
    rng = random.Random(seed)
    c = list(correct)
    le = 0
    for _ in range(n):
        rng.shuffle(c)
        le += V.aurc(V.curve(c, key)) <= obs + 1e-12
    return (le + 1) / (n + 1)


def perm_trust(correct, key, n=4000, seed=4):
    obs = V.trust_auroc(correct, key)
    rng = random.Random(seed)
    c = list(correct)
    ge = 0
    for _ in range(n):
        rng.shuffle(c)
        ge += V.trust_auroc(c, key) >= obs - 1e-12
    return (ge + 1) / (n + 1)


def report(name, sessions, truthf, seeds=(13, 113, 213), nb=2000):
    s = build(sessions, truthf)
    n = len(sessions)
    nr = sum(s["cw"])
    nf = sum(s["cf"])
    print(f"\n=== {name}: {n} sessions ({sum(1 for x in s['t'] if x == 1)} APPROVE, {sum(1 for x in s['t'] if x == -1)} REJECT);"
          f" WaRF right {nr}, first agent right {nf}")
    cum = V.curve(s["cw"], s["key"])
    covs = [n * q for q in (0.10, 0.25, 0.50, 0.75, 1.0)]
    print("  selective accuracy at 10/25/50/75/100 % (k = " + "/".join(f"{k:g}" for k in covs) + "):")
    print("    band (linear interp.)  " + "/".join(f"{V.acc_at(cum, k):.3f}" for k in covs))
    print("    band (k rounded)       " + "/".join(f"{V.acc_at_round(cum, k):.3f}" for k in covs))
    a_band = V.aurc(cum)
    a_bandonly = V.aurc(V.curve(s["cw"], s["keyb"]))
    a_lam = V.aurc(V.curve(s["cw"], s["keyl"]))
    a_first_band = V.aurc(V.curve(s["cf"], s["key"]))
    err_w, err_f = 1 - nr / n, 1 - nf / n
    print(f"  AURC band {a_band:.3f} (band only, ties averaged {a_bandonly:.3f}); |Lambda| {a_lam:.3f};"
          f" WaRF random {err_w:.3f}; first agent random {err_f:.3f}; first agent ranked by band {a_first_band:.3f}")
    print(f"  trust AUROC band {V.trust_auroc(s['cw'], s['key']):.3f}  (AURC-perm p {perm_aurc(s['cw'], s['key']):.3f},"
          f" trust-perm p {perm_trust(s['cw'], s['key']):.3f}); band-only {V.trust_auroc(s['cw'], s['keyb']):.3f}")
    # bands
    for b in ("HIGH", "MEDIUM", "LOW"):
        idx = [i for i in range(n) if s["band"][i] == b]
        print(f"    {b:<7} {len(idx):>3} sessions, WaRF right {sum(s['cw'][i] for i in idx):>3}, first agent right {sum(s['cf'][i] for i in idx):>3}")
    hi = [i for i in range(n) if s["band"][i] == "HIGH"]
    hm = [i for i in range(n) if s["band"][i] in ("HIGH", "MEDIUM")]
    lo = [i for i in range(n) if s["band"][i] == "LOW"]
    for nm, grp in (("HIGH only", hi), ("HIGH + MEDIUM", hm)):
        k = len(grp)
        r = sum(s["cw"][i] for i in grp)
        rest = [i for i in range(n) if i not in grp]
        rr = sum(s["cw"][i] for i in rest)
        cpl, cph = V.cp_interval(r, k)
        fp = V.fisher_two_sided(r, k - r, rr, len(rest) - rr)
        exp_r = k * nf / n
        hp = V.hyper_sf(r, n, nf, k)
        print(f"  act on {nm}: {k}/{n} ({k / n:.2f}), right {r}, wrong {k - r}, acc {r / k:.3f} CP [{cpl:.3f}, {cph:.3f}];"
              f" rest {rr}/{len(rest)}, Fisher p {fp:.3f}; first agent on {k} random: {exp_r:.1f} right,"
              f" {k - exp_r:.1f} wrong expected, P(>= {r}) = {hp:.3f}")
    # paired bootstrap within labels
    for seed in seeds:
        idxs = V.boot_indices(s["t"], nb, seed)
        d1, d2, d3, d4, d5, dh, ab = [], [], [], [], [], [], []
        k0 = len(hi)
        for idx in idxs:
            cw = [s["cw"][i] for i in idx]
            cf = [s["cf"][i] for i in idx]
            key = [s["key"][i] for i in idx]
            keyl = [s["keyl"][i] for i in idx]
            c1 = V.curve(cw, key)
            a1 = V.aurc(c1)
            ew = 1 - sum(cw) / len(cw)
            ef = 1 - sum(cf) / len(cf)
            al = V.aurc(V.curve(cw, keyl))
            afb = V.aurc(V.curve(cf, key))
            ab.append(a1)
            d1.append(a1 - ef)
            d2.append(a1 - ew)
            d3.append(al - ef)
            d4.append(afb - ef)
            kk = sum(1 for i in idx if s["band"][i] == "HIGH")
            if kk > 0:
                dh.append(V.acc_at(c1, kk) - (1 - ef))
        print(f"  seed {seed}: AURC band [{V.ci(ab)[0]:.3f}, {V.ci(ab)[1]:.3f}];"
              f" band - first random {a_band - err_f:+.3f} [{V.ci(d1)[0]:+.3f}, {V.ci(d1)[1]:+.3f}] p {V.boot_p(d1):.3f};"
              f" band - WaRF random {a_band - err_w:+.3f} [{V.ci(d2)[0]:+.3f}, {V.ci(d2)[1]:+.3f}] p {V.boot_p(d2):.3f};"
              f" |Lambda| - first random {a_lam - err_f:+.3f} [{V.ci(d3)[0]:+.3f}, {V.ci(d3)[1]:+.3f}];"
              f" first-by-band - first random {a_first_band - err_f:+.3f} [{V.ci(d4)[0]:+.3f}, {V.ci(d4)[1]:+.3f}];"
              f" acc at HIGH share - first {sum(s['cw'][i] for i in hi) / k0 - (1 - err_f):+.3f}"
              f" [{V.ci(dh)[0]:+.3f}, {V.ci(dh)[1]:+.3f}]")
    return s


if __name__ == "__main__":
    print("Labelled sessions per date range:", min(r["created_at"] for r in lab)[:10], "to", max(r["created_at"] for r in lab)[:10])
    s_all = report("stored labels, all", lab, lambda r: r["oracle"]["x_star"])
    report("current per-file labels, all", lab, current)
    real = [r for r in lab if not is_validation(r)]
    val = [r for r in lab if is_validation(r)]
    print(f"\nvalidation sessions {len(val)}: bands {collections.Counter(r['confidence'] for r in val)},"
          f" right {sum(V.xv(r['decision']) == r['oracle']['x_star'] for r in val)}")
    for r in lab:
        if r["confidence"] == "HIGH":
            print(f"   HIGH  {'VAL ' if is_validation(r) else 'REAL'} {r['artifact']:<70} dec {r['decision']:<7} stored {r['oracle']['x_star']:+d}"
                  f" current {current(r):+d} debate {'debate' in r} first agent {r['votes'][0]['agent']} {r['votes'][0]['vote']:+d}")
    report("stored labels, real code only", real, lambda r: r["oracle"]["x_star"])
    report("current per-file labels, real code only", real, current)
