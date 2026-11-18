"""Which seats a WaRF Jev panel needs (development, offline, no calls).

Every feature is one seat's own log-odds (no group means), as WaRF's learned aggregation will see them,
and every seat is one WaRF can express with the project context set for all seats:
  LO ctx     the five persona seats of ../history/sessions_LO_ctx.jsonl (context: build rules + profile)
  locate     ../locate: "which added line breaks a build" / "... runtime defect", or NONE (with context)
  diag       ../locate: the eleven YES/NO diagnostics (with context)
  checks     ../history/answers_checks.jsonl: the seven project checks, whole change (asked WITHOUT
             context: a stand-in for the same check seats with context)
Learned weights as in ../history/stack.py (10-fold x 5 within RocksDB).

    python select_panel.py      # writes select_panel.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "history"))
import stack as K  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


SEATS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
LOC = {}
for l in (HERE.parent / "history" / "sessions_LO_ctx.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    LOC[r["artifact"]] = {v["agent"]: K.p_reject_from_text(v["reasoning"]) for v in r["votes"]}
none, DIAG = {}, {}
for l in (HERE.parent / "locate" / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l); a = r["answers"]
    for q in ("build", "runtime"):
        none.setdefault(r["id"], {}).setdefault(q, 1.0)
        none[r["id"]][q] *= (a[q]["p"] or {}).get("NONE", 1.0)
    if r["window"] == 0:
        DIAG[r["id"]] = {k: (v["p"] or {}).get("YES", 0.0) for k, v in a.items() if k not in ("build", "runtime")}

lo = lambda i: [K.lg(LOC[i][s]) for s in SEATS]  # noqa: E731
loc = lambda i: [K.lg(1 - none[i]["build"]), K.lg(1 - none[i]["runtime"])]  # noqa: E731
dg = lambda i: [K.lg(DIAG[i][k]) for k in sorted(DIAG[i])]  # noqa: E731
ck = lambda i: [K.lg(K.whole[i][q]) for q in K.CHK]  # noqa: E731
V = {"LO ctx (5 seats)": lo,
     "LO ctx + locate (7)": lambda i: lo(i) + loc(i),
     "LO ctx + locate + diag (18)": lambda i: lo(i) + loc(i) + dg(i),
     "LO ctx + locate + checks (14)": lambda i: lo(i) + loc(i) + ck(i),
     "LO ctx + locate + diag + checks (25)": lambda i: lo(i) + loc(i) + dg(i) + ck(i)}
say("Per-seat learned weights, 10-fold x 5 within RocksDB (balanced accuracy)")
for name, f in V.items():
    for sd in (1.0, 0.3):
        m, a, b = K.cv(f, sd)
        say(f"  {name:<38} prior sd {sd}: {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
(HERE / "select_panel.log").write_text("\n".join(out) + "\n", encoding="utf-8")
