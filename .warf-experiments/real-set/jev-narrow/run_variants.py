"""Jev request variants on the 132 dev items, whole state only (development, ../DEV.md 2026-11-09).

Jev's /v1/systemone contract has three question types (choice, score, noul) and takes a state as text,
JSON object or turn list; it has no field for examples. Variants, each asking the verdict and the seven
narrow checks of run_narrow.py:
- noul:    every question as a noul (binary, returns P(true));
- score:   the verdict as a 0..4 severity score;
- json:    the state as a JSON object {domain, file, diff} instead of framed text;
- fewshot: a JSON state holding four labelled dev examples (FEWSHOT_IDS, excluded from scoring) and the
           change under review.

    python .warf-experiments/real-set/jev-narrow/run_variants.py --variant noul|score|json|fewshot
Writes answers_<variant>.jsonl (resumes). The API key is never printed or stored."""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_narrow import CHECKS, DEFAULT_PERSONA, VERDICT, YESNO, ask, frame  # noqa: E402

HERE = Path(__file__).resolve().parent
ITEMS = HERE.parent / "items.jsonl"
FEWSHOT_IDS = []          # filled from fewshot.json (built by pick_fewshot below)
SEVERITY = ["0: no problem at all", "1: style or cosmetic issue only", "2: minor issue, safe to merge",
            "3: likely defect, should be fixed before merging", "4: certain defect that breaks behaviour"]


def questions(variant):
    if variant == "noul":
        q = {"verdict": {"type": "noul", "instructions": DEFAULT_PERSONA + " True if it must be rejected.",
                         "criteria": {"false": VERDICT["APPROVE"], "true": VERDICT["REJECT"]}}}
        for k, t in CHECKS.items():
            q[k] = {"type": "noul", "instructions": t,
                    "criteria": {"false": YESNO["NO"], "true": YESNO["YES"]}}
        return q
    q = {"verdict": {"type": "choice", "instructions": DEFAULT_PERSONA, "criteria": VERDICT}}
    if variant == "score":
        q["severity"] = {"type": "score", "instructions": "How severe is the worst problem the change introduces?",
                         "criteria": SEVERITY}
    for k, t in CHECKS.items():
        q[k] = {"type": "choice", "instructions": t, "criteria": YESNO}
    return q


def state(variant, it, shots):
    if variant in ("noul", "score"):
        return frame(it["domain"], it["code"])
    obj = {"domain": it["domain"], "file": it["file"], "diff": it["code"]}
    if variant == "json":
        return obj
    return {"task": "Review the change under review. The labelled examples are earlier changes of the same "
                    "repository with their known outcome.",
            "labelled_examples": shots, "change_under_review": obj}


def pick_fewshot(items):
    """Two defective and two clean dev items, the shortest whose defect is visible in the diff."""
    path = HERE / "fewshot.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    dfx = sorted((i for i in items if i["kind"] == "defective" and i.get("visible") == "diff"), key=lambda i: len(i["code"]))[:2]
    cln = sorted((i for i in items if i["kind"] == "clean"), key=lambda i: len(i["code"]))[:2]
    shots = []
    for it in (dfx[0], cln[0], dfx[1], cln[1]):
        d = it.get("defect")
        reason = (d[0] if isinstance(d, list) else d) if it["kind"] == "defective" else "No defect; the change was never fixed."
        shots.append({"id": it["id"], "file": it["file"], "diff": it["code"],
                      "outcome": "REJECT" if it["kind"] == "defective" else "APPROVE", "reason": reason})
    path.write_text(json.dumps(shots, indent=1), encoding="utf-8")
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=["noul", "score", "json", "fewshot"])
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    shots = pick_fewshot(items) if a.variant == "fewshot" else []
    shot_ids = {s["id"] for s in shots}
    shots_wire = [{k: v for k, v in s.items() if k != "id"} for s in shots]
    out = HERE / f"answers_{a.variant}.jsonl"
    done = {json.loads(l)["id"] for l in out.open(encoding="utf-8")} if out.exists() else set()
    todo = [it for it in items if it["id"] not in done and it["id"] not in shot_ids]
    print(f"{a.variant}: {len(todo)} calls to make ({len(done)} done, {len(shot_ids)} examples excluded)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]
    import run_narrow
    q = questions(a.variant)

    def run(it):
        run_narrow.questions = lambda: q          # ask() sends run_narrow.questions()
        try:
            b = ask(state(a.variant, it, shots_wire), base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1; print(f"  error {it['id']}: {e}", flush=True)
            return
        rec = {"id": it["id"], "variant": a.variant, "model": b.get("model"), "answers": b.get("answers"), "usage": b.get("usage")}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, todo))
    print(f"done; cost ${cost[0]:.4f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
