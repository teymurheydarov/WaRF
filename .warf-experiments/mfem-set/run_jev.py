"""The frozen arms of README.md on the 300 MFEM items. No learning; nothing from MFEM enters LO's calibration.

    python run_jev.py LO        # WaRF run_review, the five-seat panel, aggregate="logodds",
                                # log_path = ../confirm-set/jev-learned/dev_sessions.jsonl -> sessions_LO.jsonl
    python run_jev.py narrow    # ../real-set/jev-narrow/run_narrow.py on items.jsonl (whole + hunks) -> answers_narrow.jsonl

The API key is never printed or stored; nothing is written to WaRF's data directory."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ITEMS = HERE / "items.jsonl"

if __name__ == "__main__":
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    if sys.argv[1] == "narrow":
        sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
        import run_narrow
        sys.argv = [sys.argv[0], "--items", str(ITEMS), "--out", str(HERE / "answers_narrow.jsonl"), "--workers", "4"]
        run_narrow.main()
        sys.exit()
    sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned"))
    import run_learned as rl                       # its p5(), review(), Tap and session_dict
    from warf.state import save_profiles
    seats = rl.p5(); agents = {p.persona: p.name for p in seats}
    prof = HERE / "profiles" / "uniform.json"; prof.parent.mkdir(exist_ok=True); save_profiles(prof, seats)
    log = EXP / "confirm-set" / "jev-learned" / "dev_sessions.jsonl"
    before = log.read_bytes()
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    out_path = HERE / "sessions_LO.jsonl"
    done = {json.loads(l)["jev"]["id"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"LO: {len(todo)} reviews to run ({len(done)} done)", flush=True)
    tap, total = rl.Tap(), 0.0
    with out_path.open("a", encoding="utf-8") as out:
        for n, it in enumerate(todo, 1):
            res, got, cost, models = rl.review(it, prof, agents, tap, aggregate="logodds", log_path=log)
            total += cost
            rec = rl.session_dict(res, artifact_path=it["id"], profile_name="LO")
            rec["jev"] = {"id": it["id"], "kind": it["kind"], "models": models, "cost": round(cost, 8), **got}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}  ${total:.4f}", flush=True)
    if log.read_bytes() != before:
        sys.exit("the calibration log changed during the run")
    print(f"done: cost ${total:.4f}", flush=True)
