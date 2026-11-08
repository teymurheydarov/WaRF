"""TypeSafe's Jev in WaRF, on the same 100 gismo6 commits as the five-Laya panel
(../laya-five/selection.jsonl), through the same review path (../laya-five/run_five.py).

Two arms, as with Laya:
  one   one agent, JEV, asked the sweep's question (WaRF's README example for a Jev agent);
        compare with the single Laya agent of the sweep
  five  WaRF's default five personas, every agent on Jev, uniform priors, debate on, early
        stopping off; compare with the five-Laya panel
  standard  WaRF's default profile unchanged, Jev selected by WARF_PROVIDER=jev, and WaRF's
        default review: no debate, early stopping on (as `warf review-commit` runs it)

    python .warf-experiments/jev-five/run_jev.py --arm one
    python .warf-experiments/jev-five/run_jev.py --arm five
    python .warf-experiments/jev-five/run_jev.py --arm one --plant      # planted-line control
    python .warf-experiments/jev-five/run_jev.py --arm one --repeat 10  # is Jev deterministic?

Jev is reached through WaRF's `jev` provider (warf/providers.py SystemOneProvider) at
TYPESAFE_BASE_URL with TYPESAFE_API_KEY. When this process does not have them, they are read
from the user's environment (HKCU\\Environment), as a newly started shell would; the key is
never printed. Writes sessions_<arm>.jsonl, controls_<arm>.jsonl or repeat_<arm>.jsonl here,
errors to errors.jsonl, and resumes where it stopped. Nothing is written to WaRF's data
directory (importing run_five points WARF_HOME at ../laya-five; WaRF writes nothing there
during a review)."""
import argparse
import contextlib
import io
import json
import os
import sys
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAYA = HERE.parent / "laya-five"
sys.path.insert(0, str(LAYA))

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _key:
    for _name in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL"):
        if not os.environ.get(_name):
            try:
                os.environ[_name] = winreg.QueryValueEx(_key, _name)[0]
            except FileNotFoundError:
                pass

from run_five import INPUT_LABEL, PLAN, PLANTS, Tap, answers, plant, prepare  # noqa: E402
from run_laya_sweep import DEFAULT_PERSONA  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash, save_profiles  # noqa: E402

MODEL = "jev-latest"          # WaRF's default for provider jev
MAX_ERRORS = 3                # consecutive failures (no credit, no key) end the run


