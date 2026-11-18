"""Freeze the arms of README.md from the 652 labelled G+Smo and MFEM items, before any KeePassXC item exists.

    python freeze.py      # writes calib_sessions.jsonl (LO), calib_V1.jsonl, calib_size.jsonl, frozen.json

Its functions (added, size_p, features, fit_logistic, joint_lambda) are also used by score_kpx.py."""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent))
from warf.calibration import approve_logodds, p_reject_from_text  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402
from warf.state import persona_hash  # noqa: E402

SIZE_TEXT = "added-line count of the file's diff"


def added(code):
    return sum(1 for ln in code.split(_SEPARATOR, 1)[0].splitlines() if ln.startswith("+") and not ln.startswith("+++"))


def size_p(code):
    """The size seat's p(REJECT): sigmoid(ln(1 + added) - 3), kept inside WaRF's [0.01, 0.99]."""
    return min(0.99, max(0.01, 1 / (1 + math.exp(-(math.log1p(added(code)) - 3)))))


def features(votes, code, size=True):
    r = {m: [approve_logodds(v["p_reject"]) for v in votes if v["model"] == m] for m in ("jev-1.14", "jev-1.13")}
    x = [1.0, sum(r["jev-1.14"]) / len(r["jev-1.14"]), sum(r["jev-1.13"]) / len(r["jev-1.13"])]
    return x + [-(math.log1p(added(code)) - 3)] if size else x


def solve(H, g):
    n = len(g); M = [row[:] + [g[r]] for r, row in enumerate(H)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [M[r][n] / M[r][r] for r in range(n)]


def fit_logistic(X, y, prior_sd=1.0, iters=50):
    """MAP logistic regression of clean (+1) on X, every coefficient ~ N(0, prior_sd^2); Newton
    (the same as ../size-seat/size_seat.py)."""
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
            return w
    raise RuntimeError("logistic fit did not converge")


def joint_lambda(frozen, votes, code, size=True):
    w = frozen["JOINT" if size else "JOINT-noSize"]
    return sum(a * b for a, b in zip(w, features(votes, code, size))) - frozen["prior_logodds"]


def main():
    items = {}
    for f in ("real-set/items.jsonl", "confirm-set/items.jsonl", "mfem-set/items.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l); items[r["id"]] = r
    keep = ("agent", "persona", "provider", "model", "vote", "p_reject")
    sessions = {}
    for f in ("confirm-set/jev-learned/dev_sessions.jsonl", "confirm-set/jev-learned/sessions_LO.jsonl",
              "mfem-set/sessions_LO.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l)
            votes = []
            for v in r["votes"]:
                p = p_reject_from_text(v["reasoning"])        # the dev log has no p_reject field: WaRF reads it so
                if v.get("p_reject", p) != p:
                    raise SystemExit(f"{r['artifact']} {v['agent']}: logged p differs from its readout")
                votes.append({k: v[k] for k in keep if k != "p_reject"} | {"p_reject": p, "evidence_source": ""})
            sessions[r["artifact"]] = votes
    if set(sessions) != set(items):
        raise SystemExit("persona votes missing for some items")
    x = {i: (-1 if it["kind"] == "defective" else 1) for i, it in items.items()}
    with (HERE / "calib_sessions.jsonl").open("w", encoding="utf-8") as f:
        for i in items:
            f.write(json.dumps({"artifact": i, "oracle": {"type": "DEVELOPER", "x_star": x[i]}, "votes": sessions[i]}) + "\n")

    sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
    from run_narrow import DEFAULT_PERSONA
    v1 = {}
    for f in ("real-set/jev-narrow/answers.jsonl", "confirm-set/jev-narrow/answers.jsonl", "mfem-set/answers_narrow.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l)
            if r["state"] == "whole" and "jev-1.14" in r["model"]:
                v1[r["id"]] = min(0.99, max(0.01, round((r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0), 2)))
    if set(v1) != set(items):
        raise SystemExit("one-Jev answers missing for some items")
    for name, agent, text, provider, model, p in (
            ("calib_V1.jsonl", "JEV", DEFAULT_PERSONA, "jev", "jev-1.14", v1),
            ("calib_size.jsonl", "SIZE", SIZE_TEXT, "size", "", {i: size_p(it["code"]) for i, it in items.items()})):
        with (HERE / name).open("w", encoding="utf-8") as f:
            for i in items:
                vote = {"agent": agent, "persona": persona_hash(text), "provider": provider, "model": model,
                        "evidence_source": "", "vote": -1 if p[i] >= 0.5 else 1, "p_reject": p[i]}
                f.write(json.dumps({"artifact": i, "oracle": {"type": "DEVELOPER", "x_star": x[i]}, "votes": [vote]}) + "\n")

    ids = list(items); y = [x[i] for i in ids]
    n_clean = sum(t == 1 for t in y)
    frozen = {"trained_on": len(ids), "prior_logodds": math.log((n_clean + 1) / (len(ids) - n_clean + 1)),
              "inputs": ["1", "mean ln((1-p)/p) jev-1.14 seats", "same for jev-1.13", "-(ln(1+added)-3)"],
              "JOINT": fit_logistic([features(sessions[i], items[i]["code"]) for i in ids], y),
              "JOINT-noSize": fit_logistic([features(sessions[i], items[i]["code"], size=False) for i in ids], y)}
    (HERE / "frozen.json").write_text(json.dumps(frozen, indent=1))
    print(f"{len(ids)} training items ({n_clean} clean); JOINT weights "
          + ", ".join(f"{w:+.3f}" for w in frozen["JOINT"]) + "; JOINT-noSize "
          + ", ".join(f"{w:+.3f}" for w in frozen["JOINT-noSize"]))


if __name__ == "__main__":
    main()
