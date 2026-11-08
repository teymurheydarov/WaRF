"""Point estimates for every system on the 100 commits: selective accuracy at 10/25/50/75/100 %,
AURC, trust AUROC (with a one-sided label-permutation p), accuracy and the HIGH counts."""
import random
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                               # noqa: E402
from systems100 import S, P5, PS, PL, truth, sel  # noqa: E402


def perm_p_trust(correct, key, n=4000, seed=1):
    obs = V.trust_auroc(correct, key)
    rng = random.Random(seed)
    c = list(correct)
    ge = 0
    for _ in range(n):
        rng.shuffle(c)
        if V.trust_auroc(c, key) >= obs - 1e-12:
            ge += 1
    return (ge + 1) / (n + 1)


def summary(name, s, perm=True):
    cum = V.curve(s["correct"], s["c"])
    accs = [V.acc_at(cum, k) for k in (10, 25, 50, 75, 100)]
    au = V.aurc(cum)
    ta = V.trust_auroc(s["correct"], s["c"])
    acc = sum(s["correct"]) / 100
    pp = perm_p_trust(s["correct"], s["c"]) if perm else float("nan")
    return accs, au, ta, acc, pp


if __name__ == "__main__":
    print(f"{'system':<28}{'acc@10':>7}{'@25':>7}{'@50':>7}{'@75':>7}{'@100':>7}{'AURC':>8}{'gain':>8}{'trAUROC':>9}{'perm p':>8}")
    for name in S:
        accs, au, ta, acc, pp = summary(name, S[name])
        print(f"{name:<28}" + "".join(f"{a:>7.3f}" for a in accs) + f"{au:>8.3f}{(1 - acc) - au:>8.3f}{ta:>9.3f}{pp:>8.3f}")

    # HIGH counts and their hit rates
    for nm, P in (("five-Jev R1", P5["r1"]), ("five-Jev final", P5["fin"]), ("defaults", PS["r1"]),
                  ("five-Laya R1", PL["r1"]), ("five-Laya final", PL["fin"])):
        hi = [i for i, b in enumerate(P["band"]) if b == "HIGH"]
        right = sum(1 for i in hi if P["d"][i] == truth[i])
        decs = {P["d"][i] for i in hi}
        print(f"{nm:<18} HIGH {len(hi):>3}  decisions {decs}  right {right}")
