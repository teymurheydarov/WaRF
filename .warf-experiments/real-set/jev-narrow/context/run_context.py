"""Lever "context": ask Jev the frozen questions (run_narrow.questions(): verdict + 7 checks) on the whole change
plus the retrieved "Related code" block (context_items.jsonl, from build_context.py). No hunks.

    state = run_narrow.frame(domain, code) + "\n\nRelated code from the same revision:\n" + block

    python run_context.py [--limit N] [--workers 4]   # resumes; appends answers_context.jsonl

Needs TYPESAFE_API_KEY and TYPESAFE_BASE_URL in the environment; the key is never printed or stored."""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_narrow as rn  # noqa: E402

OUT = HERE / "answers_context.jsonl"


def state_of(it, block):
    return rn.frame(it["domain"], it["code"]) + "\n\nRelated code from the same revision:\n" + block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    items = [json.loads(l) for l in rn.ITEMS.open(encoding="utf-8")]
    blocks = {r["id"]: r["block"] for r in map(json.loads, (HERE / "context_items.jsonl").open(encoding="utf-8"))}
    if a.limit:
        items = items[:a.limit]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.open(encoding="utf-8")}
    jobs = [it for it in items if it["id"] not in done]
    print(f"{len(items)} items, {len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(it):
        state = state_of(it, blocks[it["id"]])
        try:
            b = rn.ask(state, base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1
                print(f"  error {it['id']}: {e}", flush=True)
            return
        ans = {q: {"choice": v.get("choice"), "p": v.get("probabilities")} for q, v in (b.get("answers") or {}).items()}
        rec = {"id": it["id"], "state": "whole", "hunk": 0, "chars": len(state), "model": b.get("model"),
               "answers": ans, "usage": b.get("usage")}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(min(4, a.workers)) as ex:
        list(ex.map(run, jobs))
    print(f"done; cost this run ${cost[0]:.6f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
