"""Lever "beforeafter": ask the frozen questions (run_narrow.questions(): verdict + 7 generic checks) once per
item on the JSON state {task, domain, file, code_before, code_after} built by build_states.py.

    python run_beforeafter.py [--limit N]     # resumes; appends answers_beforeafter.jsonl

Needs TYPESAFE_API_KEY and TYPESAFE_BASE_URL; the key is never printed or stored."""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_narrow  # noqa: E402  (ask, questions, MODEL; import has no side effects)

STATES = HERE / "states.jsonl"
OUT = HERE / "answers_beforeafter.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    rows = [json.loads(l) for l in STATES.open(encoding="utf-8")]
    if a.limit:
        rows = rows[:a.limit]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.open(encoding="utf-8")}
    jobs = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} items, {len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(r):
        try:
            b = run_narrow.ask(r["state"], base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1
                print(f"  error {r['id']}: {e}", flush=True)
            return
        ans = {q: {"choice": v.get("choice"), "p": v.get("probabilities")} for q, v in (b.get("answers") or {}).items()}
        rec = {"id": r["id"], "state": "whole", "hunk": 0, "chars": len(json.dumps(r["state"])),
               "model": b.get("model"), "answers": ans, "usage": b.get("usage")}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(min(4, a.workers)) as ex:
        list(ex.map(run, jobs))
    total = sum(float((json.loads(l).get("usage") or {}).get("cost") or 0) for l in OUT.open(encoding="utf-8")) if OUT.exists() else 0
    print(f"done; cost this run ${cost[0]:.4f}, file total ${total:.4f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
