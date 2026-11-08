"""Part 2e: the pair-matched test of Jev beyond added lines, across ridge values; pairs where added lines tie."""
import math
from part2d_added import clogit, col, ALL11
from load import S, y, F
from vstats import chi2_sf_1
print("\n== Part 2e: ridge sensitivity of the pair-matched test")
for ridge in (0.0, 0.1, 1.0):
    for base in ([], ["log1p added"], ["log1p added", "comment-only", "deletion-only/deleted"], ALL11):
        if ridge == 0.0 and len(base) > 1:
            continue
        for extra in ("logit Jev", "logit Claude"):
            ll0 = clogit(base, ridge)[1] if base else 50 * math.log(0.5)
            b1, ll1 = clogit(base + [extra], ridge)
            lr = 2 * (ll1 - ll0)
            print(f"  ridge {ridge}: {('+'.join(base) if len(base) < 4 else '11 features') or '(nothing)':<50} + {extra:<12} LR {lr:5.2f} p {chi2_sf_1(lr):.3f} beta {b1[-1]:+.2f}")
J = S["jev0"]
ra = [F[2*k]["added"] > F[2*k+1]["added"] for k in range(50)]
eq = [F[2*k]["added"] == F[2*k+1]["added"] for k in range(50)]
print(f"  pairs where the later-fixed change adds more lines {sum(ra)}, equal {sum(eq)}, fewer {50-sum(ra)-sum(eq)}")
for name, idx in (("more added in R", [k for k in range(50) if ra[k]]), ("equal", [k for k in range(50) if eq[k]]), ("fewer added in R", [k for k in range(50) if not ra[k] and not eq[k]])):
    w = sum(J[2*k] > J[2*k+1] for k in idx)
    print(f"    {name}: {len(idx)} pairs, Jev ranks the later-fixed higher in {w}")
