"""A size seat for LO (README.md): offline, from stored answers, with WaRF's own functions.

    python size_seat.py        # writes size_seat.log, size_seat.json"""
import json
import math
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent))
from warf.calibration import Calibrator, approve_logodds, p_reject_from_text  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402
from warf.engine import logodds_boundary, logodds_decision, logodds_tau, pool_evidence  # noqa: E402
from warf.orchestrator import _group_key  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import DEFAULT_PERSONA  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def items_of(path):
    return {json.loads(l)["id"]: json.loads(l) for l in Path(path).open(encoding="utf-8")}


GS = {**items_of(EXP / "real-set" / "items.jsonl"), **items_of(EXP / "confirm-set" / "items.jsonl")}
MF = items_of(EXP / "mfem-set" / "items.jsonl")
ITEMS = {**GS, **MF}
assert len(ITEMS) == len(GS) + len(MF), "item ids overlap"
Y = {i: (-1 if it["kind"] == "defective" else 1) for i, it in ITEMS.items()}   # x_star: REJECT -1, APPROVE +1


def added(code):
    return sum(1 for ln in code.split(_SEPARATOR, 1)[0].splitlines() if ln.startswith("+") and not ln.startswith("+++"))


ADDED = {i: added(it["code"]) for i, it in ITEMS.items()}
SIZE_TEXT = "added-line count of the file's diff"


def seat(name, persona, provider, model, p, readout=True):
    p = min(0.99, max(0.01, round(p, 2) if readout else p))   # a text readout has two decimals
    return {"agent": name, "persona": persona_hash(persona), "persona_text": persona, "provider": provider,
            "model": model, "evidence_source": "", "vote": -1 if p >= 0.5 else 1, "p_reject": p}


TEXT = {p.persona_hash: p.persona for p in default_profiles()}
PERS = {}
for path in (EXP / "confirm-set" / "jev-learned" / "dev_sessions.jsonl",
             EXP / "confirm-set" / "jev-learned" / "sessions_LO.jsonl", EXP / "mfem-set" / "sessions_LO.jsonl"):
    for l in path.open(encoding="utf-8"):
        r = json.loads(l)
        PERS[r["artifact"]] = [seat(v["agent"], TEXT[v["persona"]], "jev", v["model"], p_reject_from_text(v["reasoning"]))
                               for v in r["votes"]]

V1 = {}
for path in (EXP / "real-set" / "jev-narrow" / "answers.jsonl", EXP / "confirm-set" / "jev-narrow" / "answers.jsonl",
             EXP / "mfem-set" / "answers_narrow.jsonl"):
    for l in path.open(encoding="utf-8"):
        r = json.loads(l)
        if r["state"] == "whole" and "jev-1.14" in r["model"]:
            V1[r["id"]] = [seat("JEV", DEFAULT_PERSONA, "jev", "jev-1.14", (r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0))]
SIZE = {i: [seat("SIZE", SIZE_TEXT, "size", "", 1 / (1 + math.exp(-(math.log1p(ADDED[i]) - 3))), readout=False)]
        for i in ITEMS}
assert set(PERS) == set(ITEMS) == set(V1), "seats missing"


# --- WaRF's log-odds decision on stored answers (as ../lo-dev/lo_offline.py) -----------------------
def profile_of(s):
    return AgentProfile(name=s["agent"], persona=s["persona_text"], persona_hash=s["persona"],
                        provider=s["provider"], model=s["model"], evidence=None)


def calibrator(train_ids, config):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for i in train_ids:
            votes = [{k: v for k, v in s.items() if k != "persona_text"} for s in config(i)]
            f.write(json.dumps({"oracle": {"type": "DEVELOPER", "x_star": Y[i]}, "votes": votes}) + "\n")
        name = f.name
    cal = Calibrator(Path(name))
    Path(name).unlink()
    return cal


