"""Part 3: WaRF's routing (finding c). 'shadow': every seat votes and learns, the heaviest
seat's vote decides; 'only': only the heaviest seat is asked and updated (--max-agents 1).

    PYTHONIOENCODING=utf-8 python -B part3_routing.py"""
import random
import statistics
from itertools import permutations
from pathlib import Path

from vm_common import Y, DOM, N, P, SEATS, ba, stream, by_row, load_dates, platt_oof, sign_p, discordant, Tee

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part3_routing.log")
ORDERS = list(permutations(SEATS))
dates, _ = load_dates()
date_order = sorted(range(N), key=lambda t: (dates[t], t))


def votes_of(rej):
    return [{s: (-1 if rej[s][t] else 1) for s in SEATS} for t in range(N)]


REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
CALP = {s: platt_oof(P[s])[0] for s in SEATS}
RC = {s: [q > 0.5 for q in CALP[s]] for s in SEATS}


def settle(res, who):
    """Reviews after which `who` is the heaviest seat for good (two readings):
    by_review: leader of each review (in that review's domain); n = index after the last review
    whose leader was not `who` (0 if it led throughout, None if it is not the last leader).
    logic: the same, counting only LOGIC reviews' leaders but reporting the position in the stream."""
    out = {}
    for name, rows in (("by_review", res), ("logic", [r for r in res if DOM[r["t"]] == "LOGIC"])):
        if rows[-1]["leader"] != who:
            out[name] = None
            continue
        k = 0
        for j, r in enumerate(rows):
            if r["leader"] != who:
                k = j + 1
        # translate to the position in the full stream
        out[name] = 0 if k == 0 else res.index(rows[k - 1]) + 1
    return out


def run(order, prof, route, votes):
    res, W = stream(order, votes, prof_order=prof, route=route)
    dec = [r["dec"] == "REJECT" for r in by_row(res)]
    fin = {s: W[s]["LOGIC"][0] / sum(W[s]["LOGIC"]) for s in prof}
    final_leader = sorted(prof, key=lambda s: fin[s], reverse=True)[0]
    shares = {s: sum(r["leader"] == s for r in res) / N for s in prof}
    return res, dec, final_leader, shares


log("== (c) routing")
a, b = discordant(REJ["JEV"], REJ["CLAUDE"], Y)
log(f"  votes right only Jev / only Claude: {a}/{b}, sign p {sign_p(a, b):.2f}")

for tag, rej, best in (("raw votes", REJ, "JEV"), ("calibrated votes", RC, "CLAUDE")):
    votes = votes_of(rej)
    log(f"\n  [{tag}] single-seat vote BA: " + ", ".join(f"{s} {ba(rej[s], Y):.3f}" for s in SEATS))
    log("   commit-date order, route 'shadow' (all seats vote and learn), per profile order:")
    for o in ORDERS:
        res, dec, fl, sh = run(date_order, o, "shadow", votes)
        st = settle(res, best)
        log(f"     {','.join(o):<20} BA {ba(dec, Y):.3f}; final leader {fl}; {best} leads for good after "
            f"{st['by_review']} reviews (LOGIC-only reading {st['logic']}); shares "
            + ", ".join(f"{s} {sh[s]:.2f}" for s in SEATS))
    rng = random.Random(17)
    for route in ("shadow", "only"):
        bas, fls, sts, stl, shs = [], [], [], [], {s: [] for s in SEATS}
        for _ in range(200):
            order = list(range(N))
            rng.shuffle(order)
            for o in ORDERS:
                res, dec, fl, sh = run(order, o, route, votes)
                bas.append(ba(dec, Y))
                fls.append(fl)
                st = settle(res, best)
                if st["by_review"] is not None:
                    sts.append(st["by_review"])
                if st["logic"] is not None:
                    stl.append(st["logic"])
                for s in SEATS:
                    shs[s].append(sh[s])
        bas.sort()
        n = len(bas)
        q = lambda xs: (statistics.median(xs), statistics.quantiles(xs, n=4)[0], statistics.quantiles(xs, n=4)[2]) if xs else None  # noqa: E731
        log(f"   1200 random orders, route '{route}': BA mean {sum(bas) / n:.3f} [{bas[int(0.025 * n)]:.3f}, "
            f"{bas[int(0.975 * n) - 1]:.3f}]; final leader " + ", ".join(f"{s} {fls.count(s) / n:.0%}" for s in SEATS)
            + f"; {best} leads for good after median/quartiles {q(sts)} (LOGIC-only {q(stl)}; "
            f"runs where it ends as leader {len(sts)}/{n}); routed shares "
            + ", ".join(f"{s} {sum(shs[s]) / n:.2f}" for s in SEATS))

# posterior probability that Jev's vote accuracy is highest (final LOGIC Betas, all seats learn)
res, W = stream(date_order, votes_of(REJ), route="shadow")
rng = random.Random(5)
for dom in ("LOGIC",):
    wins = {s: 0 for s in SEATS}
    M = 200000
    for _ in range(M):
        draw = {s: rng.betavariate(*W[s][dom]) for s in SEATS}
        wins[max(draw, key=draw.get)] += 1
    log(f"\n  posterior P(highest vote accuracy), final {dom} Betas "
        + ", ".join(f"{s} Beta({W[s][dom][0]:.0f},{W[s][dom][1]:.0f})" for s in SEATS) + ": "
        + ", ".join(f"{s} {wins[s] / M:.3f}" for s in SEATS))
# pooled over domains (one Beta per seat from all 100 labels)
wins = {s: 0 for s in SEATS}
pooled = {s: [1 + sum(1 for t in range(N) if (REJ[s][t] == Y[t])), 1 + sum(1 for t in range(N) if REJ[s][t] != Y[t])]
          for s in SEATS}
for _ in range(M):
    draw = {s: rng.betavariate(*pooled[s]) for s in SEATS}
    wins[max(draw, key=draw.get)] += 1
log("  pooled over domains: " + ", ".join(f"{s} Beta({pooled[s][0]},{pooled[s][1]}) {wins[s] / M:.3f}" for s in SEATS))
