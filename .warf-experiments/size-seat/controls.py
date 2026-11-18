"""Controls for size_seat.py's JOINT (not part of the README's rule, run after its result):
JOINT without the size input (is the gain the joint fit or the size?), JOINT with the sizes shuffled
across items (must fall back to about the no-size value), and JOINT's fitted weights.

    python controls.py        # writes controls.log"""
import random
import sys
from pathlib import Path

sys.argv = [sys.argv[0]]
HERE = Path(__file__).resolve().parent
import size_seat as S  # noqa: E402  (reruns size_seat's analysis; its log is rewritten identically)

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def joint_with(feat):
    def run(train, test):
        w = S.fit_logistic([feat(i) for i in train], [S.Y[i] for i in train])
        n_clean = sum(S.Y[i] == 1 for i in train)
        prior = S.math.log((n_clean + 1) / (len(train) - n_clean + 1))
        lam = {i: sum(a * b for a, b in zip(w, feat(i))) - prior for i in test}
        return {i: "APPROVE" if lam[i] >= S.logodds_tau(S.ITEMS[i]["domain"]) else "REJECT" for i in test}
    return run


gs, mf = list(S.GS), list(S.MF)
nosize = joint_with(lambda i: S.features(i)[:3])
say("JOINT's weights, fitted on all 352 G+Smo items: [intercept, jev-1.14 mean input, jev-1.13 mean input, -(ln(1+added)-3)]")
say("  " + ", ".join(f"{w:+.3f}" for w in S.fit_logistic([S.features(i) for i in gs], [S.Y[i] for i in gs])))
say("\nMFEM one look (calibrated on G+Smo), balanced accuracy")
say(f"  JOINT                         {100 * S.ba(S.joint(gs, mf), mf):5.1f}%")
say(f"  JOINT without size            {100 * S.ba(nosize(gs, mf), mf):5.1f}%")
for seed in range(5):
    rng = random.Random(seed)
    sizes = {}
    for ids in (gs, mf):
        v = [S.ADDED[i] for i in ids]; rng.shuffle(v); sizes.update(zip(ids, v))
    shuf = joint_with(lambda i: S.features(i)[:3] + [-(S.math.log1p(sizes[i]) - 3)])
    say(f"  JOINT, sizes shuffled (seed {seed}) {100 * S.ba(shuf(gs, mf), mf):5.1f}%")
k1, k2, p = S.mcnemar(S.joint(gs, mf), nosize(gs, mf), mf)
say(f"  JOINT vs JOINT without size: only JOINT right {k1}, only without-size right {k2}; exact McNemar p {p:.4f}")
(HERE / "controls.log").write_text("\n".join(out) + "\n", encoding="utf-8")
