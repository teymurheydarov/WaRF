"""Jev through WaRF with commit context (README.md "The test"): PANEL3's three seats on every DuckDB and PPSSPP item
that has other files in its commit, with each set's own context exactly as its fresh run had it
(../../ddb-set/run_ddb.py, ../../pp-set/run_pp.py) plus the commit context from build_cc.py. logodds, every seat
asked, an empty calibration log (calibration happens in score_cc.py), WARF_HOME a scratch folder.

    python run_cc.py [--limit N]      # resumes; writes sessions_cc_ddb.jsonl, sessions_cc_pp.jsonl"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-cc-")
HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
sys.path.insert(0, str(EXP / "confirm-set" / "jev-learned"))
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import save_profiles  # noqa: E402
from run_learned import INPUT_LABEL  # noqa: E402

SETS = {"ddb": (EXP / "ddb-set", "ddb_context.md"), "pp": (EXP / "pp-set", "pp_context.md")}


def load_panel(set_dir):
    spec = importlib.util.spec_from_file_location(f"panel_{set_dir.name}", set_dir / "panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def context(set_dir, ctx_name):
    return ((set_dir / ctx_name).read_text(encoding="utf-8").strip()
            + "\n\nDefects found in this project's past changes (from labelled reviews):\n"
            + (set_dir / "defect_profile.md").read_text(encoding="utf-8").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set")
    lock, tokens, errs, n = threading.Lock(), [0], [0], [0]
    for name, (set_dir, ctx_name) in SETS.items():
        seats = load_panel(set_dir).panel3()
        prof = HERE / f"panel3_{name}.json"
        save_profiles(prof, seats)
        ctx = context(set_dir, ctx_name)
        empty = Path(tempfile.mkdtemp()) / "empty.jsonl"
        items = {json.loads(l)["id"]: json.loads(l) for l in (set_dir / "items.jsonl").open(encoding="utf-8")}
        cc = [json.loads(l) for l in (HERE / f"cc_{name}.jsonl").open(encoding="utf-8")]
        cc = [r for r in cc if r["commit_context"]]
        if a.limit:
            cc = cc[:a.limit]
        out = HERE / f"sessions_cc_{name}.jsonl"
        done = {json.loads(l)["artifact"] for l in out.open(encoding="utf-8")} if out.exists() else set()
        todo = [r for r in cc if r["id"] not in done]
        print(f"{name}: {len(todo)} changes to review ({len(done)} done)", flush=True)

        def review(r):
            it = items[r["id"]]
            try:
                res = run_review(it["code"], it["domain"], prof, verbose=False, input_label=INPUT_LABEL, context=ctx,
                                 commit_context=r["commit_context"], aggregate="logodds", log_path=empty,
                                 no_early_stop=True)
            except Exception as exc:          # noqa: BLE001  (reported and counted; retried on resume)
                with lock:
                    errs[0] += 1; print(f"  error {r['id']}: {str(exc)[:200]}", flush=True)
                return
            rec = session_dict(res, r["id"])
            rec["artifact"], rec["kind"] = r["id"], it["kind"]
            with lock:
                tokens[0] += sum(v.tokens_in for v in res.votes); n[0] += 1
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if n[0] % 100 == 0:
                    print(f"  {n[0]} reviews, input tokens {tokens[0]}", flush=True)

        with ThreadPoolExecutor(6) as ex:
            list(ex.map(review, todo))
    print(f"done: {n[0]} reviews, input tokens {tokens[0]}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