def decide(seats, domain, cal):
    order, by = [], {}
    for s in seats:
        g = _group_key(s["provider"], s["model"], None)
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(s)
    items = []
    for g in order:
        for s in by[g]:
            e, _ = cal.evidence(profile_of(s), s["vote"], s["p_reject"], 0.5, s["provider"], s["model"])
            items.append((g, e))
        lam, means = pool_evidence(items)
        b = logodds_boundary(lam, means)
        if b is not None:
            return b.value
    lam, means = pool_evidence(items)
    return logodds_decision(lam, means, domain)[0].value


def warf_arm(config):
    def run(train, test):
        cal = calibrator(train, config)
        return {i: decide(config(i), ITEMS[i]["domain"], cal) for i in test}
    return run


# --- JOINT: one logistic regression on both versions' mean seat input and the size ----------------
def features(i):
    r14 = [approve_logodds(s["p_reject"]) for s in PERS[i] if s["model"] == "jev-1.14"]
    r13 = [approve_logodds(s["p_reject"]) for s in PERS[i] if s["model"] == "jev-1.13"]
    return [1.0, sum(r14) / len(r14), sum(r13) / len(r13), -(math.log1p(ADDED[i]) - 3)]


def fit_logistic(X, y, prior_sd=1.0, iters=50):
    """MAP logistic regression of clean (+1) on X, every coefficient ~ N(0, prior_sd^2); Newton."""
    k = len(X[0]); w = [0.0] * k
    for _ in range(iters):
        g = [-wj / prior_sd ** 2 for wj in w]
        H = [[(1 / prior_sd ** 2 if a == b else 0.0) for b in range(k)] for a in range(k)]
        for x, t in zip(X, y):
            z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            for a in range(k):
                g[a] += ((1.0 if t == 1 else 0.0) - p) * x[a]
                for b in range(k):
                    H[a][b] += p * (1 - p) * x[a] * x[b]
        step = solve(H, g)
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    return w


def solve(H, g):
    n = len(g); M = [row[:] + [g[r]] for r, row in enumerate(H)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [M[r][n] / M[r][r] for r in range(n)]


def joint(train, test):
    w = fit_logistic([features(i) for i in train], [Y[i] for i in train])
    n_clean = sum(Y[i] == 1 for i in train)
    prior = math.log((n_clean + 1) / (len(train) - n_clean + 1))
    lam = {i: sum(a * b for a, b in zip(w, features(i))) - prior for i in test}
    return {i: "APPROVE" if lam[i] >= logodds_tau(ITEMS[i]["domain"]) else "REJECT" for i in test}


ARMS = {"V1, one Jev seat": warf_arm(lambda i: V1[i]),
        "SIZE, the size seat alone": warf_arm(lambda i: SIZE[i]),
        "LO, five persona seats": warf_arm(lambda i: PERS[i]),
        "LO+SIZE, size as a third group": warf_arm(lambda i: PERS[i] + SIZE[i]),
        "JOINT, seats and size fitted together": joint}


def ba(pred, ids):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    return (sum(pred[i] == "REJECT" for i in pos) / len(pos) + sum(pred[i] == "APPROVE" for i in neg) / len(neg)) / 2


def mcnemar(a, b, ids):
    right = lambda p, i: (p[i] == "REJECT") == (Y[i] == -1)
    k1 = sum(right(a, i) and not right(b, i) for i in ids); k2 = sum(right(b, i) and not right(a, i) for i in ids)
    n = k1 + k2
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k1, k2) + 1)) / 2 ** n)
    return k1, k2, p


def cv(ids, reps=5, folds=10):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    res = {k: [] for k in ARMS}
    for rep in range(reps):
        rng = random.Random(100 + rep)
        P, Q = pos[:], neg[:]; rng.shuffle(P); rng.shuffle(Q)
        F = [P[k::folds] + Q[k::folds] for k in range(folds)]
        pred = {k: {} for k in ARMS}
        for k in range(folds):
            test = F[k]; train = [i for f in F[:k] + F[k + 1:] for i in f]
            for name, arm in ARMS.items():
                pred[name].update(arm(train, test))
        for name in ARMS:
            res[name].append(ba(pred[name], ids))
    return {k: sum(v) / len(v) for k, v in res.items()}, res


