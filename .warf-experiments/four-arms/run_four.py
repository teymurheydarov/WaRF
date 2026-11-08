"""Four reviewers on the 100 gismo6 commits of ../laya-five/selection.jsonl, each through WaRF's
own review path (../laya-five/run_five.py: the sweep's diff, enrich_patch, detect_domain, input
label, then run_review at uniform priors with no oracle feedback):

  claude-one       one agent, CLAUDE, asked the sweep's question (the same persona as Jev's one
                   agent), on claude_cli / claude-opus-5-5
  claude-standard  WaRF's default profile unchanged (five personas), WARF_PROVIDER=claude_cli and
                   WARF_MODEL=claude-opus-5-5, WaRF's default review: no debate, early stopping on
  jev-one          as claude-one, on jev / jev-latest
  jev-standard     as claude-standard, WARF_PROVIDER=jev

    python .warf-experiments/four-arms/run_four.py --arm claude-one [--workers 4 --worker 0]

Claude isolation. WaRF's claude_cli provider runs `claude -p` in the home folder, where the agent
gets the CLI's default tools and the account's connectors (../standard-five/RESULTS.md: one agent
ran find and grep over the home folder). Here an agent could read gismo6's later history and so the
label. This runner therefore adds `--tools "" --strict-mcp-config --no-session-persistence` to
every CLI call and runs it in an empty folder; WaRF's provider code is otherwise unchanged. Every
CLAUDE* variable is removed first, so each CLI starts as from a plain terminal. A reply that is not
a vote and reads like a usage-limit or login message fails the review instead of counting as
REJECT (WaRF's parser would take it for one).

Jev is reached through WaRF's jev provider with TYPESAFE_API_KEY / TYPESAFE_BASE_URL, read from the
user's environment when this process lacks them (never printed).

Writes <arm>.w<k>.jsonl (WaRF session records plus a `four` block), errors.jsonl, and resumes
where it stopped. Nothing is written to any .warf/ (run_five points WARF_HOME at ../laya-five)."""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAYA = HERE.parent / "laya-five"
CLAUDE_MODEL = "claude-opus-5-5"
JEV_MODEL = "jev-latest"
MAX_ERRORS = 3                # consecutive failed reviews (quota, login, no credit) end the worker
NON_ANSWER = re.compile(r"limit|error|log ?in|credit|overloaded|unavailable|try again", re.I)
ISOLATION = ["--tools", "", "--strict-mcp-config", "--no-session-persistence"]

ap = argparse.ArgumentParser()
ap.add_argument("--arm", choices=("claude-one", "claude-standard", "jev-one", "jev-standard"), required=True)
ap.add_argument("--workers", type=int, default=1)
ap.add_argument("--worker", type=int, default=0)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--claude-exe", default=os.environ.get("CLAUDE_CODE_EXECPATH"))
args = ap.parse_args()
CLAUDE = args.arm.startswith("claude")
STANDARD = args.arm.endswith("standard")

for name in [k for k in os.environ if k.upper().startswith("CLAUDE")]:
    del os.environ[name]
for name in ("WARF_PROVIDER", "WARF_MODEL", "ANTHROPIC_API_KEY"):
    if os.environ.get(name):
        sys.exit(f"{name} is set; unset it so that this runner's choice applies")
if CLAUDE:
    if not args.claude_exe:
        sys.exit("no Claude CLI: pass --claude-exe")
    os.environ["PATH"] = str(Path(args.claude_exe).parent) + os.pathsep + os.environ.get("PATH", "")
    if STANDARD:
        os.environ["WARF_PROVIDER"], os.environ["WARF_MODEL"] = "claude_cli", CLAUDE_MODEL
else:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _key:
        for _name in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL"):
            if not os.environ.get(_name):
                try:
                    os.environ[_name] = winreg.QueryValueEx(_key, _name)[0]
                except FileNotFoundError:
                    pass
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set (neither in this process nor in the user's environment)")
    if STANDARD:
        os.environ["WARF_PROVIDER"] = "jev"
sys.path.insert(0, str(LAYA))

from run_five import INPUT_LABEL, PLAN, Tap as JevTap, answers, prepare  # noqa: E402
from run_laya_sweep import DEFAULT_PERSONA  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, ProviderError, detect_default_provider, resolve_model  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash, save_profiles  # noqa: E402

WANT = ("claude_cli", CLAUDE_MODEL) if CLAUDE else ("jev", JEV_MODEL)
if STANDARD:
    PROVIDER = detect_default_provider()
    MODEL = resolve_model(PROVIDER)
else:
    PROVIDER, MODEL = WANT
if (PROVIDER, MODEL) != WANT:
    sys.exit(f"WaRF would use {PROVIDER}/{MODEL}, not {WANT}")


class _IsolatedSubprocess:
    """Stands in for the subprocess module inside warf.providers: the Claude CLI's command gets the
    isolation flags and an empty working folder; everything else passes through."""

    def __init__(self, exe: str) -> None:
        self.exe = os.path.normcase(exe)
        self.cwd = tempfile.mkdtemp(prefix="warf-four-")

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, cmd, **kw):
        if cmd and os.path.normcase(str(cmd[0])) == self.exe:
            cmd = [cmd[0], *ISOLATION, *cmd[1:]]
            kw["cwd"] = self.cwd
        return subprocess.run(cmd, **kw)


class ClaudeTap:
    """Keeps every CLI exchange of one review: agent, raw first line (WaRF parses the vote from
    its first word), the reply, a fingerprint of the message sent, time taken, any failure."""

    def __init__(self, agents: dict) -> None:
        self.calls: list[dict] = []
        original = ClaudeCLIProvider.complete
        tap = self

        def complete(provider, system, user, model, timeout):
            entry = {"agent": agents.get(system, "?"), "model": model,
                     "sent_sha": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16], "sent_chars": len(user)}
            t0 = time.time()
            try:
                completion = original(provider, system, user, model, timeout)
            except BaseException as exc:
                entry.update(seconds=round(time.time() - t0, 2), error=f"{type(exc).__name__}: {exc}"[:500])
                tap.calls.append(entry)
                raise
            text = completion.text
            entry.update(seconds=round(time.time() - t0, 2), first_line=text.split("\n", 1)[0][:200],
                         chars=len(text), reply=text[:2000],
                         exact=text.split()[0].upper().rstrip(".,:") in ("APPROVE", "REJECT"))
            if not entry["exact"] and len(text) < 400 and NON_ANSWER.search(text):
                entry["error"] = f"non-answer: {text[:200]}"
                tap.calls.append(entry)
                raise ProviderError(f"the CLI answered without a vote: {text[:200]}")
            tap.calls.append(entry)
            return completion

        ClaudeCLIProvider.complete = complete


def ensure_profile() -> tuple[Path, dict]:
    """The arm's panel at uniform priors. Returns the path and {persona text: agent name}."""
    if STANDARD:                # WaRF's default profile; the environment picks provider and model
        profiles = default_profiles()
    else:
        name = "CLAUDE" if CLAUDE else "JEV"
        profiles = [AgentProfile(name=name, persona=DEFAULT_PERSONA, persona_hash=persona_hash(DEFAULT_PERSONA),
                                 provider=PROVIDER, model=MODEL)]
    path = HERE / "profiles" / f"{args.arm}.json"
    want = [(p.name, p.persona_hash, p.provider, p.model) for p in profiles]
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        got = [(d["name"], persona_hash(d["persona"]), d.get("provider"), d.get("model")) for d in have]
        if got != want:
            sys.exit(f"{path} holds another panel: {got}")
    else:
        path.parent.mkdir(exist_ok=True)
        save_profiles(path, profiles)
    return path, {p.persona: p.name for p in profiles}


