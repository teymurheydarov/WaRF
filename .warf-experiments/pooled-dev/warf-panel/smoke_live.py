"""Live smoke run: the 14-seat panel (panel.json) through WaRF's run_review against the real Jev, on 10
RocksDB changes (5 defective, 5 clean, fixed seed), with the project context as ../history/run_lo_ctx.py
gives it. Checks that the locate and check seats work end to end, and compares each seat's live p(REJECT)
with the stored answer replay_learned.py used for it (the persona and locate seats were stored with the
project context, the check seats without it).

    python smoke_live.py      # about 150 Jev calls; writes smoke_live.log"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

if not os.environ.get("TYPESAFE_API_KEY"):
    sys.exit("TYPESAFE_API_KEY is not set")
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-smoke-")     # nothing reaches a real data directory
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay_learned as R  # noqa: E402  (stored answers, panel, items; its run is under __main__)
from warf import orchestrator  # noqa: E402
sys.path.insert(0, str(R.EXP / "confirm-set" / "jev-learned"))
from run_learned import INPUT_LABEL  # noqa: E402
sys.path.insert(0, str(HERE.parent / "history"))
from run_lo_ctx import CONTEXT  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


rng = random.Random(14)
D = [i for i in R.ids if R.Y[i] == -1]; C = [i for i in R.ids if R.Y[i] == 1]
pick = rng.sample(D, 5) + rng.sample(C, 5)
R.save_profiles(R.PANEL, R.seats)
empty = Path(tempfile.mkdtemp()) / "empty.jsonl"
diffs = {s.name: [] for s in R.seats}
calls = tokens = 0
for i in pick:
    it = R.items[i]
    r = orchestrator.run_review(it["code"], it["domain"], R.PANEL, verbose=False, input_label=INPUT_LABEL,
                                context=CONTEXT, aggregate="logodds", log_path=empty, no_early_stop=True)
    got = {v.agent_name: v for v in r.votes}
    if set(got) != {s.name for s in R.seats}:
        say(f"  {i}: seats without a vote: {sorted({s.name for s in R.seats} - set(got))}")
    for s in R.seats:
        if s.name in got and got[s.name].p_reject is not None:
            diffs[s.name].append(got[s.name].p_reject - R.P[(i, s.name)])
    loc = got.get("LOCATE-BUILD")
    say(f"  {i:<48} {r.decision.value:<7}  build {loc.p_reject if loc else None}  "
        f"{(loc.reasoning.splitlines()[-1][:60] if loc else '')}")
    tokens += sum(v.tokens_in for v in r.votes)
say("\nLive p(REJECT) minus stored, per seat (mean absolute difference over the 10 changes)")
for s in R.seats:
    d = diffs[s.name]
    say(f"  {s.name:<20} {s.question or 'verdict':<8} n={len(d):2d}  mean |diff| "
        f"{(sum(abs(x) for x in d) / len(d)) if d else float('nan'):.3f}  mean diff {(sum(d) / len(d)) if d else float('nan'):+.3f}")
say(f"\ninput tokens {tokens}")
(HERE / "smoke_live.log").write_text("\n".join(out) + "\n", encoding="utf-8")
