"""New information for Jev on the RocksDB matched set (development; ../README.md 2026-11-14 section).

One jev-1.14 call per item and state asks WaRF's usual question ("verdict") and the narrow "compile"
check. States:
  plain   WaRF's input, framed as run_narrow frames it (the baseline, same two questions)
  ctx     WaRF's project-context mechanism (warf_context.md, `warf init-context`): the text of
          rocksdb_context.md before the input, as warf.paths.find_context would supply it
  commit  the diffs of all C++ files of the commit (the reviewed file first, 10 lines of context),
          cut at 20 000 characters, instead of the one file
  both    ctx + commit

    python run_ctx.py        # resumes; writes answers.jsonl"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "real-set" / "jev-narrow")); sys.path.insert(0, str(EXP / "rdb-set")); sys.path.insert(0, str(EXP.parent))
import run_narrow as rn  # noqa: E402
import build_rdb as B  # noqa: E402

rn.CHECKS = {"compile": rn.CHECKS["compile"]}
CTX = (HERE / "rocksdb_context.md").read_text(encoding="utf-8").strip()
OUT = HERE / "answers.jsonl"
MAX = 20000


def commit_diff(it):
    files = [f for f in B.git(B.GD, "show", "--format=", "--name-only", it["commit"]).split() if f.endswith(B.CPP)]
    files = [it["file"]] + [f for f in files if f != it["file"]]
    parts = []
    for f in files:
        try:
            parts.append(B.git(B.GD, "show", "--format=", "-U10", "--no-color", it["commit"], "--", f))
        except Exception:
            continue
    text = "\n".join(p for p in parts if p.strip())
    return text[:MAX]


def states(it):
    plain = rn.frame(it["domain"], it["code"])
    cd = commit_diff(it)
    whole = rn.frame(it["domain"], cd)
    pre = f"Project context:\n{CTX}\n\n"
    return {"plain": plain, "ctx": pre + plain, "commit": whole, "both": pre + whole}


def main():
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    items = [json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")]
    done = {(json.loads(l)["id"], json.loads(l)["state"]) for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    jobs = [(it["id"], s, st) for it in items for s, st in states(it).items() if (it["id"], s) not in done]
    print(f"{len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(job):
        i, s, st = job
        try:
            b = rn.ask(st, base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1; print(f"  error {i} {s}: {e}", flush=True)
            return
        ans = {q: {"choice": v.get("choice"), "p": v.get("probabilities")} for q, v in (b.get("answers") or {}).items()}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": i, "state": s, "chars": len(st), "model": b.get("model"), "answers": ans,
                                    "usage": b.get("usage")}) + "\n")

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(run, jobs))
    print(f"done; cost ${cost[0]:.4f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
