"""Jev with a project defect profile learned from labelled history (development, RocksDB matched set).

The profile (defect_profile.md) was written by a fresh agent from the 37 confirmed RocksDB defects that
are NOT among the 800 test items (history_defects.md). It is the same text for every item, so it cannot
carry anything item-specific. States (jev-1.14; questions: verdict and compile, as ../context/run_ctx.py):
  prof      profile + WaRF's input
  prof_ctx  profile + the build context of ../context/rocksdb_context.md + WaRF's input

    python run_hist.py        # resumes; writes answers.jsonl"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
import run_narrow as rn  # noqa: E402

rn.CHECKS = {"compile": rn.CHECKS["compile"]}
PROFILE = (HERE / "defect_profile.md").read_text(encoding="utf-8").strip()
CTX = (HERE.parent / "context" / "rocksdb_context.md").read_text(encoding="utf-8").strip()
OUT = HERE / "answers.jsonl"


def states(it):
    plain = rn.frame(it["domain"], it["code"])
    prof = f"Defects found in this project's past changes (from labelled reviews):\n{PROFILE}\n\n"
    return {"prof": prof + plain, "prof_ctx": prof + f"Project context:\n{CTX}\n\n" + plain}


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
