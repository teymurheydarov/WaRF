"""Critic 2: per-seat REJECT rates, single-seat balanced accuracy, seat agreement, and re-scores
with the x5-only classes. Pure Python; reads only the arm records and items.jsonl.
    python -B seats.py   (writes seats.log next to it)"""
import json, math, random, itertools
from pathlib import Path
HERE = Path(__file__).resolve().parents[2]
OUT = []
def say(s=""): OUT.append(s); print(s)
items = {it["id"]: it for it in map(json.loads, (HERE / "items.jsonl").open(encoding="utf-8"))}
recs = {}
for arm in ("claude", "claude-strict", "claude-x5", "claude-standard"):
    recs[arm] = {}
    for p in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in p.open(encoding="utf-8"):
            r = json.loads(line); recs[arm][r["planted"]["id"]] = r
bases = sorted({it["base"] for it in items.values()})
ids = [f"{b}:{k}" for b in bases for k in ("clean", "planted")]
short = lambda i: i.split(":")[0]
kind = lambda i: i.rsplit(":", 1)[1]
REAL = set("06377a8 2a29aa6 2f8cd81 38858cf 3cf80c7 5853a6f 5f9ae79 6fc3f69 8058d91 890cd00 8ca586f "
           "9b1851c af41faa c826b44 da35b0c e42bec0".split())
DEB = set("15977e9 a86cf94 d9fca63 db3aca7".split())
FALSE = set("0696ac5 6c02814 a880e56 bfbe226 c0c88af".split())
# x5-only classes from verify/x5-only (critic2 spot-checked fbcf2aa and a60880c, see report)
X5_REAL, X5_DEB, X5_FALSE = {"fbcf2aa"}, {"1050623", "cd9af47"}, {"a60880c"}

seat = {}
for arm in ("claude-x5", "claude-standard"):
    seat[arm] = {}
    for i in ids:
        for v in recs[arm][i]["votes"]:
            seat[arm].setdefault(v["agent"], {})[i] = v["vote"]
    seat[arm] = {n: seat[arm][n] for n in sorted(seat[arm], key=lambda n: [v["agent"] for v in recs[arm][ids[0]]["votes"]].index(n)
                                                  if n in [v["agent"] for v in recs[arm][ids[0]]["votes"]] else 99)}
dec = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in recs}


def ba_of(rej, defect, only=None):
    P = [i for i in ids if (kind(i) == "planted" or short(i) in defect) and (only is None or i in only)]
    N = [i for i in ids if not (kind(i) == "planted" or short(i) in defect) and (only is None or i in only)]
    return (sum(rej[i] for i in P) / len(P) + sum(not rej[i] for i in N) / len(N)) / 2


say("== 1. per-seat REJECT rate (seats asked only; seat 5 is censored by the early stop) ==")
for arm in ("claude-x5", "claude-standard"):
    for name, v in seat[arm].items():
        c = [i for i in v if kind(i) == "clean"]; p = [i for i in v if kind(i) == "planted"]
        rc = sum(v[i] == -1 for i in c)
        say(f"  {arm:<16} {name:<13} clean {rc:2d}/{len(c)} = {rc/len(c):.2f}   planted {sum(v[i] == -1 for i in p):2d}/{len(p)}")
for arm in ("claude", "claude-strict", "claude-x5", "claude-standard"):
    say(f"  {arm:<16} {'DECISION':<13} clean {sum(dec[arm][i] for i in ids if kind(i)=='clean'):2d}/50"
        f"        planted {sum(dec[arm][i] for i in ids if kind(i)=='planted'):2d}/50")

say("\n== 2. seat 5 uncensored estimate: seat 5 on the clean items where it was asked ==")
for arm in ("claude-x5", "claude-standard"):
    n5 = list(seat[arm])[4]
    asked = [f"{b}:clean" for b in bases if f"{b}:clean" in seat[arm][n5]]
    say(f"  {arm}: {n5} asked on {len(asked)} clean items (not asked = early stop at 4 REJECT)")

