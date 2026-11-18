"""Jev with retrieved declarations (decl_items.jsonl) on the RocksDB matched set (development).

One jev-1.14 call per item and state asks WaRF's usual question and the seven project-learned checks of
../history/run_checks.py, on the whole change. States:
  decl      WaRF's input + "Related code from the same revision:" + the declaration block
  decl_ctx  the project context of ../history/run_lo_ctx.py (build rules + defect profile) + decl

    python run_decl.py      # resumes; writes answers.jsonl"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "history"))
from run_checks import rn  # noqa: E402  (run_narrow with the project-learned CHECKS)
from run_lo_ctx import CONTEXT  # noqa: E402

OUT = HERE / "answers.jsonl"


def main():
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    items = [json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")]
    block = {json.loads(l)["id"]: json.loads(l)["block"] for l in (HERE / "decl_items.jsonl").open(encoding="utf-8")}
    done = {(json.loads(l)["id"], json.loads(l)["state"]) for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    jobs = []
    for it in items:
        decl = rn.frame(it["domain"], it["code"]) + "\n\nRelated code from the same revision:\n" + block[it["id"]]
        for s, st in (("decl", decl), ("decl_ctx", f"Project context:\n{CONTEXT}\n\n" + decl)):
            if (it["id"], s) not in done:
                jobs.append((it["id"], s, st))
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
