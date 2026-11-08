"""Re-ask the one-question JEV agent on the 100 commits of ../laya-five/selection.jsonl,
through run_jev.py's review path (prepare -> run_review with the JEV profile, Round 1, no
debate, early stopping off), and write the answers to rerun_<tag>.jsonl in THIS directory.

Nothing is written to the experiment: the profile is a copy kept here, run_review gets that
copy, and the outputs, the state texts and the request counter live here. Every HTTP request
is counted (retries included) against a hard cap kept in requests.json.

    python -B rerun_one.py --tag A [--limit N]
"""
import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
JEV = Path(r"C:\workdir\warf\WaRF\.warf-experiments\jev-five")
LAYA = JEV.parent / "laya-five"
BUDGET = 220
COUNTER = OUT / "requests.json"

sys.path.insert(0, str(JEV))
import run_jev  # noqa: E402  (reads TYPESAFE_* from HKCU when missing; never prints the key)
from run_jev import INPUT_LABEL, PLAN, Tap, answers, prepare, run_review, session_dict  # noqa: E402


def _count() -> int:
    return json.loads(COUNTER.read_text())["count"] if COUNTER.exists() else 0


_urlopen = urllib.request.urlopen


def _counted(*args, **kwargs):
    n = _count()
    if n >= BUDGET:
        raise SystemExit(f"request budget of {BUDGET} reached")
    COUNTER.write_text(json.dumps({"count": n + 1}))
    return _urlopen(*args, **kwargs)


urllib.request.urlopen = _counted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    import os
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY not available")
    print(f"  base {os.environ.get('TYPESAFE_BASE_URL')}; requests so far {_count()} of {BUDGET}", flush=True)

    prof = OUT / "profiles" / "jev_one.json"
    if not prof.exists():
        prof.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(JEV / "profiles" / "jev_one.json", prof)
    agents = {d["persona"]: d["name"] for d in json.loads(prof.read_text(encoding="utf-8"))}

    plan = {}
    with PLAN.open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            plan[e["sha"]] = e
    selection = [json.loads(line) for line in (LAYA / "selection.jsonl").open(encoding="utf-8")]
    original = {}
    for line in (JEV / "sessions_one.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        original[r["jev"]["id"]] = r["jev"]["round1"]["JEV"]["state_chars"]

    out_path = OUT / f"rerun_{args.tag}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(line)["jev"]["id"] for line in out_path.open(encoding="utf-8")}
    states_path = OUT / "states.jsonl"
    have_state = set()
    if states_path.exists():
        have_state = {json.loads(line)["id"] for line in states_path.open(encoding="utf-8")}
    jobs = [s for s in selection if s["id"] not in done]
    print(f"  tag {args.tag}: {len(jobs)} to ask ({len(done)} done)", flush=True)

    tap = Tap()
    n = 0
    t_start = time.time()
    with out_path.open("a", encoding="utf-8") as out, states_path.open("a", encoding="utf-8") as st:
        for s in jobs:
            if args.limit and n >= args.limit:
                break
            code, domain, context, enrich_error = prepare(plan[s["commit"]], s["file"])
            if domain != s["domain"]:
                sys.exit(f"{s['id']}: domain {domain}, the sweep had {s['domain']}")
            tap.calls.clear()
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_review(code, domain, prof, verbose=False, debate=False,
                                    input_label=INPUT_LABEL, context=context, no_early_stop=True)
            got = answers(tap.calls, agents)
            if len(got["round1"]) != 1 or len(tap.calls) != 1:
                sys.exit(f"{s['id']}: {len(tap.calls)} calls")
            v = result.votes[0]
            if (got["round1"]["JEV"]["choice"] == "APPROVE") != (v.vote == 1):
                sys.exit(f"{s['id']}: tap and vote disagree")
            state = tap.calls[0]["state"]
            if len(state) != original[s["id"]]:
                sys.exit(f"{s['id']}: state has {len(state)} chars, the original run {original[s['id']]}")
            if s["id"] not in have_state:
                st.write(json.dumps({"id": s["id"], "state": state, "code": code,
                                     "sha256": hashlib.sha256(state.encode("utf-8")).hexdigest()},
                                    ensure_ascii=False) + "\n")
                have_state.add(s["id"])
            record = session_dict(result, artifact_path=f"{s['commit']}:{s['file']}", profile_name=f"rerun_{args.tag}")
            record["jev"] = {
                "id": s["id"], "commit": s["commit"], "file": s["file"], "label": s["label"], "plant": None,
                "enrich_error": enrich_error, "seconds": round(time.time() - t0, 2),
                "models": sorted({c["body"].get("model") for c in tap.calls}),
                "cost": round(sum(float((c["body"].get("usage") or {}).get("cost") or 0) for c in tap.calls), 8),
                "at": datetime.now(timezone.utc).isoformat(),
                **got,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            st.flush()
            n += 1
    print(f"  asked {n} in {(time.time() - t_start) / 60:.1f} min; requests so far {_count()} of {BUDGET}", flush=True)


if __name__ == "__main__":
    main()
