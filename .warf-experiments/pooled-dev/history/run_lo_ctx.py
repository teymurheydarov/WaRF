"""LO through WaRF with a project context (development, RocksDB matched set).

Exactly ../../rdb-set/run_jev.py LO, except that run_review gets `context` = the text a user would put in
warf_context.md: the build rules (../context/rocksdb_context.md) and the project defect profile
(defect_profile.md, written from the 37 confirmed RocksDB defects outside the test set). WaRF puts it in
front of every seat's input ("Project context: ...").

    python run_lo_ctx.py      # resumes; writes sessions_LO_ctx.jsonl"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
CONTEXT = ((HERE.parent / "context" / "rocksdb_context.md").read_text(encoding="utf-8").strip()
           + "\n\nDefects found in this project's past changes (from labelled reviews):\n"
           + (HERE / "defect_profile.md").read_text(encoding="utf-8").strip())

if __name__ == "__main__":
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned")); sys.path.insert(0, str(EXP.parent))
    import run_learned as rl
    from warf.state import save_profiles
    seats = rl.p5(); agents = {p.persona: p.name for p in seats}
    prof = HERE / "profiles" / "uniform.json"; prof.parent.mkdir(exist_ok=True); save_profiles(prof, seats)
    log = EXP / "rdb-set" / "calib_sessions.jsonl"
    before = log.read_bytes()
    items = [json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")]
    out_path = HERE / "sessions_LO_ctx.jsonl"
    done = {json.loads(l)["jev"]["id"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"LO with project context: {len(todo)} reviews to run ({len(done)} done)", flush=True)
    tap, total = rl.Tap(), 0.0
    with out_path.open("a", encoding="utf-8") as out:
        for n, it in enumerate(todo, 1):
            res, got, cost, models = rl.review({**it, "context": CONTEXT}, prof, agents, tap, aggregate="logodds", log_path=log)
            total += cost
            rec = rl.session_dict(res, artifact_path=it["id"], profile_name="LO_ctx")
            rec["jev"] = {"id": it["id"], "kind": it["kind"], "models": models, "cost": round(cost, 8), **got}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}  ${total:.4f}", flush=True)
    if log.read_bytes() != before:
        sys.exit("the calibration log changed during the run")
    print(f"done: cost ${total:.4f}", flush=True)