# --- 0. reproduction: LO calibrated on the 132 dev items must give WaRF's logged MFEM decisions -----
dev = list(items_of(EXP / "real-set" / "items.jsonl"))
logged = {json.loads(l)["artifact"]: json.loads(l)["decision"] for l in (EXP / "mfem-set" / "sessions_LO.jsonl").open(encoding="utf-8")}
mine = ARMS["LO, five persona seats"](dev, list(MF))
same = sum(mine[i] == logged[i] for i in MF)
say(f"reproduction: LO calibrated on the 132 G+Smo dev items gives {same}/300 of WaRF's logged MFEM decisions; BA {100 * ba(mine, list(MF)):.1f}%")
if same != 300:
    raise SystemExit("the offline rebuild does not match WaRF; stop")

res = {}
gs = list(GS); mf = list(MF)
say(f"\n1. G+Smo, 10-fold x 5 cross-validation over {len(gs)} items (balanced accuracy)")
m, r = cv(gs)
for k in ARMS:
    say(f"  {k:<40} {100 * m[k]:5.1f}%   (repeats {100 * min(r[k]):.1f}-{100 * max(r[k]):.1f})")
res["gsmo_cv"] = m
cand = max(("LO+SIZE, size as a third group", "JOINT, seats and size fitted together"), key=lambda k: m[k])
say(f"  candidate (the better size arm on G+Smo): {cand}")

say(f"\n2. MFEM, one look: calibrated on all {len(gs)} G+Smo items, deciding the {len(mf)} MFEM items")
pred = {k: arm(gs, mf) for k, arm in ARMS.items()}
for k in ARMS:
    pk = pred[k]
    say(f"  {k:<40} {100 * ba(pk, mf):5.1f}%   caught {sum(pk[i] == 'REJECT' for i in mf if Y[i] == -1)}/150"
        f"  false alarms {sum(pk[i] == 'REJECT' for i in mf if Y[i] == 1)}/150")
res["mfem"] = {k: ba(pred[k], mf) for k in ARMS}
for other in ("LO, five persona seats", "SIZE, the size seat alone"):
    k1, k2, p = mcnemar(pred[cand], pred[other], mf)
    say(f"  {cand.split(',')[0]} vs {other.split(',')[0]}: {100 * (ba(pred[cand], mf) - ba(pred[other], mf)):+.1f} points;"
        f" only {cand.split(',')[0]} right {k1}, only {other.split(',')[0]} right {k2}; exact McNemar p {p:.4f}")
    res[f"{cand.split(',')[0]} vs {other.split(',')[0]}"] = {"k1": k1, "k2": k2, "p": p}
k1, k2, p = mcnemar(pred[cand], pred["LO, five persona seats"], mf)
d_lo = ba(pred[cand], mf) - ba(pred["LO, five persona seats"], mf)
d_sz = ba(pred[cand], mf) - ba(pred["SIZE, the size seat alone"], mf)
verdict = ("RAISES ACCURACY" if d_lo > 0 and p < 0.05 and d_sz > 0 else "not shown" if d_lo > 0 else "no gain")
say(f"  verdict (README rule): {verdict}")
res["verdict"] = verdict

say(f"\n3. for information: 10-fold x 5 cross-validation within MFEM ({len(mf)} items)")
m, r = cv(mf)
for k in ARMS:
    say(f"  {k:<40} {100 * m[k]:5.1f}%   (repeats {100 * min(r[k]):.1f}-{100 * max(r[k]):.1f})")
res["mfem_cv"] = m
(HERE / "size_seat.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "size_seat.json").write_text(json.dumps(res, indent=1))
