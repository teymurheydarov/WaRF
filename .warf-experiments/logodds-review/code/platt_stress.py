import sys, random, math
sys.path.insert(0, r"C:/workdir/warf/WaRF")
from warf.calibration import fit_platt, approve_logodds
rng = random.Random(3); fails = 0; tot = 0; worst = []
for n in (20, 50, 200, 1000, 5000):
    for slope in (-2, -0.5, 0, 0.5, 1, 3, 10):
        for base in (0.1, 0.5, 0.9):
            for trial in range(3):
                rs, ys = [], []
                for _ in range(n):
                    p = min(.99, max(.01, round(rng.random(), 2)))
                    r = approve_logodds(p)
                    q = 1/(1+math.exp(-(math.log(base/(1-base)) + slope*r)))
                    rs.append(r); ys.append(1 if rng.random() < q else -1)
                tot += 1
                f = fit_platt(rs, ys)
                if f is None:
                    fails += 1; worst.append((n, slope, base))
# degenerate: all p identical
print("fails", fails, "/", tot, worst[:10])
print("all p=0.99:", fit_platt([approve_logodds(.99)]*40, [1]*20+[-1]*20))
print("all p=0.5:", fit_platt([0.0]*40, [1]*20+[-1]*20))
print("separable:", fit_platt([approve_logodds(.99)]*20+[approve_logodds(.01)]*20, [-1]*20+[1]*20))
