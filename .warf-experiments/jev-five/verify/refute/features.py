"""Per-commit features of the 100 selected changes, read-only from git and the experiment files.
Writes features.jsonl here.

Raw patch: run_five.file_patch (the sweep's `git show -U30`, review-commit's split).
Dates: plan.jsonl (author date as the sweep recorded it) and git's committer date.
Fixes: labels.jsonl rows of the (commit, file) -> fix commits and their dates.
Public: reachable from a refs/remotes/origin/* ref of the gismo6 clone (github.com/gismo/gismo)."""
import json
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
EXP = Path(r"C:\workdir\warf\WaRF\.warf-experiments")
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import PLAN, file_patch  # noqa: E402

GIT_DIR = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"


def git(*args):
    r = subprocess.run(["git", f"--git-dir={GIT_DIR}", *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip(), r.returncode


sel = [json.loads(line) for line in (EXP / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
want = {s["commit"] for s in sel}
plan = {}
for line in PLAN.open(encoding="utf-8"):
    e = json.loads(line)
    if e["sha"] in want:
        plan[e["sha"]] = e
labels = {}
for line in (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    if e["commit"] in want:
        labels[(e["commit"], e["file"])] = e
states = {}
for line in (OUT / "states.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    states[e["id"]] = e

SEP = "\n\n" + "─" * 60 + "\n"
rows = []
for s in sel:
    entry = plan[s["commit"]]
    patch = file_patch(entry, s["file"])
    head, _, body = patch.partition("\n@@")
    body = "@@" + body
    lines = body.splitlines()
    added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
    removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
    hunks = sum(1 for l in lines if l.startswith("@@"))
    new_file = bool(re.search(r"^new file mode", head, re.M)) or "--- /dev/null" in patch
    deleted_file = bool(re.search(r"^deleted file mode", head, re.M)) or "+++ /dev/null" in patch
    status = "new" if new_file else "deleted" if deleted_file else ("deletion-only" if not added else "modified")
    path = s["file"]
    low = path.lower()
    ext = Path(path).suffix.lower()
    test_or_example = bool(re.search(r"(^|/)(unittests?|tests?|examples?|tutorials?|benchmarks?)(/|$)|_test\.|test_|_example|example_", low))
    nonblank_added = [l for l in added if l.strip()]
    comment_re = re.compile(r"^\s*(#)") if ext == ".py" else re.compile(r"^\s*(//|/\*|\*|\*/)")
    comment_only = bool(added or removed) and all(comment_re.match(l) or not l.strip() for l in added + removed)
    st = states[s["id"]]
    enriched = SEP in st["code"]
    lab = labels.get((s["commit"], s["file"]))
    fixes = (lab or {}).get("fixes") or []
    fix_shas = sorted({f if isinstance(f, str) else (f.get("fix") or f.get("sha") or f.get("commit")) for f in fixes} - {None})
    fix_dates = []
    for f in fix_shas:
        d, rc = git("log", "-1", "--format=%cI", f)
        if rc == 0 and d:
            fix_dates.append(d)
    cdate, _ = git("log", "-1", "--format=%cI", s["commit"])
    adate, _ = git("log", "-1", "--format=%aI", s["commit"])
    author, _ = git("log", "-1", "--format=%an", s["commit"])
    subject, _ = git("log", "-1", "--format=%s", s["commit"])
    remote, _ = git("for-each-ref", "--contains", s["commit"], "--count=1", "--format=%(refname)", "refs/remotes/origin")
    rows.append({
        "id": s["id"], "commit": s["commit"], "file": path, "label": s["label"], "domain": s["domain"],
        "patch_chars": s["patch_chars"], "state_tokens": s["state_tokens"],
        "raw_patch_chars": len(patch), "state_chars": len(st["state"]),
        "status": status, "new_file": new_file, "deleted_file": deleted_file,
        "deletion_only": not added, "addition_only": not removed,
        "ext": ext, "header": ext in (".h", ".hpp", ".hh", ".hxx"),
        "top": path.split("/")[0], "extensions_dir": path.startswith("extensions/"),
        "test_or_example": test_or_example,
        "hunks": hunks, "added": len(added), "removed": len(removed), "nonblank_added": len(nonblank_added),
        "comment_only": comment_only, "enriched": enriched,
        "plan_date": entry["date"], "commit_date": cdate, "author_date": adate,
        "author": author, "subject": subject, "files_in_commit": entry["files"],
        "also_in": entry["also_in"], "public": bool(remote), "public_ref": remote,
        "fixes": fix_shas, "fix_dates": fix_dates, "label_reason": (lab or {}).get("reason"),
        "labels_label": (lab or {}).get("label"), "labels_repo": (lab or {}).get("repo"),
        "fix_kinds": [f.get("kind") for f in fixes if isinstance(f, dict)],
        "fix_days": [f.get("days") for f in fixes if isinstance(f, dict)],
        "later_days": (lab or {}).get("later_days"), "blamed_lines": (lab or {}).get("blamed_lines"),
    })

with (OUT / "features.jsonl").open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows), "rows")
