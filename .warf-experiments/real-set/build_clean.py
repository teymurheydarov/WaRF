"""Clean controls for the real-defect set, screened without Claude before any reviewer runs.

A control is a change to a C++ file under src/ (gismo6 clone, origin/dev) whose added non-blank lines are
all still attributed to its commit by `git blame origin/dev` (../hard-set/build_hard.py survives()), so
nothing it added was later changed or fixed. Commits reviewed in ../laya-five, ../evidence-set or
../hard-set, and the defective candidates' commits, are excluded; one file per commit; at most MAX_CHARS.
Committed 2014-01-01 .. 2026-04-01 (at least six months of later history), like the defects' range.

    python .warf-experiments/real-set/build_clean.py     # writes clean_pool.jsonl"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "evidence-set"))
sys.path.insert(0, str(EXP / "hard-set"))
from build_set import GISMO, git, prepare  # noqa: E402
from build_hard import survives  # noqa: E402

MAX_CHARS = 20000
N_POOL = 200


def main() -> None:
    used = set()
    for path in (EXP / "laya-five" / "selection.jsonl", EXP / "evidence-set" / "candidates.jsonl",
                 EXP / "hard-set" / "candidates.jsonl", HERE / "candidates.jsonl"):
        used |= {json.loads(line)["commit"] for line in path.open(encoding="utf-8")}
    commits = git(str(GISMO / ".git"), "log", "origin/dev", "--no-merges", "--since=2014-01-01", "--until=2026-04-01",
                  "--format=%H%x09%ad%x09%s", "--date=short", "--", "src/*.h", "src/*.hpp", "src/*.cpp").splitlines()
    rng = random.Random(20261105 + 1)
    rng.shuffle(commits)
    base = {"git_dir": str(GISMO / ".git"), "worktree": str(GISMO)}
    pool = []
    for row in commits:
        if len(pool) == N_POOL:
            break
        sha, date, subject = row.split("\t", 2)
        if sha in used or subject.startswith(("Revert", "Merge")):
            continue
        files = [f for f in git(str(GISMO / ".git"), "show", "--format=", "--name-only", "--diff-filter=AM", sha).split()
                 if f.startswith("src/") and f.endswith((".h", ".hpp", ".cpp"))]
        rng.shuffle(files)
        for f in files:
            code, domain, context, enrich_error = prepare({**base, "sha": sha}, f)
            if len(code) > MAX_CHARS or not any(ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()
                                                for ln in code.splitlines()):
                continue
            if survives(sha, f, code):
                pool.append({"base": f"{sha[:7]}:{Path(f).name}", "commit": sha, "date": date, "subject": subject,
                             "file": f, "domain": domain, "context": context, "enrich_error": enrich_error, "code": code})
                break
    with (HERE / "clean_pool.jsonl").open("w", encoding="utf-8") as out:
        for p in pool:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
    years = {}
    for p in pool:
        years[p["date"][:4]] = years.get(p["date"][:4], 0) + 1
    print(f"clean pool: {len(pool)}; years: " + ", ".join(f"{y} {n}" for y, n in sorted(years.items())))


if __name__ == "__main__":
    main()
