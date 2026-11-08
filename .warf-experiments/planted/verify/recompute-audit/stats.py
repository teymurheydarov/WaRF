"""(4) exact McNemar on the discordant items, a base-level sign-flip test, and power for a +0.03 gain."""
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
mine = {r["id"]: r for r in map(json.loads, (HERE / "mine.jsonl").open(encoding="utf-8"))}
claude = {}
for p in sorted(EXP.glob("claude.w*.jsonl")):
    for l in p.open(encoding="utf-8"):
        r = json.loads(l)
        claude[r["planted"]["id"]] = r["decision"] == "REJECT"
jev, laya = {}, {}
for name, d in (("jev", jev), ("laya", laya)):
    for l in (EXP / f"{name}.w0.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        d[r["planted"]["id"]] = r["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"]
defect = {i: i.endswith(":planted") for i in mine}


def binom_cdf(k, n, p=0.5):
    return sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k + 1))


def mcnemar(b, c):
    n = b + c
    k = min(b, c)
    p2 = min(1.0, 2 * binom_cdf(k, n))
    mid = min(1.0, 2 * (binom_cdf(k, n) - 0.5 * math.comb(n, k) * 0.5 ** n))
    return p2, mid


print("== discordant items ==")
for mode in ("cal", "cold"):
    rows = []
    for i in mine:
        pr = mine[i][mode]["decision"] == "REJECT"
        if (pr == defect[i]) != (claude[i] == defect[i]):
            rows.append((i, "panel" if pr == defect[i] else "claude", mine[i][mode]["confidence"],
                         round(mine[i][mode]["lambda"], 3), round(jev[i], 2), round(laya[i], 2)))
    b = sum(r[1] == "panel" for r in rows)
    c = sum(r[1] == "claude" for r in rows)
    p2, mid = mcnemar(b, c)
    print(f"  {mode}: only panel {b}, only Claude {c}: exact McNemar two-sided p = {p2:.4f}, mid-p = {mid:.4f}")
    for r in rows:
        print("    ", r)
    # base level: d_b = sum over the two items of (panel right - claude right); exact sign-flip test
    d = {}
    for i in mine:
        pr = mine[i][mode]["decision"] == "REJECT"
        d.setdefault(i.rsplit(":", 1)[0], 0)
        d[i.rsplit(":", 1)[0]] += (pr == defect[i]) - (claude[i] == defect[i])
    nz = [v for v in d.values() if v]
    obs = sum(nz)
    hits = tot = 0
    for signs in itertools.product((1, -1), repeat=len(nz)):
        tot += 1
        hits += abs(sum(s * v for s, v in zip(signs, nz))) >= abs(obs)
    print(f"  {mode}: base-level differences (non-zero) {sorted(nz)}; sign-flip two-sided p = {hits / tot:.4f}")


def power_mcnemar(n_items, delta, psi, alpha=0.05):
    """P(exact two-sided McNemar rejects) when each item is panel-only w.p. (psi+delta)/2 and
    Claude-only w.p. (psi-delta)/2, independently; D ~ Bin(n, psi), X | D ~ Bin(D, q)."""
    q = (psi + delta) / (2 * psi)
    pw = 0.0
    for D in range(n_items + 1):
        pD = math.comb(n_items, D) * psi ** D * (1 - psi) ** (n_items - D)
        if pD < 1e-15:
            continue
        # rejection region of the exact test at this D
        rej = [x for x in range(D + 1) if min(1.0, 2 * binom_cdf(min(x, D - x), D)) <= alpha]
        pw += pD * sum(math.comb(D, x) * q ** x * (1 - q) ** (D - x) for x in rej)
    return pw


print("\n== power, exact McNemar at alpha 0.05, BA gain +0.03 (= net +0.03 per item, 2 items per base) ==")
for psi in (7 / 108, 0.10, 0.15):
    print(f"  discordance {psi:.3f}: 54 bases {power_mcnemar(108, 0.03, psi):.3f}; "
          f"200 bases {power_mcnemar(400, 0.03, psi):.3f}; 500 bases {power_mcnemar(1000, 0.03, psi):.3f}")
for psi in (7 / 108,):
    for nb in (100, 150, 200, 250, 300, 350, 400, 500):
        print(f"    psi {psi:.3f}, {nb} bases: power {power_mcnemar(2 * nb, 0.03, psi):.3f}")

print("\n== Jev / Laya p(REJECT) by class ==")
for name, d in (("jev", jev), ("laya", laya)):
    for cls in (True, False):
        xs = sorted(d[i] for i in d if defect[i] == cls)
        print(f"  {name} {'planted' if cls else 'clean'}: min {xs[0]}, median {xs[len(xs)//2]}, max {xs[-1]}, "
              f"share >= 0.99: {sum(x >= 0.99 for x in xs)}/{len(xs)}")
