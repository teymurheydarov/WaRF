"""Splitting the question seats in two (development, offline, stand-ins, no calls): locate build / runtime as two
seats, and the checklist as a build checklist (inttype, format, warning, assert) and a runtime checklist
(lifetime, concurrency, edge), each pooled as "any question" (1 - prod(1 - p(YES))). Rule logodds of search.py.

    python split.py      # writes split.log"""
import math
import search as S
import views as W
from warf.calibration import approve_logodds

BUILD, RUN = ["inttype", "format", "warning", "assert"], ["lifetime", "concurrency", "edge"]
for name, keys in (("CK.build", BUILD), ("CK.run", RUN)):
    sc = {i: 1 - math.prod(1 - W.V[f"CK:{k}"][i] for k in keys) for i in W.ids}
    W.V[name] = sc
    S.R[name] = {i: approve_logodds(min(0.99, max(0.01, round(sc[i], 2)))) for i in W.ids}
    S.say(f"  {name:<9} AUC {W.auc(sc):.3f}")
PANELS = {"BOUNDARY + LE + CK.or (3 seats, stand-ins)": ("P:BOUNDARY", "LE", "CK.or"),
          "BOUNDARY + LB + LR + CK.or (4)": ("P:BOUNDARY", "LB", "LR", "CK.or"),
          "BOUNDARY + LE + CK.build + CK.run (4)": ("P:BOUNDARY", "LE", "CK.build", "CK.run"),
          "BOUNDARY + LB + LR + CK.build + CK.run (5)": ("P:BOUNDARY", "LB", "LR", "CK.build", "CK.run"),
          "SKEPTIC + BOUNDARY + LE + CK.build + CK.run (5)": ("P:SKEPTIC", "P:BOUNDARY", "LE", "CK.build", "CK.run")}
S.say("\n10-fold x 5, rule logodds (balanced accuracy)")
for name, panel in PANELS.items():
    r = [S.run(panel, "logodds", rep) for rep in range(5)]
    S.say(f"  {name:<50} {100 * sum(r) / 5:5.1f}%  ({100 * min(r):.1f}-{100 * max(r):.1f})")
(S.HERE / "split.log").write_text("\n".join(S.out) + "\n", encoding="utf-8")
