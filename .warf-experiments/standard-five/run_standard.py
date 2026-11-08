"""WaRF's standard panel, as shipped, on the 100 gismo6 commits of ../laya-five/selection.jsonl:
the five default personas (SKEPTIC, ADVOCATE, AUDITOR, TEST-FOCUSED, BOUNDARY) with no
provider or model on the profile, so WaRF picks its default (warf/providers.py): the Claude CLI
with claude-haiku-4-5-20251001. Same review path as the Laya and Jev panels
(../laya-five/run_five.py): the sweep's diff, enrich_patch, detect_domain and input label, then
run_review with uniform priors, no oracle feedback, early stopping off.

Two arms:
  five      the standard panel, debate Round 2 on
  auditor5  AUDITOR alone, asked five times per commit (Round 1 only): five votes from one
            persona, to separate what five personas add from what five votes add

    python .warf-experiments/standard-five/run_standard.py --arm five [--workers 4 --worker 0]

The Claude desktop app keeps its CLI where WaRF's find_claude_exe() does not look, so the CLI's
directory goes on PATH (taken from CLAUDE_CODE_EXECPATH or --claude-exe); WaRF then selects it
by its own rule. When this runs inside a Claude Code session, every CLAUDE* variable is removed
first, so each agent's CLI starts as it would from a plain terminal and not as a child of that
session. A reply whose first word is not APPROVE or REJECT and that reads like a usage-limit
or login message fails the review instead of being counted: WaRF's parser would take it for a
REJECT. Writes <arm>.w<k>.jsonl (WaRF session records plus a `std` block), errors.jsonl, and
resumes where it stopped. WaRF writes nothing to its data directory during a review; the CLI
keeps a transcript of every call under ~/.claude/projects/ for the home directory, as it does
whenever WaRF uses it."""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAYA = HERE.parent / "laya-five"
MAX_ERRORS = 3                # consecutive failed reviews (quota, login, CLI gone) end the worker
NON_ANSWER = re.compile(r"limit|error|log ?in|credit|overloaded|unavailable|try again", re.I)

ap = argparse.ArgumentParser()
ap.add_argument("--arm", choices=("five", "auditor5"), required=True)
ap.add_argument("--workers", type=int, default=1)
ap.add_argument("--worker", type=int, default=0)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--claude-exe", default=os.environ.get("CLAUDE_CODE_EXECPATH"))
args = ap.parse_args()

for name in [k for k in os.environ if k.upper().startswith("CLAUDE")]:
    del os.environ[name]
if args.claude_exe:
    os.environ["PATH"] = str(Path(args.claude_exe).parent) + os.pathsep + os.environ.get("PATH", "")
for name in ("WARF_PROVIDER", "WARF_MODEL", "ANTHROPIC_API_KEY"):
    if os.environ.get(name):
        sys.exit(f"{name} is set; unset it so that WaRF's standard choice applies")
sys.path.insert(0, str(LAYA))

from run_five import INPUT_LABEL, PLAN, prepare  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, ProviderError, detect_default_provider, resolve_model  # noqa: E402
from warf.state import PERSONA_AUDITOR, AgentProfile, default_profiles, persona_hash, save_profiles  # noqa: E402

PROVIDER = detect_default_provider()
MODEL = resolve_model(PROVIDER)
if (PROVIDER, MODEL) != ("claude_cli", "claude-haiku-4-5-20251001"):
    sys.exit(f"WaRF would use {PROVIDER}/{MODEL}, not its standard claude_cli/claude-haiku-4-5-20251001")


def ensure_profile(arm: str) -> tuple[Path, dict]:
    """The arm's panel with WaRF's personas and no provider or model, at uniform priors.
    Returns the path and {persona text: agent name}."""
    if arm == "five":
        profiles = default_profiles()
    else:
        profiles = [AgentProfile(name="AUDITOR", persona=PERSONA_AUDITOR, persona_hash=persona_hash(PERSONA_AUDITOR))]
    path = HERE / "profiles" / f"standard_{arm}.json"
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        want = [(p.name, p.persona_hash, None, None) for p in profiles]
        got = [(d["name"], persona_hash(d["persona"]), d.get("provider"), d.get("model")) for d in have]
        if got != want:
            sys.exit(f"{path} holds another panel: {got}")
    else:
        save_profiles(path, profiles)
    return path, {p.persona: p.name for p in profiles}


