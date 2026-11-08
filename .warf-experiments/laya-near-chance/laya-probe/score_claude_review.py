"""Score the blinded reference review against the git-history key, next to Laya and size."""
import json, math, random, sys
from pathlib import Path

BASE = Path(__file__).parent.parent / "claude-review"
key = {k["id"]: k for k in json.loads((BASE / "key.json").read_text(encoding="utf-8"))}
result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
reviews = result["reviews"] if "reviews" in result else result

answers, dup, unknown = {}, 0, []
for batch in reviews:
    for it in batch.get("items") or []:
        if it["id"] not in key:
            unknown.append(it["id"])
        elif it["id"] in answers:
            dup += 1
        else:
            answers[it["id"]] = it
print(f"answers {len(answers)} of {len(key)}; duplicates {dup}; unknown ids {len(unknown)} {unknown[:5]}")
for b in sorted({k["batch"] for k in key.values()}):
    ids = [i for i, k in key.items() if k["batch"] == b]
    print(f"  batch {b:02d}: {sum(i in answers for i in ids)}/{len(ids)} answered")

rows = [(answers[i]["p_defect"], k["p_laya"], k["patch_chars"], k["label"] == "REJECT", k["batch"], i)
        for i, k in key.items() if i in answers]


def auc(score, pos):
    P = [s for s, y in zip(score, pos) if y]
    N = [s for s, y in zip(score, pos) if not y]
    a = sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt((a * (1 - a) + (len(P) - 1) * (q1 - a * a) + (len(N) - 1) * (q2 - a * a)) / (len(P) * len(N)))
    return a, se


def boot(score, pos, n=2000, seed=5):
    rng = random.Random(seed)
    idx = list(range(len(score)))
    vals = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        ys = [pos[j] for j in s]
        if 0 < sum(ys) < len(ys):
            vals.append(auc([score[j] for j in s], ys)[0])
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


claude = [r[0] for r in rows]; laya = [r[1] for r in rows]; size = [r[2] for r in rows]; y = [r[3] for r in rows]
print(f"\n  {len(rows)} items, {sum(y)} later fixed")
for name, sc in (("Claude p(defect)", claude), ("Laya p(REJECT)", laya), ("patch size", size)):
    a, se = auc(sc, y)
    lo, hi = boot(sc, y)
    print(f"  {name:<18} AUC {a:.3f} ± {se:.3f}   95% bootstrap {lo:.3f}-{hi:.3f}")
diffs = []
rng = random.Random(9)
idx = list(range(len(rows)))
for _ in range(2000):
    s = [rng.choice(idx) for _ in idx]
    ys = [y[j] for j in s]
    if 0 < sum(ys) < len(ys):
        diffs.append(auc([claude[j] for j in s], ys)[0] - auc([laya[j] for j in s], ys)[0])
diffs.sort()
print(f"  Claude minus Laya: 95% bootstrap {diffs[int(0.025 * len(diffs))]:+.3f} to {diffs[int(0.975 * len(diffs))]:+.3f}")
print(f"  Claude's p(defect): mean {sum(claude) / len(claude):.3f}; on later-fixed "
      f"{sum(c for c, t in zip(claude, y) if t) / sum(y):.3f}, on never-fixed {sum(c for c, t in zip(claude, y) if not t) / (len(y) - sum(y)):.3f}; "
      f"distinct values {len(set(claude))}")
for b in sorted({r[4] for r in rows}):
    rs = [r for r in rows if r[4] == b]
    if 0 < sum(r[3] for r in rs) < len(rs):
        print(f"  batch {b:02d}: Claude {auc([r[0] for r in rs], [r[3] for r in rs])[0]:.3f}  Laya {auc([r[1] for r in rs], [r[3] for r in rs])[0]:.3f}")
# the items Claude is most and least worried about, with their labels
top = sorted(rows, key=lambda r: -r[0])
print("\n  Claude's 12 most suspicious items:")
for r in top[:12]:
    print(f"    p {r[0]:.2f}  label {'fixed later' if r[3] else 'never fixed'}  {key[r[5]]['file']}  - {answers[r[5]]['reason']}")
print(f"  later fixed among Claude's top quarter: {sum(r[3] for r in top[:len(top) // 4])}/{len(top) // 4}, "
      f"bottom quarter: {sum(r[3] for r in top[-(len(top) // 4):])}/{len(top) // 4}")
