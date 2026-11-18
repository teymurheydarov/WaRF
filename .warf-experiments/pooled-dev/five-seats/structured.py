"""Five-seat panels chosen by a rule, not by searching panel scores (development, offline, no calls).

Rule: the best single seat of each kind by its own AUC (views.py): a persona seat per model (SKEPTIC on
jev-1.14, BOUNDARY on jev-1.13), the locate seat asking build and runtime in one call (LE), the checklist
seat asking the seven checks in one call (CK.or); the fifth seat is varied. Same CV and rules as search.py.

    python structured.py      # writes structured.log"""
from search import run, say, out, HERE  # noqa: F401

CORE = ("P:SKEPTIC", "P:BOUNDARY", "LE", "CK.or")
PANELS = {"4 seats: SKEPTIC + BOUNDARY + LOCATE + CHECKLIST": CORE,
          "+ WaRF's default question (V.prof_ctx)": CORE + ("V.prof_ctx",),
          "+ the diagnostics checklist (DG.mean)": CORE + ("DG.mean",),
          "+ the compile question (C.prof_ctx)": CORE + ("C.prof_ctx",),
          "+ AUDITOR": CORE + ("P:AUDITOR",),
          "3 seats: BOUNDARY + LOCATE + CHECKLIST": ("P:BOUNDARY", "LE", "CK.or"),
          "2 seats: LOCATE + CHECKLIST": ("LE", "CK.or")}
say("Structured panels, 10-fold x 5 within RocksDB (balanced accuracy)")
for name, panel in PANELS.items():
    lo = [run(panel, "logodds", r) for r in range(5)]; le = [run(panel, "learned", r) for r in range(5)]
    say(f"  {name:<48} logodds {100 * sum(lo) / 5:5.1f}% ({100 * min(lo):.1f}-{100 * max(lo):.1f})  "
        f"learned {100 * sum(le) / 5:5.1f}% ({100 * min(le):.1f}-{100 * max(le):.1f})")
(HERE / "structured.log").write_text("\n".join(out) + "\n", encoding="utf-8")
