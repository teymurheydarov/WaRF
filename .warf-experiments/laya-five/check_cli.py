"""Does run_five.py review a file the way WaRF itself does? For the first N commits of
sessions.jsonl, run the real `warf review-commit <sha> --debate --json` with the same
five-Laya profile in a scratch WARF_HOME and compare the reviewed file's session with the
runner's: every vote with its probability readout in both rounds, Lambda, the decision.
review-commit has no --no-early-stop, so on a commit where the SPRT fires (009fa8 and d7525b
of the 100) it stops at the boundary and differs by design; none of the first three does.

    python .warf-experiments/laya-five/check_cli.py SCRATCH_DIR [N]      # output: check_cli.log"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WARF = HERE.parent.parent
scratch = Path(sys.argv[1]).resolve()
n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
if (scratch / "sessions.jsonl").exists():
    sys.exit(f"{scratch} already holds sessions; use an empty directory")
(scratch / "profiles").mkdir(parents=True, exist_ok=True)
shutil.copy(HERE / "profiles" / "laya_five.json", scratch / "profiles" / "laya_five.json")
plan = {e["sha"]: e for e in map(json.loads, (WARF / ".warf-experiments" / "laya-sweep" / "plan.jsonl").open(encoding="utf-8"))}
runner = [json.loads(line) for line in (HERE / "sessions.jsonl").open(encoding="utf-8")][:n]
env = dict(os.environ, WARF_HOME=str(scratch), WARF_NO_BROWSER="1", PYTHONIOENCODING="utf-8")


def votes(record: dict, key: str) -> list:
    rows = record.get(key) or []
    return [(v["agent"], v["vote"], v["reasoning"]) for v in rows]


bad = 0
for r in runner:
    f = r["five"]
    entry = plan[f["commit"]]
    proc = subprocess.run([sys.executable, "-m", "warf", "review-commit", f["commit"], "--repo", entry["worktree"],
                           "--debate", "--profile", "laya_five", "--force", "--json"],
                          cwd=WARF, env=env, capture_output=True, text=True, encoding="utf-8")
    out = json.loads(proc.stdout)
    cli = next(s for s in out["reviews"] if s.get("artifact") == f"{f['commit']}:{f['file']}")
    same = {
        "round 1 votes": votes(cli, "votes") == votes(r, "votes"),
        "debate votes": votes(cli.get("debate") or {}, "votes") == votes(r.get("debate") or {}, "votes"),
        "lambda": cli["sprt_lambda"] == r["sprt_lambda"],
        "decision": (cli["decision"], cli["confidence"]) == (r["decision"], r["confidence"]),
    }
    bad += not all(same.values())
    print(f"  {f['id']} {f['commit'][:9]} {f['file']}: {len(out['reviews'])} file(s) in the commit; "
          + ", ".join(f"{k} {'same' if v else 'DIFFERENT'}" for k, v in same.items()))
    if not all(same.values()):
        print("    cli   ", votes(cli, "votes"), cli.get("debate"))
        print("    runner", votes(r, "votes"), r.get("debate"))
print(f"  {len(runner) - bad} of {len(runner)} identical")
