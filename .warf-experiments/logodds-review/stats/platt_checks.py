import sys, math, random
sys.path.insert(0, "C:/workdir/warf/WaRF")
from warf.calibration import fit_platt, _log_posterior, _logit
from warf import engine as E

def ref_map(rs, ys):
    # independent: coordinate-free gradient ascent with tiny lr, long run
    a, b = 0.0, 1.0
    for it in range(200000):
        ga, gb = -a, -(b-1)
        for r, y in zip(rs, ys):
            p = 1/(1+math.exp(-(a+b*r))); t = 1 if y == 1 else 0
            ga += t-p; gb += (t-p)*r
        lr = 0.5/ (1+len(rs)*(1+max(abs(r) for r in rs))**2/4)
        a += lr*ga; b += lr*gb
        if abs(ga) < 1e-10 and abs(gb) < 1e-10: break
    return a, b

print("== degenerate: all r equal ==")
for r0 in (0.0, 2.0, 4.595):
    rs = [r0]*30; ys = [1]*20+[-1]*10
    f = fit_platt(rs, ys); ra = ref_map(rs, ys)
    print(r0, f and (round(f.a,6), round(f.b,6), round(f.evidence(r0),4)), [round(x,6) for x in ra])

print("== perfectly separated ==")
rs = [-4.6]*10 + [4.6]*10; ys = [-1]*10 + [1]*10
f = fit_platt(rs, ys); print(f and (f.a, f.b, f.evidence(4.6), f.evidence(-4.6)), ref_map(rs, ys))

print("== tiny ==")
for rs, ys in [([1.0],[1]), ([1.0,-1.0],[1,-1]), ([],[])]:
    f = fit_platt(rs, ys); print(rs, ys, f and (round(f.a,4), round(f.b,4), round(f.prior_logodds,4)))

print("== convergence failures on random data ==")
rng = random.Random(1); fails = 0; maxdiff = 0; N = 300
for t in range(N):
    n = rng.choice([20, 50, 200, 2000])
    slope = rng.uniform(-2, 3); base = rng.uniform(-2, 2)
    rs = [max(-4.595, min(4.595, round(rng.gauss(rng.uniform(-3,3), rng.uniform(0.1,3)), 2))) for _ in range(n)]
    ys = [1 if rng.random() < 1/(1+math.exp(-(base+slope*r))) else -1 for r in rs]
    f = fit_platt(rs, ys)
    if f is None: fails += 1; print("FAIL n=%d slope=%.2f" % (n, slope)); continue
    if t < 40:
        ra, rb = ref_map(rs, ys) if n <= 200 else (f.a, f.b)
        maxdiff = max(maxdiff, abs(ra-f.a), abs(rb-f.b))
print("fails", fails, "/", N, "max |diff| vs reference", maxdiff)

print("== property 4 at minimum sizes: uninformative p, imbalanced ==")
for n_clean, n_def, mu in [(40,10,2.0),(10,10,2.0),(90,10,3.0),(10,40,-1.0),(200,50,2.0)]:
    biases = []
    for rep in range(200):
        rr = random.Random(rep)
        rs = [max(-4.595, min(4.595, round(rr.gauss(mu, 1.0), 2))) for _ in range(n_clean+n_def)]
        ys = [1]*n_clean + [-1]*n_def
        f = fit_platt(rs, ys)
        if f is None: continue
        biases.append(sum(f.evidence(r) for r in rs)/len(rs))   # mean evidence on training r
    m = sum(biases)/len(biases); print(f"clean {n_clean} def {n_def} mean r {mu}: mean evidence {m:+.3f}")