class Tap:
    """Keeps every CLI exchange of one review: which agent and round, the raw first line (WaRF
    parses the vote from its first word), the reply's length, a fingerprint of the message sent,
    the time taken, and any failure. The agents of a review are asked one after another."""

    def __init__(self, agents: dict) -> None:
        self.calls: list[dict] = []
        original = ClaudeCLIProvider.complete
        tap = self

        def complete(provider, system, user, model, timeout):
            entry = {"agent": agents.get(system, "?"),
                     "round": "round2" if "=== Round 1 Summary ===" in user else "round1",
                     "model": model, "sent_sha": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16],
                     "sent_chars": len(user)}
            t0 = time.time()
            try:
                completion = original(provider, system, user, model, timeout)
            except BaseException as exc:
                entry.update(seconds=round(time.time() - t0, 2), error=f"{type(exc).__name__}: {exc}"[:500])
                tap.calls.append(entry)
                raise
            text = completion.text
            entry.update(seconds=round(time.time() - t0, 2), first_line=text.split("\n", 1)[0][:200], chars=len(text),
                         exact=text.split()[0].upper().rstrip(".,:") in ("APPROVE", "REJECT"))
            if not entry["exact"] and len(text) < 400 and NON_ANSWER.search(text):
                # WaRF would read a usage-limit or login message as REJECT (_parse_vote's fallback)
                entry["error"] = f"non-answer: {text[:200]}"
                tap.calls.append(entry)
                raise ProviderError(f"the CLI answered without a vote: {text[:200]}")
            tap.calls.append(entry)
            return completion

        ClaudeCLIProvider.complete = complete


def main() -> None:
    profile_path, agents = ensure_profile(args.arm)
    plan = {}
    with PLAN.open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            plan[e["sha"]] = e
    selection = [json.loads(line) for line in (LAYA / "selection.jsonl").open(encoding="utf-8")]
    samples = 5 if args.arm == "auditor5" else 1
    done = set()
    for path in HERE.glob(f"{args.arm}.w*.jsonl"):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["std"]["id"], r["std"]["sample"]))
    jobs = [(s, k) for s in selection for k in range(samples) if (s["id"], k) not in done]
    jobs = [job for i, job in enumerate(jobs) if i % args.workers == args.worker]
    out_path = HERE / f"{args.arm}.w{args.worker}.jsonl"
    print(f"  {PROVIDER}/{MODEL}; arm {args.arm}, worker {args.worker} of {args.workers}: "
          f"{len(jobs)} reviews to run ({len(done)} done) -> {out_path.name}", flush=True)

    tap = Tap(agents)
    t_start, n, errors = time.time(), 0, 0
    with out_path.open("a", encoding="utf-8") as out:
        for s, k in jobs:
            if args.limit and n >= args.limit:
                break
            code, domain, context, enrich_error = prepare(plan[s["commit"]], s["file"])
            if domain != s["domain"]:
                sys.exit(f"{s['id']}: domain {domain}, the sweep had {s['domain']}")
            tap.calls.clear()
            t0 = time.time()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = run_review(code, domain, profile_path, verbose=False, debate=args.arm == "five",
                                        input_label=INPUT_LABEL, context=context, no_early_stop=True)
            except Exception as exc:             # one review must not end the run; a lost login will
                errors += 1
                with (HERE / "errors.jsonl").open("a", encoding="utf-8") as e:
                    e.write(json.dumps({"id": s["id"], "arm": args.arm, "sample": k,
                                        "error": f"{type(exc).__name__}: {exc}"[:1000], "calls": tap.calls,
                                        "at": datetime.now(timezone.utc).isoformat()}) + "\n")
                print(f"  {s['id']}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                if errors >= MAX_ERRORS:
                    sys.exit(f"  worker {args.worker} stopping: {errors} consecutive errors")
                continue
            errors = 0
            seconds = time.time() - t0
            for rnd, votes in (("round1", result.votes), ("round2", result.debate_votes)):
                answered = [c for c in tap.calls if c["round"] == rnd and "error" not in c]
                if [c["agent"] for c in answered] != [v.agent_name for v in votes]:
                    sys.exit(f"{s['id']}: {rnd} tap {[c['agent'] for c in answered]} vs votes {[v.agent_name for v in votes]}")
                for c, v in zip(answered, votes):
                    c["vote"] = v.vote
            record = session_dict(result, artifact_path=f"{s['commit']}:{s['file']}", profile_name=f"standard_{args.arm}")
            record["std"] = {
                "id": s["id"], "commit": s["commit"], "file": s["file"], "label": s["label"], "arm": args.arm,
                "sample": k, "enrich_error": enrich_error, "seconds": round(seconds, 2), "calls": list(tap.calls),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 5 == 0:
                rate = (time.time() - t_start) / n
                print(f"  worker {args.worker}: {n}/{len(jobs)}  {rate:.0f} s per review, "
                      f"~{rate * (len(jobs) - n) / 60:.0f} min left", flush=True)
    print(f"  worker {args.worker} done: {n} reviews in {(time.time() - t_start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
