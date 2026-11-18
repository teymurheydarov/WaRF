"""The five-seat panel through WaRF's own run_review, from stored answers (development, no calls).

Panel (profile panel5.json, written here), every seat on Jev with the project context:
  SKEPTIC   jev-1.14  persona seat of LO with the context (../history/sessions_LO_ctx.jsonl)
  BOUNDARY  jev-1.13  persona seat of LO with the context
  DEFAULT   jev-1.14  WaRF's default question (run_narrow.DEFAULT_PERSONA); stand-in: the verdict of the
                      prof_ctx state (../history/answers.jsonl: profile + build rules + the change)
  LOCATE    jev-1.14  question "locate", two questions in one call (build, runtime: ../locate/run_locate.py);
                      stand-in 1 - min_w (p_w,build(NONE) * p_w,runtime(NONE)), the provider's rule
  CHECKLIST jev-1.14  question "check", the seven project checks in one call (../history/run_checks.py);
                      stand-in 1 - prod(1 - p(YES)), the provider's rule (stored without the context)
Same harness and folds as ../warf-panel/replay_learned.py; also the 3-seat panel BOUNDARY + LOCATE +
CHECKLIST, and paired exact McNemar tests on repetition 0.

    python replay5.py      # writes replay5.log"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "warf-panel")); sys.path.insert(0, str(HERE))
import replay_learned as R  # noqa: E402
from paired import mcnemar, predict  # noqa: E402
import views as W  # noqa: E402
from run_checks import rn  # noqa: E402
from run_locate import LOCATE  # noqa: E402
from warf.state import AgentProfile, persona_hash  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def seat(name, persona, model, question=None):
    return AgentProfile(name=name, persona=persona, provider="jev", model=model, persona_hash=persona_hash(persona),
                        question=question)


by_name = {s.name: s for s in R.personas}
DEFAULT = seat("DEFAULT", rn.DEFAULT_PERSONA, "jev-1.14")
LOC = seat("LOCATE", "\n".join(LOCATE.values()), "jev-1.14", "locate")
CHK = seat("CHECKLIST", "\n".join(rn.CHECKS.values()), "jev-1.14", "check")
for s in (DEFAULT, LOC, CHK):
    R.BY_PERSONA[s.persona] = s
for i in R.ids:
    R.P[(i, "DEFAULT")] = W.V["V.prof_ctx"][i]
    R.P[(i, "LOCATE")] = W.V["LE"][i]
    R.P[(i, "CHECKLIST")] = W.V["CK.or"][i]
R.PANEL = HERE / "panel5.json"
FIVE = [by_name["SKEPTIC"], by_name["BOUNDARY"], DEFAULT, LOC, CHK]
THREE = [by_name["BOUNDARY"], LOC, CHK]

say("WaRF run_review on 800 RocksDB changes, stored Jev answers, 10-fold x 5 (balanced accuracy)")
for name, panel in (("LO with context (5 persona seats)", R.personas), ("3 seats: BOUNDARY + LOCATE + CHECKLIST", THREE),
                    ("5 seats: SKEPTIC + BOUNDARY + DEFAULT + LOCATE + CHECKLIST", FIVE)):
    for agg in ("logodds", "learned"):
        m, a, b, modes = R.replay(panel, agg)
        say(f"  {name:<58} --aggregate {agg:<8} {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})  ran as {sorted(modes)}")
R.save_profiles(R.PANEL, FIVE)
pred = {"LO": predict(R.personas, "logodds"), "3": predict(THREE, "logodds"), "5": predict(FIVE, "logodds"),
        "14": predict(R.seats, "logodds")}
say("\nExact McNemar, repetition 0, --aggregate logodds (changes right only in the first, only in the second, p)")
for a, b in (("5", "LO"), ("3", "LO"), ("5", "14"), ("5", "3")):
    n10, n01, p = mcnemar(pred[a], pred[b])
    say(f"  {a + ' seats' if a != 'LO' else 'LO':<9} vs {b + ' seats' if b != 'LO' else 'LO':<9}: {n10} vs {n01}, p = {p:.3f}")
R.save_profiles(R.PANEL, FIVE)
(HERE / "replay5.log").write_text("\n".join(out) + "\n", encoding="utf-8")
