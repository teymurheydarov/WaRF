"""Alternatives to the within-label bootstrap: (1) old corpus, resampling FILES (several sessions
review the same file); (2) the 100 commits, resampling the 50 size-matched pairs."""
import collections
import random
import sys
from pathlib import PurePath

sys.path.insert(0, "C:/workdir/warf/WaRF")
sys.path.insert(0, "C:/workdir/warf/WaRF/tools")
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                      # noqa: E402
from _groundtruth import file_key                        # noqa: E402

rows = V.load(f"{V.ROOT}/.warf/sessions.jsonl")
lab = [r for r in rows if isinstance(r.get("oracle"), dict) and r["oracle"].get("x_star") in (1, -1)]


def clus(r, mode):
    a = r["artifact"]
    k = file_key(a)
    if k is None:                       # "<rev>:<path>" commit artifacts
        path = a.split(":", 1)[1] if mode == "path" else a
        return "commit:" + path.replace("\\", "/").lower()
    return k


t = [r["oracle"]["x_star"] for r in lab]
d = [V.xv(r["decision"]) for r in lab]
f = [r["votes"][0]["vote"] for r in lab]
key = [(V.BAND_RANK[r["confidence"]], round(abs(r["debate"]["sprt_lambda"] if "debate" in r else r["sprt_lambda"]), 6)) for r in lab]
cw = [1 if a == b else 0 for a, b in zip(d, t)]
cf = [1 if a == b else 0 for a, b in zip(f, t)]
for mode in ("artifact", "path"):
    cl = [clus(r, mode) for r in lab]
    groups = collections.defaultdict(list)
    for i, c in enumerate(cl):
        groups[c].append(i)
    G = list(groups.values())
    sizes = collections.Counter(len(g) for g in G)
    rng = random.Random(21)
    d1, d2 = [], []
    for _ in range(2000):
        idx = [i for _ in G for i in rng.choice(G)]
        c1 = [cw[i] for i in idx]
        a1 = V.aurc(V.curve(c1, [key[i] for i in idx]))
        d1.append(a1 - (1 - sum(c1) / len(c1)))
        d2.append(a1 - (1 - sum(cf[i] for i in idx) / len(idx)))
    a = V.aurc(V.curve(cw, key))
    print(f"old corpus, clusters by {mode}: {len(G)} clusters (sizes {dict(sorted(sizes.items()))});"
          f" band - WaRF random {a - (1 - sum(cw) / 62):+.3f} [{V.ci(d1)[0]:+.3f}, {V.ci(d1)[1]:+.3f}] p {V.boot_p(d1):.3f};"
          f" band - first random [{V.ci(d2)[0]:+.3f}, {V.ci(d2)[1]:+.3f}] p {V.boot_p(d2):.3f}")

# 100 commits: resample the 50 matched pairs (rows 2k, 2k+1)
from systems100 import S, sel, truth                     # noqa: E402
assert all(sel[2 * k]["label"] == "REJECT" and sel[2 * k + 1]["label"] == "APPROVE" for k in range(50))
rng = random.Random(31)
pairs_idx = []
for _ in range(2000):
    ks = [rng.randrange(50) for _ in range(50)]
    pairs_idx.append([i for k in ks for i in (2 * k, 2 * k + 1)])
for X, Y in (("jev5_R1_band", "jev_single"), ("jevdef_R1_band", "jev_single"), ("jev5_fin_band", "jev_single"),
             ("jev5_R1_band", "jev5_seat_SKEPTIC"), ("laya5_R1_band", "laya_single")):
    da, dt = [], []
    for idx in pairs_idx:
        cx = [S[X]["correct"][i] for i in idx]; kx = [S[X]["c"][i] for i in idx]
        cy = [S[Y]["correct"][i] for i in idx]; ky = [S[Y]["c"][i] for i in idx]
        da.append(V.aurc(V.curve(cx, kx)) - V.aurc(V.curve(cy, ky)))
        dt.append(V.trust_auroc(cx, kx) - V.trust_auroc(cy, ky))
    full = list(range(100))
    oa = V.aurc(V.curve(S[X]["correct"], S[X]["c"])) - V.aurc(V.curve(S[Y]["correct"], S[Y]["c"]))
    ot = V.trust_auroc(S[X]["correct"], S[X]["c"]) - V.trust_auroc(S[Y]["correct"], S[Y]["c"])
    print(f"pair bootstrap {X} - {Y}: AURC {oa:+.3f} [{V.ci(da)[0]:+.3f}, {V.ci(da)[1]:+.3f}] p {V.boot_p(da):.3f};"
          f" trust {ot:+.3f} [{V.ci(dt)[0]:+.3f}, {V.ci(dt)[1]:+.3f}] p {V.boot_p(dt):.3f}")