say("\n== 3. each seat alone as a reviewer (balanced accuracy), seats 1-4, on the items it voted ==")
labs = {"as given": set(), "real": REAL, "real+deb": REAL | DEB,
        "real*": REAL | X5_REAL, "real*+deb*": REAL | DEB | X5_REAL | X5_DEB}
say("  " + " " * 30 + "  ".join(f"{k:>10}" for k in labs))
for arm in ("claude-x5", "claude-standard"):
    for name in list(seat[arm])[:4]:
        v = seat[arm][name]; rej = {i: v.get(i) == -1 for i in ids}
        say(f"  {arm:<16} {name:<13} " + "  ".join(f"{ba_of(rej, d, set(v)):>10.3f}" for d in labs.values()))
for arm in recs:
    say(f"  {arm:<16} {'DECISION':<13} " + "  ".join(f"{ba_of(dec[arm], d):>10.3f}" for d in labs.values()))

say("\n== 4. seat agreement on clean items (pairs among seats 1-4, both voted) ==")
for arm in ("claude-x5", "claude-standard"):
    names = list(seat[arm])[:4]
    tot = agr = 0; ks = []
    for a, b in itertools.combinations(names, 2):
        c = [f"{x}:clean" for x in bases if f"{x}:clean" in seat[arm][a] and f"{x}:clean" in seat[arm][b]]
        A = [seat[arm][a][i] == -1 for i in c]; B = [seat[arm][b][i] == -1 for i in c]
        n = len(c); po = sum(x == y for x, y in zip(A, B)) / n
        pa, pb = sum(A) / n, sum(B) / n; pe = pa * pb + (1 - pa) * (1 - pb)
        k = (po - pe) / (1 - pe) if pe < 1 else float("nan"); ks.append(k)
        tot += n; agr += sum(x == y for x, y in zip(A, B))
        say(f"    {a}-{b}: agree {po:.2f} kappa {k:+.2f}")
    say(f"  {arm}: pairwise agreement {agr}/{tot} = {agr/tot:.3f}, mean kappa {sum(ks)/len(ks):+.2f}")
    split = [b for b in bases if len({seat[arm][n].get(f'{b}:clean') for n in names} - {None}) > 1]
    say(f"  {arm}: clean items with seats 1-4 split: {len(split)}")


def indep_majority(rates, need=3):
    tot = 0.0
    for votes in itertools.product((0, 1), repeat=len(rates)):
        pr = 1.0
        for r, x in zip(rates, votes): pr *= r if x else 1 - r
        tot += pr * (sum(votes) >= need)
    return tot


say("\n== 5. leniency vs independence on clean items ==")
for arm in ("claude-x5", "claude-standard"):
    names = list(seat[arm])[:4]
    rates = [sum(seat[arm][n][i] == -1 for i in seat[arm][n] if kind(i) == "clean") /
             sum(kind(i) == "clean" for i in seat[arm][n]) for n in names]
    mean4 = sum(rates) / 4
    # majority of seats 1-4 (>=3 of 4 REJECT) observed vs independent
    obs = sum(sum(seat[arm][n].get(f"{b}:clean") == -1 for n in names) >= 3 for b in bases) / 50
    say(f"  {arm}: seats 1-4 clean REJECT rates {[round(r, 2) for r in rates]}, mean {mean4:.3f}")
    say(f"     >=3 of seats 1-4 REJECT: observed {obs:.3f}; if independent with these rates {indep_majority(rates, 3):.3f}")
    say(f"     arm decision clean REJECT {sum(dec[arm][f'{b}:clean'] for b in bases)/50:.3f}")

say("\n== 6. clean items: number of seats 1-4 rejecting, by item class ==")
cls = {**{s: "real" for s in REAL | X5_REAL}, **{s: "deb" for s in DEB | X5_DEB},
       **{s: "false" for s in FALSE | X5_FALSE}}
