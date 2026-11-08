"""Independent re-computation of mixed_panel.py's headline numbers with plain code (no review() machinery,
a pairwise AUC, and a gradient-descent Platt fit instead of Newton's method), plus two details:
how often WaRF's early stopping changes a decision in the log-odds variant, and how often its HIGH
verdicts are right. Stored data only. Writes verify_independent.log next to this file.

    PYTHONIOENCODING=utf-8 python -B .warf-experiments/why-warf/mixed/verify_independent.py
"""
import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf.engine import A, B, THETA  # noqa: E402

OUT = []


def say(s=""):
    OUT.append(s)
    print(s, flush=True)


sel = [json.loads(line) for line in (EXP / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
one = {}
for line in (EXP / "jev-five" / "sessions_one.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    one[r["jev"]["id"]] = r["jev"]["round1"]["JEV"]["p_reject"]
n = len(sel)
y = [s["label"] == "REJECT" for s in sel]
dom = [s["domain"] for s in sel]
P = {"JEV": [one[s["id"]] for s in sel], "LAYA": [s["p_single_laya"] for s in sel],
     "CLAUDE": [s["p_claude"] for s in sel]}
SEATS = tuple(P)


def auc_pairs(score):
    pos = [s for s, t in zip(score, y) if t]
    neg = [s for s, t in zip(score, y) if not t]
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def ba(rej):
    tp = sum(r and t for r, t in zip(rej, y))
    tn = sum((not r) and (not t) for r, t in zip(rej, y))
    return (tp / sum(y) + tn / (n - sum(y))) / 2


def lg(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


# votes and the majority of three (uniform weights: the synthesis of three +-1 votes)
rejv = {s: [p > 0.5 for p in P[s]] for s in SEATS}
maj = [sum(rejv[s][i] for s in SEATS) >= 2 for i in range(n)]
say(f"REJECT votes: " + ", ".join(f"{s} {sum(rejv[s])}" for s in SEATS))
say(f"majority of three: REJECT {sum(maj)}, bal.acc {ba(maj):.3f}; AUC of the REJECT-vote count "
    f"{auc_pairs([sum(rejv[s][i] for s in SEATS) for i in range(n)]):.3f}")
say(f"majority identical to CLAUDE's vote: {maj == rejv['CLAUDE']}")

# raw log-odds sum, decision against theta on the mean APPROVE log-odds
raw = [sum(lg(P[s][i]) for s in SEATS) for i in range(n)]
rej_raw = [-(raw[i] / 3) < THETA[dom[i]] for i in range(n)]
say(f"raw log-odds sum: REJECT {sum(rej_raw)}, bal.acc {ba(rej_raw):.3f}, AUC {auc_pairs(raw):.3f}")


def platt_gd(xs, ts, steps=20000, lr=0.05, a=0.0, b=0.0):
    m = len(xs)
    for _ in range(steps):
        ga = gb = 0.0
        for x, t in zip(xs, ts):
            q = 1 / (1 + math.exp(-(a + b * x)))
            ga += q - t
            gb += (q - t) * x
        a -= lr * ga / m
        b -= lr * gb / m
    return a, b


cal = {}
for s in SEATS:
    x = [lg(p) for p in P[s]]
    out = [0.0] * n
    a0, b0 = platt_gd(x, [1.0 if t else 0.0 for t in y], steps=20000, lr=0.5)
    for k in range(n // 2):
        tr = [i for i in range(n) if i // 2 != k]
        a, b = platt_gd([x[i] for i in tr], [1.0 if y[i] else 0.0 for i in tr], steps=400, lr=0.5, a=a0, b=b0)
        out[2 * k] = a + b * x[2 * k]
        out[2 * k + 1] = a + b * x[2 * k + 1]
    cal[s] = out
    rc = [z > 0 for z in out]
    say(f"{s}: calibrated (gradient descent) REJECT {sum(rc)}, bal.acc {ba(rc):.3f}")
cs = [sum(cal[s][i] for s in SEATS) for i in range(n)]
rej_cal = [-(cs[i] / 3) < THETA[dom[i]] for i in range(n)]
say(f"calibrated log-odds sum: REJECT {sum(rej_cal)}, bal.acc {ba(rej_cal):.3f}, AUC {auc_pairs(cs):.3f}")
cv = {s: [z > 0 for z in cal[s]] for s in SEATS}
majc = [sum(cv[s][i] for s in SEATS) >= 2 for i in range(n)]
say(f"majority of calibrated votes: REJECT {sum(majc)}, bal.acc {ba(majc):.3f}")

# early stopping on the log-odds Lambda (omega 0.5): plain loop with WaRF's A and B
for tag, L in (("raw", {s: [-lg(p) for p in P[s]] for s in SEATS}),
               ("calibrated", {s: [-z for z in cal[s]] for s in SEATS})):
    for order in itertools.permutations(SEATS):
        rej, high, high_right, changed = [], 0, 0, 0
        for i in range(n):
            lam, verdict, asked = 0.0, None, 0
            for s in order:
                lam += 0.5 * L[s][i]
                asked += 1
                if lam >= A:
                    verdict = False
                    break
                if lam <= B:
                    verdict = True
                    break
            if verdict is None:
                verdict = (sum(L[s][i] for s in order) / 3) < THETA[dom[i]]
                full = verdict
            else:
                high += 1
                high_right += verdict == y[i]
                full = (sum(L[s][i] for s in order) / 3) < THETA[dom[i]]
            changed += verdict != full
            rej.append(verdict)
        say(f"{tag:<10} early stopping, order {'-'.join(order):<18}: HIGH verdicts {high} ({high_right} right), "
            f"decisions changed by stopping early {changed}, bal.acc {ba(rej):.3f}")

(HERE / "verify_independent.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
