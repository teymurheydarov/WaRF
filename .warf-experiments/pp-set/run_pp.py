"""Jev through WaRF on the frozen PPSSPP set (README.md "The arms"): every seat of both arms in one run_review per
change, so the shared BOUNDARY seat is asked once. Seats: SKEPTIC, ADVOCATE, AUDITOR (jev-1.14), TEST-FOCUSED,
BOUNDARY (jev-1.13), LOCATE, CHECKLIST, DEFAULT (jev-1.14). aggregate logodds, every seat asked, an empty
calibration log (calibration happens in score_pp.py, from the other folds), the project context
(pp_context.md + the defect profile), WARF_HOME a scratch folder.

    python run_pp.py [--limit N]      # resumes; writes sessions.jsonl"""
import argparse
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-pp-")
HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent)); sys.path.insert(0, str(HERE))
sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned"))
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import save_profiles  # noqa: E402
from run_learned import INPUT_LABEL  # noqa: E402
import panel  # noqa: E402

OUT = HERE / "sessions.jsonl"
CONTEXT = ((HERE / "pp_context.md").read_text(encoding="utf-8").strip()
           + "\n\nDefects found in this project's past changes (from labelled reviews):\n"
           + (HERE / "defect_profile.md").read_text(encoding="utf-8").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    seats = panel.personas() + panel.question_seats()
    prof = HERE / "panel_all.json"
    save_profiles(prof, seats)
    empty = Path(tempfile.mkdtemp()) / "empty.jsonl"
    items = [json.loads(l) for l in (HERE / "items.jsonl").open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = {json.loads(l)["artifact"] for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"{len(todo)} changes to review ({len(done)} done)", flush=True)
    lock, tokens, errs, n = threading.Lock(), [0], [0], [0]

    def review(it):
        try:
            r = run_review(it["code"], it["domain"], prof, verbose=False, input_label=INPUT_LABEL, context=CONTEXT,
                           aggregate="logodds", log_path=empty, no_early_stop=True)
        except Exception as exc:          # noqa: BLE001  (reported and counted; retried on resume)
            with lock:
                errs[0] += 1; print(f"  error {it['id']}: {str(exc)[:200]}", flush=True)
            return
        rec = session_dict(r, it["id"])
        rec["artifact"], rec["kind"] = it["id"], it["kind"]
        with lock:
            tokens[0] += sum(v.tokens_in for v in r.votes); n[0] += 1
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if n[0] % 100 == 0:
                print(f"  {n[0]}/{len(todo)}  input tokens {tokens[0]}", flush=True)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(review, todo))
    print(f"done: {n[0]} reviews, input tokens {tokens[0]} (about ${tokens[0] * 4.2e-8:.2f}), errors {errs[0]}",
          flush=True)


if __name__ == "__main__":
    main()
