"""Panels of at most five seats through WaRF's run_review, from live WaRF answers only (development, no calls).

Every answer is one WaRF recorded: SKEPTIC and BOUNDARY from ../history/sessions_LO_ctx.jsonl, the question
seats from sessions_live.jsonl (run_live.py), all with the project context. Same harness, folds and paired
test as ../warf-panel/replay_learned.py and paired.py; calibration from the training folds' sessions.

    python replay_live.py      # writes replay_live.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "warf-panel")); sys.path.insert(0, str(HERE))
import replay_learned as R  # noqa: E402
from paired import mcnemar, predict  # noqa: E402
import views as W  # noqa: E402
from run_live import SEATS  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


live = {json.loads(l)["artifact"]: json.loads(l) for l in (HERE / "sessions_live.jsonl").open(encoding="utf-8")}
if set(live) != set(R.ids):
    raise SystemExit(f"{len(set(R.ids) - set(live))} live reviews missing")
for i, rec in live.items():
    for v in rec["votes"]:
        R.P[(i, v["agent"])] = v["p_reject"]; R.READ[(i, v["agent"])] = v["reasoning"]
BY = {(s.persona, s.model): s for s in R.personas + SEATS}


def stub(persona, code, domain, **kw):
    s = BY[(persona, kw["model"])]
    i = R.CURRENT[0]
    return R.vote_of(i, s), R.readout(i, s), 0, 0, kw["provider"], kw["model"]


R.stub = stub
R.PANEL = HERE / "panel_replay.json"
P = {s.name: s for s in R.personas + SEATS}

say("AUC of each live seat on the 800 changes (stand-in used before, in brackets)")
for name, stand in (("DEFAULT", "V.prof_ctx"), ("LOCATE", "LE"), ("CHECKLIST", "CK.or"), ("LOCATE-13", "LE"),
                    ("CHECKLIST-13", "CK.or")):
    say(f"  {name:<13} {W.auc({i: R.P[(i, name)] for i in R.ids}):.3f}  ({W.auc(W.V[stand]):.3f})")

PANELS = {"LO with context (5 persona seats)": [P[n] for n in ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")],
          "3: BOUNDARY + LOCATE + CHECKLIST": [P["BOUNDARY"], P["LOCATE"], P["CHECKLIST"]],
          "5: SKEPTIC + BOUNDARY + DEFAULT + LOCATE + CHECKLIST": [P[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT",
                                                                                   "LOCATE", "CHECKLIST")],
          "5: ... with LOCATE-13 + CHECKLIST-13": [P[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT", "LOCATE-13",
                                                                  "CHECKLIST-13")],
          "5: ... with LOCATE-13 + CHECKLIST": [P[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT", "LOCATE-13", "CHECKLIST")],
          "5: ... with LOCATE + CHECKLIST-13": [P[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT", "LOCATE", "CHECKLIST-13")]}
say("\nWaRF run_review, live answers, 10-fold x 5 (balanced accuracy)")
for name, panel in PANELS.items():
    m, a, b, modes = R.replay(panel, "logodds")
    say(f"  {name:<52} --aggregate logodds {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
pred = {name: predict(panel, "logodds") for name, panel in PANELS.items()}
ref = "LO with context (5 persona seats)"
say("\nExact McNemar against LO with context, repetition 0 (right only in the panel, only in LO, p)")
for name in list(PANELS)[1:]:
    n10, n01, p = mcnemar(pred[name], pred[ref])
    say(f"  {name:<52} {n10} vs {n01}, p = {p:.3f}")
(HERE / "replay_live.log").write_text("\n".join(out) + "\n", encoding="utf-8")
