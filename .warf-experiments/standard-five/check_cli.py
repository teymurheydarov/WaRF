"""Does run_standard.py send what WaRF itself sends? For single-file commits of the selection, run
the real `warf review-commit <sha> --debate --profile standard_five --debug --json` in a scratch
WARF_HOME, with the environment run_standard.py gives its agents, and compare every message that
WaRF's debug log shows going to an agent:
  Round 1  with the message run_standard.py sends (run_five.prepare in WaRF's own format);
  Round 2  with _build_debate_prompt rebuilt from the CLI's own Round-1 votes.
Haiku's answers vary from run to run, so they are not compared; their provider and model are.
review-commit has no --no-early-stop, so a review whose SPRT fires in Round 1 has no Round 2.

    python .warf-experiments/standard-five/check_cli.py SCRATCH_DIR c518a5 e604d8   # -> check_cli.log"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WARF = HERE.parent.parent
LAYA = HERE.parent / "laya-five"
scratch = Path(sys.argv[1]).resolve()
ids = sys.argv[2:]
exe = os.environ.get("CLAUDE_CODE_EXECPATH")
env = {k: v for k, v in os.environ.items() if not k.upper().startswith("CLAUDE")}
if exe:
    env["PATH"] = str(Path(exe).parent) + os.pathsep + env.get("PATH", "")
env.update(WARF_NO_BROWSER="1", PYTHONIOENCODING="utf-8")
sys.path.insert(0, str(LAYA))

from run_five import INPUT_LABEL, PLAN, prepare  # noqa: E402
from warf.orchestrator import REPLY_FORMAT, VoteRecord, _build_debate_prompt  # noqa: E402

plan = {e["sha"]: e for e in map(json.loads, PLAN.open(encoding="utf-8"))}
selection = {s["id"]: s for s in map(json.loads, (LAYA / "selection.jsonl").open(encoding="utf-8"))}
bad = 0
for i in ids:
    s, home = selection[i], scratch / i
    if (home / "sessions.jsonl").exists():
        sys.exit(f"{home} already holds sessions; use an empty directory")
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "profiles" / "standard_five.json", home / "profiles" / "standard_five.json")
    entry = plan[s["commit"]]
    proc = subprocess.run([sys.executable, "-B", "-m", "warf", "review-commit", s["commit"], "--repo", entry["worktree"],
                           "--debate", "--profile", "standard_five", "--force", "--json", "--debug"],
                          cwd=WARF, env=dict(env, WARF_HOME=str(home)), capture_output=True, text=True,
                          encoding="utf-8", timeout=3600)
    if proc.returncode != 0:
        print(f"  {i}: review-commit failed (rc {proc.returncode}): {proc.stderr[-600:]}")
        bad += 1
        continue
    reviews = json.loads(proc.stdout)["reviews"]
    cli = next(r for r in reviews if r.get("artifact") == f"{s['commit']}:{s['file']}")
    log = next(home.rglob("debug.log")).read_text(encoding="utf-8")
    sent = [log[m.end():m.end() + int(m.group(1))] for m in re.finditer(r"\[INPUT len=(\d+)\]\n", log)]

    code, domain, context, _ = prepare(entry, s["file"])
    ctx = f"Project context:\n{context}\n\n" if context else ""
    round1 = f"Domain: {domain}\n\n{ctx}{INPUT_LABEL}:\n```\n{code}\n```\n\n{REPLY_FORMAT}"
    r1_votes = [VoteRecord(agent_name=v["agent"], vote=v["vote"], omega=v["omega"], reasoning=v["reasoning"])
                for v in cli["votes"]]
    round2 = {f"{_build_debate_prompt(code, domain, r1_votes, agent_name=v.agent_name, context=context)}\n\n{REPLY_FORMAT}"
              for v in r1_votes}
    sent1 = [m for m in sent if "=== Round 1 Summary ===" not in m]
    sent2 = [m for m in sent if "=== Round 1 Summary ===" in m]
    debate = (cli.get("debate") or {}).get("votes") or []
    models = {(v["provider"], v["model"]) for v in cli["votes"] + debate}
    checks = {
        "one file in the commit": len(reviews) == 1,
        f"Round 1, {len(sent1)} messages equal the runner's": bool(sent1) and all(m == round1 for m in sent1),
        f"Round 2, {len(sent2)} messages equal the rebuilt debate prompts": len(sent2) == len(debate)
                                                                            and all(m in round2 for m in sent2),
        "every vote from claude_cli/claude-haiku-4-5-20251001": models == {("claude_cli", "claude-haiku-4-5-20251001")},
    }
    bad += not all(checks.values())
    print(f"  {i} {s['commit'][:9]} {s['file']}: decision {cli['decision']} {cli['confidence']}; "
          + "; ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in checks.items()), flush=True)
print(f"  {len(ids) - bad} of {len(ids)} commits pass")
