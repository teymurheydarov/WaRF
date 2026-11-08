"""Recompute the headline numbers by other means: exact pairwise AUC and a logistic
regression of the label on log patch size plus Laya's p(REJECT)."""
import json, math, sys
from pathlib import Path
import numpy as np

home = Path(sys.argv[1])
labels = {}
with (home / "labels.jsonl").open(encoding="utf-8") as f:
    for line in f:
        lab = json.loads(line)
        labels[(lab["commit"], lab["file"])] = lab["label"]
y, p, size, full, phase = [], [], [], [], []
with (home / "sessions.jsonl").open(encoding="utf-8") as f:
    for line in f:
        s = json.loads(line)
        if s.get("profile") != "laya_sweep" or "sweep" not in s:
            continue
        w = s["sweep"]
        lab = labels.get((w["commit"], w["file"]))
        if lab is None:
            continue
        y.append(lab == "REJECT"); p.append(w["laya"]["probabilities"]["REJECT"])
        size.append(w["patch_chars"]); phase.append(w["phase"])
        full.append(not (w["laya"].get("usage") or {}).get("state_tokens_dropped"))
y, p, size, full, phase = map(np.asarray, (y, p, size, full, phase))

def auc_exact(score, pos):
    """P(score of a REJECT > score of an APPROVE) + half the ties, by counting."""
    neg = np.sort(score[~pos])
    lo = np.searchsorted(neg, score[pos], "left")
    hi = np.searchsorted(neg, score[pos], "right")
    return float((lo + 0.5 * (hi - lo)).sum() / (pos.sum() * len(neg)))

def solve_small(A, v):
    """Gaussian elimination with partial pivoting (numpy's BLAS crashes in this Python)."""
    n = len(v)
    M = [list(map(float, A[i])) + [float(v[i])] for i in range(n)]
    for c in range(n):
        r = max(range(c, n), key=lambda k: abs(M[k][c]))
        M[c], M[r] = M[r], M[c]
        for k in range(c + 1, n):
            f = M[k][c] / M[c][c]
            M[k] = [a - f * b for a, b in zip(M[k], M[c])]
    x = [0.0] * n
    for c in reversed(range(n)):
        x[c] = (M[c][n] - sum(M[c][k] * x[k] for k in range(c + 1, n))) / M[c][c]
    return np.array(x)

def gram(X, w):
    """X^T diag(w) X by elementwise sums, no BLAS."""
    k = X.shape[1]
    return [[float((X[:, i] * X[:, j] * w).sum()) for j in range(k)] for i in range(k)]

def logit_fit(X, t, iters=50):
    """Newton-Raphson logistic regression; returns coefficients and their standard errors."""
    k = X.shape[1]
    b = np.zeros(k)
    for _ in range(iters):
        eta = sum(X[:, j] * b[j] for j in range(k))
        mu = 1 / (1 + np.exp(-eta))
        H = gram(X, mu * (1 - mu))
        g = [float((X[:, j] * (t - mu)).sum()) for j in range(k)]
        step = solve_small(H, g)
        b += step
        if np.abs(step).max() < 1e-10:
            break
    inv_diag = [solve_small(H, [1.0 if i == j else 0.0 for i in range(k)])[j] for j in range(k)]
    return b, np.sqrt(np.array(inv_diag))

for name, m in (("all labelled", np.ones(len(y), bool)), ("phase A", phase == "A"),
                ("phase A, read in full", (phase == "A") & full), ("phase B", phase == "B")):
    t = y[m].astype(float)
    lp = np.log(np.clip(p[m], 1e-9, 1 - 1e-9) / (1 - np.clip(p[m], 1e-9, 1 - 1e-9)))
    ls = np.log(size[m])
    z = lambda v: (v - v.mean()) / v.std()
    X = np.column_stack([np.ones(m.sum()), z(ls), z(lp)])
    b, se = logit_fit(X, t)
    X0 = np.column_stack([np.ones(m.sum()), z(lp)])
    b0, se0 = logit_fit(X0, t)
    print(f"{name:<22} n {m.sum():>6} REJ {int(t.sum()):>5}  AUC p {auc_exact(p[m], y[m]):.3f}  "
          f"AUC size {auc_exact(size[m].astype(float), y[m]):.3f}  |  logit(p) alone: z {b0[1] / se0[1]:+.1f}  "
          f"|  with log size: size z {b[1] / se[1]:+.1f}, logit(p) z {b[2] / se[2]:+.1f} "
          f"(coef {b[2]:+.3f} per SD)")
