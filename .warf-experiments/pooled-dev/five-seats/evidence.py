"""A fourth and fifth seat that sees other evidence (development, offline, stand-ins, no calls): the whole commit
(../context states commit / both: verdict and compile), and the retrieved declarations (../decl states decl /
decl_ctx: the verdict and the seven checks, pooled as the checklist rule). Each is its own group (ADR 0002).
Rule logodds of search.py.

    python evidence.py      # writes evidence.log"""
import json
import math
from pathlib import Path

import search as S
import views as W
from warf.calibration import approve_logodds

CHK = W.CHK
for l in (Path(S.HERE).parent / "decl" / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = [(r["answers"][k]["p"] or {}).get("YES", 0.0) for k in CHK]
    W.V.setdefault(f"CK.{r['state']}", {})[r["id"]] = 1 - math.prod(1 - x for x in p)
    W.V.setdefault(f"V.{r['state']}", {})[r["id"]] = (r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0)
NEW = ["V.commit", "C.commit", "V.both", "C.both", "CK.decl", "CK.decl_ctx", "V.decl", "V.decl_ctx"]
for name in NEW:
    S.R[name] = {i: approve_logodds(min(0.99, max(0.01, round(W.V[name][i], 2)))) for i in W.ids}
    S.say(f"  {name:<12} AUC {W.auc(W.V[name]):.3f}")
CORE = ("P:BOUNDARY", "LE", "CK.or")
S.say("\n10-fold x 5, rule logodds (balanced accuracy)")
r = [S.run(CORE, "logodds", rep) for rep in range(5)]
S.say(f"  {'core: BOUNDARY + LE + CK.or':<42} {100 * sum(r) / 5:5.1f}%")
for name in NEW:
    r = [S.run(CORE + (name,), "logodds", rep) for rep in range(5)]
    S.say(f"  {'core + ' + name:<42} {100 * sum(r) / 5:5.1f}%  ({100 * min(r):.1f}-{100 * max(r):.1f})")
for pair in (("V.commit", "CK.decl_ctx"), ("C.both", "CK.decl_ctx"), ("V.both", "CK.decl_ctx")):
    r = [S.run(CORE + pair, "logodds", rep) for rep in range(5)]
    S.say(f"  {'core + ' + ' + '.join(pair):<42} {100 * sum(r) / 5:5.1f}%  ({100 * min(r):.1f}-{100 * max(r):.1f})")
(S.HERE / "evidence.log").write_text("\n".join(S.out) + "\n", encoding="utf-8")
