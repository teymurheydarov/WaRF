import sys, math, random
sys.path.insert(0, "C:/workdir/warf/WaRF")
from warf.calibration import fit_platt
from warf.engine import A, B
# Worthless decision agent: r independent of label. How large is fitted evidence at its own extreme readouts?
for nc, nd, sd in [(10,10,2.5),(10,10,1.0),(30,10,2.5),(50,50,2.5)]:
    ext, cross, b_hat = [], 0, []
    R = 2000
    for rep in range(R):
        rr = random.Random(rep)
        rs = [max(-4.595, min(4.595, round(rr.gauss(1.0, sd), 2))) for _ in range(nc+nd)]
        ys = [1]*nc + [-1]*nd; rr.shuffle(ys)
        f = fit_platt(rs, ys)
        e = max(abs(f.evidence(4.595)), abs(f.evidence(-4.595)))
        ext.append(e); b_hat.append(f.b)
        # probability a fresh test readout from the same r distribution yields single-seat crossing
        rt = max(-4.595, min(4.595, round(rr.gauss(1.0, sd), 2)))
        et = f.evidence(rt)
        if et >= A or et <= B: cross += 1
    ext.sort(); b_hat.sort()
    print(f"clean {nc} def {nd} sd(r) {sd}: |e| at r=+-4.6 median {ext[R//2]:.2f} p90 {ext[int(.9*R)]:.2f}; "
          f"b median {b_hat[R//2]:.2f} p90 {b_hat[int(.9*R)]:.2f}; P(single fresh seat crosses A/B) {cross/R:.3f}")
