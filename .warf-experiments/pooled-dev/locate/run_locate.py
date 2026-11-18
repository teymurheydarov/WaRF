"""Line localisation and specific build diagnostics for Jev (development, RocksDB matched set).

Two new elicitations, both on the project-context state of ../history/run_lo_ctx.py (build rules from
RocksDB's Makefile/CMake + the defect profile of the 37 defects outside the test set):

  locate   each added line of the diff is marked [L1], [L2], ... and two choice questions ask WHICH added line
           breaks a supported build ("build") or introduces a runtime defect ("runtime"), with NONE as an
           option. The score of a change is 1 - p(NONE). Changes with more than WINDOW added lines are asked in
           windows of WINDOW lines (same state, options for that window only); the score then is
           1 - prod_w p_w(NONE).
  diag     eleven YES/NO questions, one per strict-build or runtime failure the project's build rules guard
           against (sign-compare, narrowing, -Wshadow, NDEBUG-only use, override, format, configurations,
           includes, uninitialised members, leaks, flaky tests); asked once per change (first window's call).

    python run_locate.py [--limit N]      # resumes; writes answers.jsonl"""
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
EXP = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "history"))
from run_checks import rn  # noqa: E402  (frame, ask machinery, YESNO)
from run_lo_ctx import CONTEXT  # noqa: E402
sys.path.insert(0, str(EXP.parent))
from warf.context_extractor import _SEPARATOR  # noqa: E402

OUT = HERE / "answers.jsonl"
WINDOW = 60
LOCATE = {
    "build": "Which added line makes this change fail to build on a supported RocksDB configuration: a compiler "
             "error, or a warning that -Werror or /WX turns into an error (sign-compare, shadowing, an unused "
             "variable or parameter in release builds, a missing override, a narrowing conversion, a format "
             "specifier that does not match its argument, a name unavailable under ROCKSDB_LITE, a custom "
             "ROCKSDB_NAMESPACE, Windows/MSVC or another platform)? Choose NONE if every added line builds "
             "everywhere.",
    "runtime": "Which added line introduces a runtime defect: a wrong result, a crash, a leak, a read of an "
               "uninitialised or freed value, a data race or deadlock, or a test that can hang or fail "
               "intermittently? Choose NONE if no added line does.",
}
DIAG = {
    "signcmp": "Does an added line compare a signed integer with an unsigned one (int with size_t or uint64_t, or "
               "a plain int literal with .size() in ASSERT_EQ/EXPECT_EQ/ASSERT_LT), which -Wsign-compare rejects?",
    "narrow": "Does an added line store a 64-bit or size_t value into a 32-bit or smaller integer, or a wider "
              "into a narrower type, without an explicit cast (-Wshorten-64-to-32, MSVC C4244/C4267)?",
    "shadow": "Does an added declaration reuse the name of a variable, parameter or member of an enclosing scope "
              "(-Wshadow)?",
    "ndebug": "Is an added variable, parameter or function used only inside assert() or only under some #ifdef, "
              "so that a release (NDEBUG) or other build warns that it is unused?",
    "override": "Does a class in the change override a virtual function without `override` while other members "
                "use it, or mark a function `override` that overrides nothing?",
    "format": "Does an added printf-style call use a format specifier that does not match its argument on every "
              "platform (%lu or %llu for uint64_t instead of PRIu64, %d for size_t)?",
    "config": "Does added code use a name, header or feature that is missing in another supported build: "
              "ROCKSDB_LITE, a custom ROCKSDB_NAMESPACE, Windows/MSVC, 32-bit, or a build without an optional "
              "library?",
    "include": "Does added code use a function or type without including its header, or include an internal "
               "header from public headers or examples?",
    "uninit": "Does the change add a member, field or variable that can be read before it is initialised, for "
              "example a struct member with no default initializer?",
    "leak": "Does added code allocate memory or a resource (new, an iterator, a transaction, a file, a snapshot) "
            "that is not released on every path?",
    "flaky": "Does an added or changed test depend on timing, thread scheduling, sync points or background "
             "flushes/compactions in a way that can make it hang or fail intermittently?",
}


def mark(code):
    """The diff with each added line tagged [Lk]; returns (marked code, list of added-line texts)."""
    diff, sep, rest = code.partition(_SEPARATOR)
    out, added = [], []
    for ln in diff.splitlines():
        if ln.startswith("+") and not ln.startswith("+++"):
            added.append(ln[1:].strip())
            out.append(f"+[L{len(added)}] {ln[1:]}")
        else:
            out.append(ln)
    return "\n".join(out) + (sep + rest if sep else ""), added


def questions(lo, hi, added, with_diag):
    opts = {f"L{k + 1}": f"the added line marked [L{k + 1}]: {added[k][:50]}" for k in range(lo, hi)}
    opts["NONE"] = "None of these added lines has this problem."
    q = {k: {"type": "choice", "instructions": t, "criteria": opts} for k, t in LOCATE.items()}
    if with_diag:
        q.update({k: {"type": "choice", "instructions": t, "criteria": rn.YESNO} for k, t in DIAG.items()})
    return q


def ask(state, q, base, key):
    """rn.ask with the questions as an argument (rn.ask sends the module-level rn.questions())."""
    body = json.dumps({"model": rn.MODEL, "state": state, "questions": q}).encode("utf-8")
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
    a = ap.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    items = [json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    done = {(json.loads(l)["id"], json.loads(l)["window"]) for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    jobs = []
    for it in items:
        code, added = mark(it["code"])
        state = f"Project context:\n{CONTEXT}\n\n" + rn.frame(it["domain"], code)
        for w, lo in enumerate(range(0, max(1, len(added)), WINDOW)):
            if (it["id"], w) not in done:
                jobs.append((it["id"], w, state, questions(lo, min(lo + WINDOW, len(added)), added, w == 0)))
    print(f"{len(jobs)} calls to make ({len(done)} done)", flush=True)
    lock, cost, errs = threading.Lock(), [0.0], [0]

    def run(job):
        i, w, st, q = job
        try:
            b = ask(st, q, base, key)
        except RuntimeError as e:
            with lock:
                errs[0] += 1; print(f"  error {i} w{w}: {e}", flush=True)
            return
        ans = {k: {"choice": v.get("choice"), "p": v.get("probabilities")} for k, v in (b.get("answers") or {}).items()}
        with lock:
            cost[0] += float((b.get("usage") or {}).get("cost") or 0)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": i, "window": w, "chars": len(st), "model": b.get("model"), "answers": ans,
                                    "usage": b.get("usage")}) + "\n")

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(run, jobs))
    print(f"done; cost ${cost[0]:.4f}, errors {errs[0]}", flush=True)


if __name__ == "__main__":
    main()
