"""Part 0: recompute the reported AUCs. Part 1: Jev's sampling noise (three full runs)."""
import random
from load import S, y, ids, one, runA, runB, rep, pair
from vstats import auc, hanley_se, delong_single, delong_paired, corr, spearman, binom_two_sided, mean

print("== Part 0: reported AUCs, recomputed (Hanley SE / DeLong SE)")
for k in ("jev0", "five_r1", "five_final", "laya1", "laya5_r1", "laya5_final", "claude", "patch_chars"):
    a = auc(S[k], y)
    print(f"  {k:<12} {a:.3f}  Hanley ±{hanley_se(a, 50, 50):.3f}  DeLong ±{delong_single(S[k], y)[1]:.3f}")

print("\n== Part 1: three full runs of the one-question JEV agent")
models = {m for rs in (one, runA, runB) for r in rs.values() for m in r["jev"]["models"]}
print(f"  models reported: {sorted(models)}")
print(f"  run dates: original {one[ids[0]]['created_at'][:19]}, A {runA[ids[0]]['jev']['at'][:19]}, B {runB[ids[0]]['jev']['at'][:19]}")
for k in ("jev0", "jevA", "jevB", "jev3"):
    a, se = delong_single(S[k], y)
    z = (a - 0.5) / se
    from vstats import norm_sf
    won = sum((S[k][2 * j] > S[k][2 * j + 1]) + 0.5 * (S[k][2 * j] == S[k][2 * j + 1]) for j in range(50))
    print(f"  {k:<6} AUC {a:.3f} ± {se:.3f}  (z {z:.2f}, one-sided p {norm_sf(z):.4f}); pairs won {won:.1f}/50; "
          f"distinct p {len(set(S[k]))}; REJECT choices {sum(v > 0.5 for v in S[k])}")
for a_, b_ in (("jev0", "jevA"), ("jev0", "jevB"), ("jevA", "jevB")):
    d = [abs(u - v) for u, v in zip(S[a_], S[b_])]
    print(f"  {a_} vs {b_}: Pearson {corr(S[a_], S[b_]):.3f}, Spearman {spearman(S[a_], S[b_]):.3f}, "
          f"identical {sum(u == v for u, v in zip(S[a_], S[b_]))}/100, mean |diff| {mean(d):.4f}, max {max(d):.3f}, "
          f"choice flips {sum((u > 0.5) != (v > 0.5) for u, v in zip(S[a_], S[b_]))}")
    dd = delong_paired(S[a_], S[b_], y)
    print(f"      AUC difference {dd[0]:+.4f} ± {dd[1]:.4f}")
# Per-commit spread across the three runs
sd = [((u - (u + v + w) / 3) ** 2 + (v - (u + v + w) / 3) ** 2 + (w - (u + v + w) / 3) ** 2) / 2
      for u, v, w in zip(S["jev0"], S["jevA"], S["jevB"])]
print(f"  within-commit SD of p across runs: mean {mean([x ** 0.5 for x in sd]):.4f}; between-commit SD of the mean "
      f"{(sum((m - mean(S['jev3'])) ** 2 for m in S['jev3']) / 99) ** 0.5:.4f}")
# Distribution of the single-run AUC: pick one of the three answers per commit at random
rng = random.Random(11)
draws = []
runs = [S["jev0"], S["jevA"], S["jevB"]]
for _ in range(2000):
    s = [runs[rng.randrange(3)][i] for i in range(100)]
    draws.append(auc(s, y))
draws.sort()
print(f"  AUC of a random single draw per commit (2000 mixes): mean {mean(draws):.3f}, SD {(sum((d - mean(draws)) ** 2 for d in draws) / 1999) ** 0.5:.4f}, "
      f"2.5-97.5 % [{draws[50]:.3f}, {draws[1949]:.3f}]")
# repeat_one: the 20 commits asked again right after the original run
r20 = [i for i in ids if i in rep]
print(f"  repeat_one ({len(r20)} commits): identical to original {sum(rep[i]['jev']['round1']['JEV']['p_reject'] == one[i]['jev']['round1']['JEV']['p_reject'] for i in r20)}, "
      f"identical to A {sum(rep[i]['jev']['round1']['JEV']['p_reject'] == runA[i]['jev']['round1']['JEV']['p_reject'] for i in r20)}")
# Fold-in of the repeat answers as a fourth draw where available
four = [(S['jev0'][k] + S['jevA'][k] + S['jevB'][k] + (rep[i]['jev']['round1']['JEV']['p_reject'] if i in rep else S['jev3'][k])) / 4 if i in rep else S['jev3'][k]
        for k, i in enumerate(ids)]
print(f"  mean of all answers (4 on the first 20): AUC {auc(four, y):.3f}")
# Within-pair (matched design) sign test and pair-level permutation p for jev0 and jev3
for k in ("jev0", "jev3"):
    s = S[k]
    wins = sum(s[2 * j] > s[2 * j + 1] for j in range(50))
    ties = sum(s[2 * j] == s[2 * j + 1] for j in range(50))
    print(f"  {k}: pairs where the later-fixed scores higher {wins}, lower {50 - wins - ties}, tied {ties}; "
          f"sign test two-sided p {binom_two_sided(wins, 50 - ties):.3f}")
    # permutation that respects the matched design: swap labels within pairs
    obs = auc(s, y)
    rng = random.Random(7)
    ge = 0
    B = 4000
    for _ in range(B):
        yy = []
        for j in range(50):
            if rng.random() < 0.5:
                yy += [True, False]
            else:
                yy += [False, True]
        if auc(s, yy) >= obs:
            ge += 1
    print(f"      within-pair label swap permutation: one-sided p {(ge + 1) / (B + 1):.4f} (AUC {obs:.3f})")
    # unrestricted shuffle
    rng = random.Random(8)
    ge = 0
    for _ in range(B):
        yy = y[:]
        rng.shuffle(yy)
        if auc(s, yy) >= obs:
            ge += 1
    print(f"      free label shuffle permutation: one-sided p {(ge + 1) / (B + 1):.4f}")