for arm in ("claude-x5", "claude-standard"):
    names = list(seat[arm])[:4]
    rows = {}
    for b in bases:
        i = f"{b}:clean"; c = cls.get(short(i), "unflagged")
        rows.setdefault(c, []).append(sum(seat[arm][n].get(i) == -1 for n in names))
    say(f"  {arm}: " + "; ".join(f"{c} n={len(v)} hist{[v.count(k) for k in range(5)]}" for c, v in sorted(rows.items())))
say("  (hist = items with 0,1,2,3,4 of seats 1-4 rejecting)")
say("  per seat, clean rejects by class (real*/deb*/false*/unflagged):")
for arm in ("claude-x5", "claude-standard"):
    for n in seat[arm]:
        v = seat[arm][n]
        say(f"    {arm:<16} {n:<13} " + ", ".join(
            f"{c} {sum(v.get(f'{b}:clean') == -1 for b in bases if cls.get(short(b), 'unflagged') == c)}"
            for c in ("real", "deb", "false", "unflagged")))
for arm in ("claude", "claude-strict"):
    say(f"    {arm:<16} {'DECISION':<13} " + ", ".join(
        f"{c} {sum(dec[arm][f'{b}:clean'] for b in bases if cls.get(short(b), 'unflagged') == c)}"
        for c in ("real", "deb", "false", "unflagged")))

say("\n== 7. re-score with the x5-only classes (fbcf2aa real; 1050623, cd9af47 debatable; a60880c false) ==")
rng = random.Random(4); boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]


def ba_b(arm, bs, defect):
    P = [f"{b}:{k}" for b in bs for k in ("clean", "planted") if k == "planted" or short(b) in defect]
    N = [f"{b}:{k}" for b in bs for k in ("clean", "planted") if not (k == "planted" or short(b) in defect)]
    return (sum(dec[arm][i] for i in P) / len(P) + sum(not dec[arm][i] for i in N) / len(N)) / 2


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


INTRO = (REAL | X5_REAL) - {"8ca586f"}
for name, d in (("real (16, as score_all)", REAL), ("real* (17)", REAL | X5_REAL),
                ("real*+deb* (23)", REAL | DEB | X5_REAL | X5_DEB),
                ("introduced only: real* minus 8ca586f (16)", INTRO)):
    say(f"  -- {name}: " + ", ".join(f"{a} {ba_b(a, bases, d):.3f}" for a in recs))
    for a1, a2 in (("claude-standard", "claude-strict"), ("claude-standard", "claude-x5"),
                   ("claude-standard", "claude"), ("claude-strict", "claude"), ("claude-x5", "claude")):
        diff = ba_b(a1, bases, d) - ba_b(a2, bases, d)
        xs = sorted(ba_b(a1, s, d) - ba_b(a2, s, d) for s in boots)
        t = lambda i: kind(i) == "planted" or short(i) in d
        k1 = sum(dec[a1][i] == t(i) and dec[a2][i] != t(i) for i in ids)
        k2 = sum(dec[a2][i] == t(i) and dec[a1][i] != t(i) for i in ids)
        say(f"     {a1} - {a2}: {diff:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}] only first {k1}, only second {k2}, "
            f"McNemar p {mcnemar(k1, k1 + k2):.3f}, share<=0 {sum(x <= 0 for x in xs) / 20:.1f}%")

say("\n== 8. who rejects each x5-only clean item (-1 = REJECT) ==")
for s in sorted(X5_REAL | X5_DEB | X5_FALSE):
    b = [x for x in bases if short(x) == s][0]; i = f"{b}:clean"
    say(f"  {s}: one {dec['claude'][i]}, strict {dec['claude-strict'][i]}, x5 {[seat['claude-x5'][n].get(i) for n in seat['claude-x5']]}, "
        f"standard {[seat['claude-standard'][n].get(i) for n in seat['claude-standard']]}")
say("\n== 9. calls ==")
for a in recs:
    say(f"  {a}: {sum(len(recs[a][i]['planted'].get('calls', [0])) for i in ids)}")
Path(__file__).with_name("seats.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
