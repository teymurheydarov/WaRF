"""Mixed-version Jev panels in WaRF on the 220 confirm items (../README.md, fourth test, 2026-11-11).

    python .warf-experiments/confirm-set/jev-panels/run_panels.py --arm P5|P3 [--limit N]

WaRF does the review: warf.orchestrator.run_review, vote aggregation, uniform priors, no debate,
no_early_stop (every seat answers; WaRF's verdict is unchanged by it). Seats are WaRF's default
personas in their default order, the first ones on jev-1.14 and the rest on jev-1.13 (ARMS). Jev's
full-precision answers are kept with ../../laya-five/run_five.py's Tap. Writes sessions_<arm>.jsonl
here and resumes. The API key is never printed or stored; nothing is written to WaRF's data directory."""
import argparse
import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import Tap, answers  # noqa: E402  (also points WARF_HOME away from the user's data)
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import default_profiles, save_profiles  # noqa: E402

INPUT_LABEL = "Patch under review (unified diff)"
ARMS = {"P5": (5, 3), "P3": (3, 2)}          # (seats, how many of the first ones are on jev-1.14)


def profile(arm):
    n, on14 = ARMS[arm]
    seats = default_profiles()[:n]
    for k, p in enumerate(seats):
        p.provider, p.model = "jev", ("jev-1.14" if k < on14 else "jev-1.13")
    path = HERE / "profiles" / f"{arm}.json"
    path.parent.mkdir(exist_ok=True)
    save_profiles(path, seats)
    return path, {p.persona: p.name for p in seats}, {p.name: p.model for p in seats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS), required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    path, agents, seat_model = profile(a.arm)
    items = [json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")]
    out_path = HERE / f"sessions_{a.arm}.jsonl"
    done = {json.loads(l)["jev"]["id"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    todo = [it for it in items if it["id"] not in done][: a.limit or None]
    print(f"{a.arm}: seats {seat_model}; {len(todo)} reviews to run ({len(done)} done)", flush=True)
    tap, cost, errors, t0 = Tap(), 0.0, 0, time.time()
    with out_path.open("a", encoding="utf-8") as out:
        for n, it in enumerate(todo, 1):
            tap.calls.clear()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    res = run_review(it["code"], it["domain"], path, verbose=False, debate=False,
                                     input_label=INPUT_LABEL, context=it["context"], no_early_stop=True)
            except Exception as exc:
                errors += 1
                print(f"  {it['id']}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                if errors >= 3:
                    sys.exit("stopping: 3 consecutive errors")
                continue
            errors = 0
            got = answers(tap.calls, agents)
            for v in res.votes:                  # the tap and WaRF's votes must agree
                if (got["round1"][v.agent_name]["choice"] == "APPROVE") != (v.vote == 1):
                    sys.exit(f"{it['id']}: {v.agent_name} vote {v.vote} vs {got['round1'][v.agent_name]}")
            if len(got["round1"]) != len(agents):
                sys.exit(f"{it['id']}: {len(got['round1'])} answers for {len(agents)} seats")
            models = {c["body"].get("model") for c in tap.calls}
            c = sum(float((x["body"].get("usage") or {}).get("cost") or 0) for x in tap.calls); cost += c
            rec = session_dict(res, artifact_path=f"{it['commit']}:{it['file']}", profile_name=a.arm)
            rec["jev"] = {"id": it["id"], "kind": it["kind"], "seat_model": seat_model, "models": sorted(models),
                          "cost": round(c, 8), **got}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            if n % 20 == 0:
                print(f"  {n}/{len(todo)}  {(time.time() - t0) / n:.1f} s per review, ${cost:.4f}", flush=True)
    print(f"done: cost ${cost:.4f}", flush=True)


if __name__ == "__main__":
    main()
