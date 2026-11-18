"""The question seats of the five-seat panel, live through WaRF's run_review on the 800 RocksDB changes.

Seats (profile panel_live.json), every one with the project context of ../history/run_lo_ctx.py, as WaRF
shows it to all seats:
  DEFAULT       jev-1.14  WaRF's default question (run_narrow.DEFAULT_PERSONA)
  LOCATE        jev-1.14  question "locate", build + runtime (../locate/run_locate.py) in one call
  CHECKLIST     jev-1.14  question "check", the seven project checks (../history/run_checks.py) in one call
  LOCATE-13     jev-1.13  the same as LOCATE
  CHECKLIST-13  jev-1.13  the same as CHECKLIST
The persona seats SKEPTIC and BOUNDARY come from the WaRF run ../history/sessions_LO_ctx.jsonl (same context,
same input label). Calibration log: empty (the answers are recorded; calibration happens in replay_live.py).
WARF_HOME is a scratch folder, so nothing reaches the repository's .warf/.

    python run_live.py [--limit N]      # resumes; writes sessions_live.jsonl"""
import argparse
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-live-")
HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
sys.path.insert(0, str(HERE.parent / "history")); sys.path.insert(0, str(HERE.parent / "locate"))
sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned"))
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import AgentProfile, persona_hash, save_profiles  # noqa: E402
from run_checks import rn  # noqa: E402
from run_locate import LOCATE  # noqa: E402
from run_lo_ctx import CONTEXT  # noqa: E402
from run_learned import INPUT_LABEL  # noqa: E402

OUT = HERE / "sessions_live.jsonl"


def seat(name, persona, model, question=None):
    return AgentProfile(name=name, persona=persona, provider="jev", model=model, persona_hash=persona_hash(persona),
                        question=question)


SEATS = [seat("DEFAULT", rn.DEFAULT_PERSONA, "jev-1.14"),
         seat("LOCATE", "\n".join(LOCATE.values()), "jev-1.14", "locate"),
         seat("CHECKLIST", "\n".join(rn.CHECKS.values()), "jev-1.14", "check"),
         seat("LOCATE-13", "\n".join(LOCATE.values()), "jev-1.13", "locate"),
         seat("CHECKLIST-13", "\n".join(rn.CHECKS.values()), "jev-1.13", "check")]
PANEL = HERE / "panel_live.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    save_profiles(PANEL, SEATS)
    empty = Path(tempfile.mkdtemp()) / "empty.jsonl"
    items = [json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = {json.loads(l)["artifact"] for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"{len(todo)} changes to review ({len(done)} done)", flush=True)
    lock, tokens, errs, n = threading.Lock(), [0], [0], [0]

    def review(it):
        try:
            # no redirect_stdout: it swaps sys.stdout for every thread and swallowed the progress lines
            r = run_review(it["code"], it["domain"], PANEL, verbose=False, input_label=INPUT_LABEL,
                           context=CONTEXT, aggregate="logodds", log_path=empty, no_early_stop=True)
        except Exception as exc:          # noqa: BLE001  (reported and counted; the change is retried on resume)
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