def ensure_profile(arm: str) -> tuple[Path, dict]:
    """The arm's panel on provider jev: current personas, uniform priors. Returns the path
    and {persona text: agent name} for mapping Jev's answers back to agents."""
    if arm == "one":
        profiles = [AgentProfile(name="JEV", persona=DEFAULT_PERSONA, persona_hash=persona_hash(DEFAULT_PERSONA))]
    else:
        profiles = default_profiles()
    if arm != "standard":       # standard: no provider on the profile; WARF_PROVIDER picks Jev
        for p in profiles:
            p.provider, p.model = "jev", MODEL
    path = HERE / "profiles" / f"jev_{arm}.json"
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        want = [(p.name, p.persona_hash, p.provider, p.model) for p in profiles]
        got = [(d["name"], persona_hash(d["persona"]), d.get("provider"), d.get("model")) for d in have]
        if got != want:
            sys.exit(f"{path} holds another panel: {got}")
    else:
        save_profiles(path, profiles)
    return path, {p.persona: p.name for p in profiles}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("one", "five", "standard"), required=True)
    ap.add_argument("--plant", action="store_true", help="control: planted lines in the never-fixed changes, Round 1")
    ap.add_argument("--repeat", type=int, default=0, help="ask the first N commits again, Round 1, to check determinism")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set (neither in this process nor in the user's environment)")
    if args.arm == "standard":
        os.environ["WARF_PROVIDER"] = "jev"
    print(f"  Jev at {os.environ.get('TYPESAFE_BASE_URL') or 'https://api.typesafe.ai'}, model {MODEL}", flush=True)

    profile_path, agents = ensure_profile(args.arm)
    plan = {}
    with PLAN.open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            plan[e["sha"]] = e
    selection = [json.loads(line) for line in (LAYA / "selection.jsonl").open(encoding="utf-8")]
    kind = "controls" if args.plant else "repeat" if args.repeat else "sessions"
    out_path = HERE / f"{kind}_{args.arm}.jsonl"
    done = set()
    if out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["jev"]["id"], r["jev"].get("plant")))
    if args.repeat:
        jobs = [(s, None) for s in selection[:args.repeat]]
    else:
        jobs = [(s, name) for s in selection for name in (PLANTS if args.plant else [None])
                if not args.plant or s["label"] == "APPROVE"]
    jobs = [(s, name) for s, name in jobs if (s["id"], name) not in done]
    debate = args.arm == "five" and kind == "sessions"
    print(f"  arm {args.arm}: {len(jobs)} reviews to run ({len(done)} done) -> {out_path.name}", flush=True)

    tap = Tap()
    t_start, n, skipped, errors = time.time(), 0, 0, 0
    with out_path.open("a", encoding="utf-8") as out:
        for s, name in jobs:
            if args.limit and n >= args.limit:
                break
            code, domain, context, enrich_error = prepare(plan[s["commit"]], s["file"])
            if domain != s["domain"]:
                sys.exit(f"{s['id']}: domain {domain}, the sweep had {s['domain']}")
            if name:
                code = plant(code, PLANTS[name])
                if code is None:
                    skipped += 1
                    continue
            tap.calls.clear()
            t0 = time.time()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = run_review(code, domain, profile_path, verbose=False, debate=debate,
                                        input_label=INPUT_LABEL, context=context,
                                        no_early_stop=args.arm != "standard")
            except Exception as exc:             # one review must not end the run; a dead key will
                errors += 1
                with (HERE / "errors.jsonl").open("a", encoding="utf-8") as e:
                    e.write(json.dumps({"id": s["id"], "arm": args.arm, "kind": kind, "plant": name,
                                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                                        "at": datetime.now(timezone.utc).isoformat()}) + "\n")
                print(f"  {s['id']}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                if errors >= MAX_ERRORS:
                    sys.exit(f"  stopping: {errors} consecutive errors")
                continue
            errors = 0
            seconds = time.time() - t0
            got = answers(tap.calls, agents)
            for rnd, votes in (("round1", result.votes), ("round2", result.debate_votes)):
                for v in votes:                       # the tap and WaRF's votes must agree
                    if (got[rnd][v.agent_name]["choice"] == "APPROVE") != (v.vote == 1):
                        sys.exit(f"{s['id']}: {rnd} {v.agent_name} vote {v.vote} vs {got[rnd][v.agent_name]}")
            if args.arm != "standard" and len(got["round1"]) != len(agents):   # standard may stop early
                sys.exit(f"{s['id']}: {len(got['round1'])} Round-1 answers")
            record = session_dict(result, artifact_path=f"{s['commit']}:{s['file']}", profile_name=f"jev_{args.arm}")
            record["jev"] = {
                "id": s["id"], "commit": s["commit"], "file": s["file"], "label": s["label"], "plant": name,
                "enrich_error": enrich_error, "seconds": round(seconds, 2),
                "models": sorted({c["body"].get("model") for c in tap.calls}),
                "cost": round(sum(float((c["body"].get("usage") or {}).get("cost") or 0) for c in tap.calls), 8),
                **got,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 10 == 0:
                rate = (time.time() - t_start) / n
                print(f"  {n}/{len(jobs)}  {rate:.1f} s per review, ~{rate * (len(jobs) - n) / 60:.0f} min left", flush=True)
    print(f"  done: {n} reviews in {(time.time() - t_start) / 60:.1f} min"
          + (f"; {skipped} skipped, the patch adds no line to plant after" if skipped else ""), flush=True)


if __name__ == "__main__":
    main()
