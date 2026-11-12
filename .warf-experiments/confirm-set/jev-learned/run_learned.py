"""The mixed-version Jev panel after WaRF has learned (../README.md, fifth test, 2026-11-11).

    python run_learned.py learn                 # dev: review + label each of the 132 items -> dev_sessions.jsonl, profiles/learned.json
    python run_learned.py test --arm LV|LO      # the 220 confirm items, no learning -> sessions_<arm>.jsonl

WaRF does the work: warf.orchestrator.run_review (no debate, every seat asked), apply_oracle and
warf.logger.append_session for the learning, aggregate="logodds" with the dev log for LO. Seats are
the fourth test's P5. Resumes. The API key is never printed or stored; nothing is written to WaRF's
data directory."""
import contextlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import Tap, answers  # noqa: E402  (also points WARF_HOME away from the user's data)
from warf.logger import append_session, session_dict  # noqa: E402
from warf.orchestrator import apply_oracle, run_review  # noqa: E402
from warf.state import default_profiles, save_profiles  # noqa: E402

INPUT_LABEL = "Patch under review (unified diff)"
PROF = HERE / "profiles"
DEV_LOG = HERE / "dev_sessions.jsonl"


def p5():
    seats = default_profiles()
    for k, p in enumerate(seats):
        p.provider, p.model = "jev", ("jev-1.14" if k < 3 else "jev-1.13")
    return seats


def review(it, path, agents, tap, **kw):
    tap.calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        res = run_review(it["code"], it["domain"], path, verbose=False, debate=False,
                         input_label=INPUT_LABEL, context=it["context"], no_early_stop=True, **kw)
    got = answers(tap.calls, agents)
    if len(got["round1"]) != len(agents):
        sys.exit(f"{it['id']}: {len(got['round1'])} answers for {len(agents)} seats")
    cost = sum(float((c["body"].get("usage") or {}).get("cost") or 0) for c in tap.calls)
    return res, got, cost, sorted({c["body"].get("model") for c in tap.calls})


def main():
    phase = sys.argv[1]
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    PROF.mkdir(exist_ok=True)
    seats = p5()
    agents = {p.persona: p.name for p in seats}
    tap, total = Tap(), 0.0
    if phase == "learn":
        learned = PROF / "learned.json"
        if not learned.exists():
            save_profiles(learned, seats)
        items = [json.loads(l) for l in (EXP / "real-set" / "items.jsonl").open(encoding="utf-8")]
        done = set()
        if DEV_LOG.exists():
            done = {json.loads(l)["artifact"] for l in DEV_LOG.open(encoding="utf-8")}
        todo = [it for it in items if it["id"] not in done]
        print(f"learn: {len(todo)} dev reviews to run ({len(done)} done)", flush=True)
        for n, it in enumerate(todo, 1):
            res, got, cost, models = review(it, learned, agents, tap)
            total += cost
            x_star = -1 if it["kind"] == "defective" else 1
            with contextlib.redirect_stdout(io.StringIO()):
                upd = apply_oracle(res, x_star, "DEVELOPER", learned, verbose=False)
            append_session(res, it["id"], oracle_type="DEVELOPER", x_star=x_star, weight_updates=upd,
                           log_path=DEV_LOG, profile_name="learned")
            if n % 20 == 0:
                print(f"  {n}/{len(todo)}  ${total:.4f}", flush=True)
        shutil.copy(learned, PROF / "learned_frozen.json")
    else:
        arm = sys.argv[sys.argv.index("--arm") + 1]
        if arm == "LV":
            path, kw = PROF / "learned_frozen.json", {}
        else:
            path = PROF / "uniform.json"
            save_profiles(path, seats)
            kw = {"aggregate": "logodds", "log_path": DEV_LOG}
        items = [json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")]
        out_path = HERE / f"sessions_{arm}.jsonl"
        done = {json.loads(l)["jev"]["id"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
        todo = [it for it in items if it["id"] not in done]
        before = path.read_bytes()
        print(f"test {arm}: {len(todo)} reviews to run ({len(done)} done)", flush=True)
        with out_path.open("a", encoding="utf-8") as out:
            for n, it in enumerate(todo, 1):
                res, got, cost, models = review(it, path, agents, tap, **kw)
                total += cost
                rec = session_dict(res, artifact_path=it["id"], profile_name=arm)
                rec["jev"] = {"id": it["id"], "kind": it["kind"], "models": models, "cost": round(cost, 8), **got}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
                if n % 20 == 0:
                    print(f"  {n}/{len(todo)}  ${total:.4f}", flush=True)
        if path.read_bytes() != before:
            sys.exit(f"{path} changed during the test")
    print(f"done: cost ${total:.4f}", flush=True)


if __name__ == "__main__":
    main()
