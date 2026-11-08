"""DEVELOPMENT: inputs for a checker seat (the finder + checker idea, DEV.md). For every item the finder
(the claude-commit arm: one Claude, the sweep's question, whole commit) rejected, the checker is shown
the same whole-commit input followed by the finder's objection (its reply text, vote word removed).
Items the finder approved get no checker call; the panel approves them.

    python .warf-experiments/real-set/build_verify_inputs.py     # writes verify_inputs.jsonl"""
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

whole = {r["id"]: r["code"] for r in map(json.loads, (HERE / "commit_inputs.jsonl").open(encoding="utf-8"))}
finder = {}
for f in glob.glob(str(HERE / "claude-commit.w*.jsonl")):
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        finder[r["planted"]["id"]] = r
n = 0
with (HERE / "verify_inputs.jsonl").open("w", encoding="utf-8") as out:
    for i, r in sorted(finder.items()):
        if r["decision"] != "REJECT":
            continue
        objection = r["votes"][0]["reasoning"].strip()
        code = f"{whole[i]}\n\n=== An objection another reviewer raised against this change ===\n{objection}"
        out.write(json.dumps({"id": i, "code": code}, ensure_ascii=False) + "\n")
        n += 1
print(f"{n} checker inputs (items the finder rejected) of {len(finder)}")
