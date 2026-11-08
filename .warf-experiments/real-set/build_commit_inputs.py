"""Whole-commit inputs for the 132 items of items.jsonl (ADR 0002's whole-commit reader).

Each input is a superset of the single-file view every other arm got:
  1. the commit message (subject and body);
  2. the item's own `code`, unchanged (its diff with 30 context lines and the enclosing function bodies);
  3. the diffs of every OTHER file the commit touched (`git show -U10`), so declarations, callers,
     build files and companion .h/.hpp/.cpp of the same commit are visible.
Nothing later than the commit is included. Part 3 is cut at MAX_OTHER characters (counted and logged).

    python .warf-experiments/real-set/build_commit_inputs.py     # writes commit_inputs.jsonl"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "evidence-set"))
from build_set import GISMO, git  # noqa: E402

MAX_OTHER = 60000
INPUT_LABEL = "Commit under review: its message, the reviewed file's diff, then the commit's other files"


def main() -> None:
    items = [json.loads(line) for line in (HERE / "items.jsonl").open(encoding="utf-8")]
    gd = str(GISMO / ".git")
    cut, sizes = 0, []
    with (HERE / "commit_inputs.jsonl").open("w", encoding="utf-8") as out:
        for it in items:
            message = git(gd, "show", "-s", "--format=%s%n%n%b", it["commit"]).strip()
            files = [f for f in git(gd, "show", "--format=", "--name-only", it["commit"]).split() if f != it["file"]]
            other = (git(gd, "show", "-U10", "--no-color", "--format=", it["commit"], "--", ".",
                         f":(exclude){it['file']}") if files else "")
            if len(other) > MAX_OTHER:
                other = other[:MAX_OTHER] + "\n[... the remaining diff of the other files is cut ...]"
                cut += 1
            code = (f"Commit message:\n{message}\n\n=== The reviewed file ({it['file']}) ===\n{it['code']}\n\n"
                    f"=== The commit's other files ({len(files)}) ===\n{other or '(none)'}")
            sizes.append(len(code))
            out.write(json.dumps({"id": it["id"], "other_files": len(files), "code": code}, ensure_ascii=False) + "\n")
    sizes.sort()
    print(f"{len(items)} inputs; median {sizes[len(sizes) // 2]} chars, max {sizes[-1]}; other files cut in {cut}")


if __name__ == "__main__":
    main()
