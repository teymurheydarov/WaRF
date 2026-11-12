"""Jev with narrow questions, on the whole change and per hunk (development, ../DEV.md 2026-11-09).

One System One call per state asks the original WaRF question ("verdict", DEFAULT_PERSONA) and seven
narrow checks. Each check is a YES/NO choice. States:
- whole: the item's code, framed as WaRF's orchestrator frames it;
- hunk:  each @@ hunk of the item's diff on its own, with the file header.

    python .warf-experiments/real-set/jev-narrow/run_narrow.py [--limit N]   # resumes; writes answers.jsonl

Needs TYPESAFE_API_KEY (and TYPESAFE_BASE_URL for OpenRouter) in the environment. The key is never
printed or stored."""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = HERE.parent / "items.jsonl"
OUT = HERE / "answers.jsonl"
MODEL = "jev-latest"
INPUT_LABEL = "Patch under review (unified diff)"
DEFAULT_PERSONA = "Should this change be merged as it is? A defect you can point to is a REJECT."
VERDICT = {"APPROVE": "The code is correct and safe to merge as it is.",
           "REJECT": "The code has a defect, vulnerability or regression that must be fixed before it is merged."}
YESNO = {"YES": "Yes, the changed lines have this problem.", "NO": "No, the changed lines do not have this problem."}
CHECKS = {
    "offbyone": "Is an index, loop bound, size or range in the changed lines off by one or out of bounds?",
    "condition": "Is a condition, comparison, sign or operator in the changed lines inverted or wrong?",
    "wrongvar": "Does a changed line use the wrong variable, member, argument or function, for example one with a similar name?",
    "missing": "Does the change forget a case, an initialisation, a resize or an update that the surrounding code needs?",
    "memory": "Does the change introduce a memory or lifetime error: a dangling reference, a leak, a double free or an uninitialised value?",
    "interface": "Does the change break callers: a changed signature, return value or meaning that other code relies on?",
    "compile": "Would the changed code fail to compile on a supported configuration, for example a template, const or missing-include error?",
}


def questions():
    q = {"verdict": {"type": "choice", "instructions": DEFAULT_PERSONA, "criteria": VERDICT}}
    for k, text in CHECKS.items():
        q[k] = {"type": "choice", "instructions": text, "criteria": YESNO}
    return q


def frame(domain, code):
    return f"Domain: {domain}\n\n{INPUT_LABEL}:\n```\n{code}\n```"


def hunks(code):
    lines = code.splitlines()
    head, i = [], 0
    while i < len(lines) and not lines[i].startswith("@@"):
        head.append(lines[i]); i += 1
    out, cur = [], None
    for ln in lines[i:]:
        if ln.startswith("@@"):
            if cur: out.append(cur)
            cur = [ln]
        elif cur is not None:
            if ln.startswith("diff --git"):      # a later file in the same input: stop this hunk
                out.append(cur); cur = None
            else:
                cur.append(ln)
    if cur: out.append(cur)
    out = [h for h in out if any(l.startswith(("+", "-")) and not l.startswith(("+++", "---")) for l in h)]
    return ["\n".join(head + h) for h in out]


def ask(state, base, key):
    body = json.dumps({"model": MODEL, "state": state, "questions": questions()}).encode("utf-8")
    req = urllib.request.Request(f"{base}/v1/systemone", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    delay = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(delay); delay *= 2; continue
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError) as e:
            if attempt < 4:
                time.sleep(delay); delay *= 2; continue
            raise RuntimeError(str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--items", default=str(ITEMS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--whole-only", action="store_true", help="ask only the whole-item state, no hunks")
    a = ap.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    out = Path(a.out)
    items = [json.loads(l) for l in Path(a.items).open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = set()
    if out.exists():
        for l in out.open(encoding="utf-8"):
            r = json.loads(l); done.add((r["id"], r["state"], r["hunk"]))
    jobs = []
    for it in items:
        jobs.append((it, "whole", 0, frame(it["domain"], it["code"])))
        for k, h in enumerate([] if a.whole_only else hunks(it["code"])):
            jobs.append((it, "hunk", k, frame(it["domain"], h)))
    jobs = [j for j in jobs if (j[0]["id"], j[1], j[2]) not in done]
    print(f"{len(items)} items, {len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(job):
        it, st, k, state = job
        try:
            b = ask(state, base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1
                print(f"  error {it['id']} {st} {k}: {e}", flush=True)
            return
        ans = {q: {"choice": v.get("choice"), "p": v.get("probabilities")} for q, v in (b.get("answers") or {}).items()}
        rec = {"id": it["id"], "state": st, "hunk": k, "chars": len(state), "model": b.get("model"),
               "answers": ans, "usage": b.get("usage")}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, jobs))
    print(f"done; cost this run ${cost[0]:.4f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
