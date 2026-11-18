"""A fourth seat shown retrieved declarations, live through WaRF's run_review on one project (development).

DECL: WaRF's default question (run_narrow.DEFAULT_PERSONA) on jev-1.14, evidence source "declarations"
(ADR 0002): its input is the change followed by "Related code from the same revision:" and the item's
declaration block (RocksDB ../decl/decl_items.jsonl, DuckDB ../../ddb-set/decl/decl_items.jsonl). The project
context is the one every seat of that project saw. Calibration log empty (calibration happens in cross.py).
WARF_HOME is a scratch folder.

    python run_decl_seat.py rdb|ddb [--limit N]      # resumes; writes decl_<project>.jsonl"""
import argparse
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-decl-")
HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned")); sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import AgentProfile, persona_hash, save_profiles  # noqa: E402
from run_learned import INPUT_LABEL  # noqa: E402
from run_narrow import DEFAULT_PERSONA  # noqa: E402


def project(name):
    if name == "rdb":
        sys.path.insert(0, str(HERE.parent / "history"))
        from run_lo_ctx import CONTEXT
        return EXP / "rdb-set" / "items.jsonl", HERE.parent / "decl" / "decl_items.jsonl", CONTEXT
    d = EXP / "ddb-set"
    ctx = ((d / "ddb_context.md").read_text(encoding="utf-8").strip()
           + "\n\nDefects found in this project's past changes (from labelled reviews):\n"
           + (d / "defect_profile.md").read_text(encoding="utf-8").strip())
    return d / "items.jsonl", d / "decl" / "decl_items.jsonl", ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", choices=("rdb", "ddb"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    items_path, decl_path, context = project(a.project)
    block = {json.loads(l)["id"]: json.loads(l)["block"] for l in decl_path.open(encoding="utf-8")}
    seat = AgentProfile(name="DECL", persona=DEFAULT_PERSONA, provider="jev", model="jev-1.14",
                        persona_hash=persona_hash(DEFAULT_PERSONA), evidence="declarations")
    prof = HERE / f"panel_decl_{a.project}.json"
    save_profiles(prof, [seat])
    empty = Path(tempfile.mkdtemp()) / "empty.jsonl"
    out = HERE / f"decl_{a.project}.jsonl"
    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = {json.loads(l)["artifact"] for l in out.open(encoding="utf-8")} if out.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"{len(todo)} changes to review ({len(done)} done)", flush=True)
    lock, tokens, errs = threading.Lock(), [0], [0]

    def review(it):
        inputs = {"declarations": it["code"] + "\n\nRelated code from the same revision:\n" + block[it["id"]]}
        try:
            r = run_review(it["code"], it["domain"], prof, verbose=False, input_label=INPUT_LABEL, context=context,
                           aggregate="logodds", log_path=empty, no_early_stop=True, seat_inputs=inputs)
        except Exception as exc:          # noqa: BLE001  (reported and counted; retried on resume)
            with lock:
                errs[0] += 1; print(f"  error {it['id']}: {str(exc)[:200]}", flush=True)
            return
        rec = session_dict(r, it["id"])
        rec["artifact"], rec["kind"] = it["id"], it["kind"]
        with lock:
            tokens[0] += sum(v.tokens_in for v in r.votes)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(review, todo))
    print(f"done; input tokens {tokens[0]} (about ${tokens[0] * 4.2e-8:.2f}), errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
