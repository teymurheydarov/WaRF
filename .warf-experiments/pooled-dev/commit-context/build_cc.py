"""The commit context of every frozen DuckDB and PPSSPP item, built with WaRF's own code (warf.vcs.get_diff with
3 lines, warf.cli._parse_diff, warf.commit_context.commit_context), as `review-commit --commit-context` builds it.
Git only, no model calls. The clones are partial (no blobs until needed) and are deleted after the test.

    python build_cc.py      # writes cc_ddb.jsonl, cc_pp.jsonl, build_cc.log"""
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf.cli import _parse_diff  # noqa: E402
from warf.commit_context import COMMIT_CONTEXT_CHARS, commit_context  # noqa: E402
from warf.vcs import get_diff  # noqa: E402

SETS = {"ddb": (EXP / "ddb-set" / "items.jsonl", r"C:\workdir\warf\repos\duckdb"),
        "pp": (EXP / "pp-set" / "items.jsonl", r"C:\workdir\warf\repos\ppsspp")}
log = []


def say(s=""):
    log.append(s); print(s, flush=True)


for name, (items_path, repo) in SETS.items():
    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]
    shas = sorted({it["commit"] for it in items})
    with ThreadPoolExecutor(6) as ex:
        patches = dict(zip(shas, ex.map(lambda s: _parse_diff(get_diff(repo, s, 3)), shas)))
    rows = []
    for it in items:
        p = patches[it["commit"]]
        if it["file"] not in {f for f, _ in p}:
            raise SystemExit(f"{it['id']}: {it['file']} is not in its commit's diff")
        cc = commit_context(p, it["file"])
        rows.append({"id": it["id"], "kind": it["kind"], "n_other": len(p) - 1, "chars": len(cc or ""),
                     "cut": bool(cc and "[... rest of this file's diff cut ...]" in cc),
                     "named": bool(cc and "Also changed (diff not shown):" in cc), "commit_context": cc})
    with (HERE / f"cc_{name}.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    say(f"\n{name}: {len(items)} items from {len(shas)} commits (budget {COMMIT_CONTEXT_CHARS} characters)")
    for kind in ("defective", "clean"):
        k = [r for r in rows if r["kind"] == kind]
        w = [r for r in k if r["commit_context"]]
        say(f"  {kind:<9} with other files {len(w)}/{len(k)}; other files median "
            f"{statistics.median(r['n_other'] for r in k)}; context chars median (when present) "
            f"{statistics.median(r['chars'] for r in w) if w else 0:.0f}; cut {sum(r['cut'] for r in k)}, "
            f"files only named {sum(r['named'] for r in k)}")
(HERE / "build_cc.log").write_text("\n".join(log) + "\n", encoding="utf-8")
