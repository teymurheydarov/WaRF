"""Alternative Jev inputs for the 132 dev items (DEV.md 2026-11-09):
- items_commit.jsonl:  the whole commit (message, reviewed file, other files; ../commit_inputs.jsonl), cut at 50,000 chars;
- items_changed.jsonl: the item's diff with the context lines removed (headers, @@ lines, + and - lines kept)."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
items = [json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")]
commit = {json.loads(l)["id"]: json.loads(l)["code"] for l in (HERE.parent / "commit_inputs.jsonl").open(encoding="utf-8")}
def changed(code):
    return "\n".join(l for l in code.splitlines() if not l.startswith(" ") and l != "")
with open(HERE / "items_commit.jsonl", "w", encoding="utf-8") as f:
    for it in items: f.write(json.dumps({**it, "code": commit[it["id"]][:50000]}) + "\n")
with open(HERE / "items_changed.jsonl", "w", encoding="utf-8") as f:
    for it in items: f.write(json.dumps({**it, "code": changed(it["code"])}) + "\n")
print("ok", sum(len(commit[i["id"]]) > 50000 for i in items), "commit inputs cut")
