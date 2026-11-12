"""Lever "locate": make Jev point at an added line (development, ../../DEV.md).

For each hunk (run_narrow.hunks) the added lines are numbered L1..Lk, k <= K (a hunk with more added lines is split
into chunks of K added lines; each chunk keeps the hunk's file header and @@ line, and up to CTX hunk lines before
its first and after its last labelled line, shown unlabelled). One System One call per chunk asks
  locate: choice "Which added line introduces a defect, if any?" over NONE, L1..Lk (criterion = the line's text)
  plus the 7 generic checks of run_narrow (YES/NO).
The state is run_narrow.frame(domain, chunk) with "[Lj] " prefixed to the labelled added lines.
A hunk with no added line (deletions only) gets the 7 checks without the locate question.

    python -B run_locate.py [--limit N] [--workers 4] [--k 25]   # resumes; writes answers_locate.jsonl

The key is read from TYPESAFE_API_KEY and is never printed or stored."""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_narrow as rn  # noqa: E402

ITEMS = HERE.parent.parent / "items.jsonl"
OUT = HERE / "answers_locate.jsonl"
LOCATE = "Which added line introduces a defect, if any?"
CTX = 10


def is_add(ln):
    return ln.startswith("+") and not ln.startswith("+++")


def chunks(hunk, K):
    """-> list of (state_text, {label: line text}) for one hunk string (header + @@ + body)."""
    lines = hunk.splitlines()
    at = next(i for i, l in enumerate(lines) if l.startswith("@@"))
    head, body = lines[:at + 1], lines[at + 1:]
    adds = [i for i, l in enumerate(body) if is_add(l)]
    if not adds:
        return [("\n".join(head + body), {})]
    out = []
    for c in range(0, len(adds), K):
        mine = adds[c:c + K]
        lo = 0 if len(adds) <= K else max(0, mine[0] - CTX)
        hi = len(body) if len(adds) <= K else min(len(body), mine[-1] + 1 + CTX)
        lab, txt = {}, []
        for i in range(lo, hi):
            if i in mine:
                j = mine.index(i) + 1
                t = body[i][1:].strip()
                lab[f"L{j}"] = (t[:300] if t else "(blank line)")
                txt.append(f"[L{j}] {body[i]}")
            else:
                txt.append(body[i])
        out.append(("\n".join(head + txt), lab))
    return out


def questions(lab):
    q = {}
    if lab:
        crit = {"NONE": "No added line introduces a defect."}
        crit.update(lab)
        q["locate"] = {"type": "choice", "instructions": LOCATE, "criteria": crit}
    for k, text in rn.CHECKS.items():
        q[k] = {"type": "choice", "instructions": text, "criteria": rn.YESNO}
    return q


def ask(state, qs, base, key):
    body = json.dumps({"model": rn.MODEL, "state": state, "questions": qs}).encode("utf-8")
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
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    a.workers = min(a.workers, 4)
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    out = Path(a.out)
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = set()
    if out.exists():
        for l in out.open(encoding="utf-8"):
            r = json.loads(l); done.add((r["id"], r["hunk"], r["chunk"]))
    jobs = []
    for it in items:
        for h, hk in enumerate(rn.hunks(it["code"])):
            for c, (txt, lab) in enumerate(chunks(hk, a.k)):
                if (it["id"], h, c) not in done:
                    jobs.append((it, h, c, rn.frame(it["domain"], txt), lab))
    print(f"{len(items)} items, {len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(job):
        it, h, c, state, lab = job
        try:
            b = ask(state, questions(lab), base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1
                print(f"  error {it['id']} {h} {c}: {e}", flush=True)
            return
        ans = {q: {"choice": v.get("choice"), "p": v.get("probabilities")} for q, v in (b.get("answers") or {}).items()}
        rec = {"id": it["id"], "state": "hunk", "hunk": h, "chunk": c, "k": len(lab), "chars": len(state),
               "model": b.get("model"), "answers": ans, "usage": b.get("usage")}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, jobs))
    print(f"done; cost this run ${cost[0]:.5f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