def main() -> None:
    profile_path, agents = ensure_profile()
    if CLAUDE:
        providers.subprocess = _IsolatedSubprocess(str(Path(args.claude_exe)))
        tap = ClaudeTap(agents)
    else:
        tap = JevTap()
    plan = {}
    with PLAN.open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            plan[e["sha"]] = e
    selection = [json.loads(line) for line in (LAYA / "selection.jsonl").open(encoding="utf-8")]
    done = set()
    for path in HERE.glob(f"{args.arm}.w*.jsonl"):
        for line in path.open(encoding="utf-8"):
            done.add(json.loads(line)["four"]["id"])
    jobs = [s for s in selection if s["id"] not in done]
    jobs = [s for i, s in enumerate(jobs) if i % args.workers == args.worker]
    out_path = HERE / f"{args.arm}.w{args.worker}.jsonl"
    print(f"  {PROVIDER}/{MODEL}; arm {args.arm}, worker {args.worker} of {args.workers}: "
          f"{len(jobs)} reviews to run ({len(done)} done) -> {out_path.name}", flush=True)

    t_start, n, errors = time.time(), 0, 0
    with out_path.open("a", encoding="utf-8") as out:
        for s in jobs:
            if args.limit and n >= args.limit:
                break
            code, domain, context, enrich_error = prepare(plan[s["commit"]], s["file"])
            if domain != s["domain"]:
                sys.exit(f"{s['id']}: domain {domain}, the sweep had {s['domain']}")
            tap.calls.clear()
            t0 = time.time()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = run_review(code, domain, profile_path, verbose=False, debate=False,
                                        input_label=INPUT_LABEL, context=context, no_early_stop=not STANDARD)
            except Exception as exc:             # one review must not end the run; a lost login will
                errors += 1
                with (HERE / "errors.jsonl").open("a", encoding="utf-8") as e:
                    e.write(json.dumps({"id": s["id"], "arm": args.arm, "error": f"{type(exc).__name__}: {exc}"[:1000],
                                        "calls": tap.calls if CLAUDE else [],
                                        "at": datetime.now(timezone.utc).isoformat()}) + "\n")
                print(f"  {s['id']}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                if errors >= MAX_ERRORS:
                    sys.exit(f"  worker {args.worker} stopping: {errors} consecutive errors")
                continue
            errors = 0
            seconds = time.time() - t0
            four = {"id": s["id"], "commit": s["commit"], "file": s["file"], "label": s["label"], "arm": args.arm,
                    "provider": PROVIDER, "model": MODEL, "enrich_error": enrich_error, "seconds": round(seconds, 2)}
            if CLAUDE:
                answered = [c for c in tap.calls if "error" not in c]
                if [c["agent"] for c in answered] != [v.agent_name for v in result.votes]:
                    sys.exit(f"{s['id']}: tap {[c['agent'] for c in answered]} vs votes {[v.agent_name for v in result.votes]}")
                for c, v in zip(answered, result.votes):
                    c["vote"] = v.vote
                four["calls"] = list(tap.calls)
            else:
                got = answers(tap.calls, agents)
                for v in result.votes:                # the tap and WaRF's votes must agree
                    if (got["round1"][v.agent_name]["choice"] == "APPROVE") != (v.vote == 1):
                        sys.exit(f"{s['id']}: {v.agent_name} vote {v.vote} vs {got['round1'][v.agent_name]}")
                four["models"] = sorted({c["body"].get("model") for c in tap.calls})
                four["cost"] = round(sum(float((c["body"].get("usage") or {}).get("cost") or 0) for c in tap.calls), 8)
                four["round1"] = got["round1"]
            if not STANDARD and len(result.votes) != 1:
                sys.exit(f"{s['id']}: {len(result.votes)} votes from one agent")
            record = session_dict(result, artifact_path=f"{s['commit']}:{s['file']}", profile_name=args.arm)
            record["four"] = four
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
