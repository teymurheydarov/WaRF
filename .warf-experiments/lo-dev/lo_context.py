"""LO plus a context seat (README.md), judged as in lo_offline.py: 10-fold x 5 cross-validation over the
352 judged items, calibration from training folds only. No calls here.

The context seat is jev-1.14 shown the whole change plus the retrieved "Related code" block (dev:
../real-set/jev-narrow/context/, confirm: ../confirm-set/jev-context/). It is its own evidence source
("context", ADR 0002), so WaRF pools it as a separate group. Two forms, fixed in advance: the usual
question as one seat, or the seven narrow checks as seven seats.

    python lo_context.py      # writes lo_context.log"""
import contextlib
import io
import json
import random
from pathlib import Path

with contextlib.redirect_stdout(io.StringIO()):
    import lo_offline as L

EXP = L.EXP
CTXV, CTXC = {}, {}
for path in (EXP / "real-set" / "jev-narrow" / "context" / "answers_context.jsonl",
             EXP / "confirm-set" / "jev-context" / "answers_context.jsonl"):
    for l in path.open(encoding="utf-8"):
        r = json.loads(l)
        p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
        CTXV[r["id"]] = [L.seat("JEV-CTX", L.DEFAULT_PERSONA, "jev-1.14", "context", p["verdict"])]
        CTXC[r["id"]] = [L.seat(f"CTX-{q}", t, "jev-1.14", "context", p[q]) for q, t in L.CHECKS.items()]
assert set(CTXV) == set(L.ITEMS), "context answers missing"

CONFIGS = {
    "LO: 5 personas (as tested)":          lambda i: L.PERS[i],
    "LO + context seat (usual question)":  lambda i: L.PERS[i] + CTXV[i],
    "LO + context seats (7 checks)":       lambda i: L.PERS[i] + CTXC[i],
    "context seat alone (usual question)": lambda i: CTXV[i],
    "one Jev seat (usual question)":       lambda i: [s for s in L.VERD[i] if s["model"] == "jev-1.14"],
}
ids = list(L.ITEMS); pos = [i for i in ids if L.Y[i] == -1]; neg = [i for i in ids if L.Y[i] == 1]
other = [i for i in pos if L.ITEMS[i].get("visible") == "needs_other_file"]
res = {k: [] for k in CONFIGS}; rec = {k: [] for k in CONFIGS}
for rep in range(5):
    rng = random.Random(100 + rep)                      # the same folds as lo_offline.py
    P, Q = pos[:], neg[:]; rng.shuffle(P); rng.shuffle(Q)
    folds = [P[k::10] + Q[k::10] for k in range(10)]
    pred = {k: {} for k in CONFIGS}
    for k in range(10):
        test = folds[k]; train = [i for f in folds[:k] + folds[k + 1:] for i in f]
        for name, cfg in CONFIGS.items():
            pred[name].update(L.run(cfg, train, test))
    for name in CONFIGS:
        res[name].append(L.ba(pred[name], ids))
        rec[name].append(sum(pred[name][i] == "REJECT" for i in other) / len(other))
out = [f"cross-validated, 352 items (10 folds x 5 repeats); {len(other)} defects need another file"]
for name in CONFIGS:
    r, c = res[name], rec[name]
    out.append(f"  {name:<38} right {100 * sum(r) / len(r):5.1f}% (repeats {100 * min(r):.1f}-{100 * max(r):.1f})"
               f"   caught of the needs-other-file defects {100 * sum(c) / len(c):5.1f}%")
out.append("\nfor information only (another look at the confirm set): calibrate on dev, decide confirm")
for name, cfg in CONFIGS.items():
    out.append(f"  {name:<38} {100 * L.ba(L.run(cfg, list(L.DEV), list(L.CONF)), list(L.CONF)):5.1f}%")
print("\n".join(out))
Path(__file__).with_name("lo_context.log").write_text("\n".join(out) + "\n", encoding="utf-8")
