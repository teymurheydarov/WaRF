"""Dry run of score_ddb.py on RocksDB's stored WaRF answers (../../pooled-dev): it must give the RocksDB numbers
of ../../pooled-dev/five-seats/replay_live.log (PANEL3 73.6%, LO-ctx 70.2%, FIVE 73.5% as 5-repetition means;
PANEL3 vs LO-ctx 49 vs 22 on repetition 0).

    python dry_run.py      # writes rdb_sessions.jsonl, dry_run.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
merged = {}
for f in (EXP / "pooled-dev" / "history" / "sessions_LO_ctx.jsonl", EXP / "pooled-dev" / "five-seats" / "sessions_live.jsonl"):
    for l in f.open(encoding="utf-8"):
        r = json.loads(l)
        merged.setdefault(r["artifact"], []).extend(
            {"agent": v["agent"], "vote": v["vote"], "reasoning": v["reasoning"], "p_reject": v["p_reject"]} for v in r["votes"])
with (HERE / "rdb_sessions.jsonl").open("w", encoding="utf-8") as f:
    for i, votes in merged.items():
        f.write(json.dumps({"artifact": i, "votes": votes}) + "\n")
sys.path.insert(0, str(HERE.parent))
import panel  # noqa: E402
panel.checks = lambda: [f"placeholder check {k}" for k in range(7)]      # RocksDB's answers are read by seat name
import score_ddb  # noqa: E402
sys.argv = [sys.argv[0], "--items", str(EXP / "rdb-set" / "items.jsonl"), "--sessions", str(HERE / "rdb_sessions.jsonl"),
            "--log", str(HERE / "dry_run.log")]
score_ddb.main()
