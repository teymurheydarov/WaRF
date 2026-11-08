"""Ask each of three reviewers, once, about every item of items.jsonl (plant.py: 54 never-fixed gismo6
changes, each clean and with one planted defect), through WaRF's run_review with one agent:

  claude   CLAUDE on claude_cli / claude-opus-5-5
  jev      JEV on jev / jev-latest
  laya     LAYA on laya / multilingual (a local laya-serve)
  claude-standard  WaRF's default profile unchanged (the five personas) with WARF_PROVIDER=claude_cli
           and WARF_MODEL=claude-opus-5-5, and WaRF's default review: no debate, early stopping on
           (as ../four-arms/ ran it): five copies of Claude Opus with different persona texts
  claude-strict    one CLAUDE agent asked STRICT_PERSONA: reject only for a defect the change introduces
  claude-x5        five identical CLAUDE seats with the single agent's question, WaRF's default
           review: the same prompt sampled five times, majority, at the panel's cost
  claude-advocate  one agent with WaRF's ADVOCATE persona; claude-skeptic: one with SKEPTIC's
  claude-commit    one agent shown the whole commit (the set's commit_inputs.jsonl), the sweep's question;
                   claude-commit-strict: the same with STRICT_PERSONA

The single agents get the sweep's question (the same persona as in ../four-arms/), and the item's code,
domain and context exactly as stored. These single answers are the material for score_planted.py:
Claude alone is the claude arm's verdict, and the mixed panel replays the three stored answers
through WaRF's log-odds mode, so its Claude seat is the same answer Claude alone gave.

    python .warf-experiments/planted/run_planted.py --arm claude [--workers 2 --worker 0]
    python .warf-experiments/planted/run_planted.py --arm claude --set .warf-experiments/evidence-set

--set reviews another folder's items.jsonl (same fields) and writes the outputs there.

Claude runs isolated as in ../four-arms/run_four.py: `--tools "" --strict-mcp-config
--no-session-persistence`, an empty working folder, no CLAUDE* variables; a run that does not apply
the flags stops. Jev's key comes from the user's environment when this process lacks it (never
printed). Writes <arm>.w<k>.jsonl (WaRF session records plus a `planted` block holding the raw
answer), errors.jsonl, and resumes where it stopped. Nothing is written to any .warf/."""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
MAX_ERRORS = 3
NON_ANSWER = re.compile(r"limit|error|log ?in|credit|overloaded|unavailable|try again", re.I)
ISOLATION = ["--tools", "", "--strict-mcp-config", "--no-session-persistence"]
SEATS = {"claude": ("CLAUDE", "claude_cli", "claude-opus-5-5"),
         "jev": ("JEV", "jev", "jev-latest"),
         "laya": ("LAYA", "laya", "multilingual"),
         "claude-standard": (None, "claude_cli", "claude-opus-5-5"),
         "claude-strict": ("CLAUDE", "claude_cli", "claude-opus-5-5"),
         "claude-x5": ("CLAUDE", "claude_cli", "claude-opus-5-5"),
         "claude-advocate": ("ADVOCATE", "claude_cli", "claude-opus-5-5"),
         "claude-skeptic": ("SKEPTIC", "claude_cli", "claude-opus-5-5"),
         "claude-commit": ("CLAUDE-COMMIT", "claude_cli", "claude-opus-5-5"),
         "claude-commit-strict": ("CLAUDE-COMMIT", "claude_cli", "claude-opus-5-5"),
         "claude-verify": ("CHECKER", "claude_cli", "claude-opus-5-5"),
         "claude-verify-tools": ("CHECKER-SEARCH", "claude_cli", "claude-opus-5-5"),
         "claude-commit-strict-tools": ("CLAUDE-SEARCH", "claude_cli", "claude-opus-5-5")}
# claude-verify (development, real-set DEV.md): the checker of a finder + checker panel. It reviews only
# the items of the set's verify_inputs.jsonl (the whole commit plus the finder's objection), asked
# VERIFY_PERSONA; its profile carries evidence="objection".
VERIFY_PERSONA = ("Another reviewer objected to this change; the objection follows the code. Check the "
                  "objection against the code you are shown. REJECT only if it, or another defect you can "
                  "point to, is a real defect that this change introduces: something the added or modified "
                  "lines do wrong when compiled or run on a configuration the project supports. APPROVE if "
                  "the objection is mistaken, concerns code this change did not touch, or is about style, "
                  "naming, documentation, missing tests or design. Where it depends on code you cannot see, "
                  "judge how likely it is from the code shown and the conventions it follows.")
VERIFY_LABEL = "Commit under review (message, the reviewed file's diff, the other files) and an objection to it"
# claude-verify-tools (development): the same checker, able to read and search a snapshot of the
# repository at the commit (git archive, no .git, so no later history). Its working folder is that
# snapshot; the CLI's read tools are refused outside it (checked with canaries on 2026-11-06).
VERIFY_TOOLS_PERSONA = (VERIFY_PERSONA + " Your working folder holds the repository exactly as it was at "
                        "this commit; read and search it to check claims about code you are not shown.")
TOOL_ARMS = ("claude-verify-tools", "claude-commit-strict-tools")
TOOL_ISOLATION = ["--tools", "Read,Grep,Glob", "--strict-mcp-config", "--no-session-persistence"]
GISMO = Path(r"C:\Users\Teymur Heydarov\source\repos\gismo6")
SNAPSHOT_SKIP = {"filedata", "external", "doc"}     # data files, third-party code, documentation
# The whole-commit arms (ADR 0002's whole-commit reader) review commit_inputs.jsonl of the set instead
# of items.jsonl's single-file `code`, under COMMIT_LABEL; their profile carries evidence="whole-commit".
COMMIT_ARMS = ("claude-commit", "claude-commit-strict", "claude-commit-strict-tools")
COMMIT_LABEL = "Commit under review: its message, the reviewed file's diff, then the commit's other files"
# claude-strict's question, fixed on 2026-11-05 before it was run: the single agent's question with a
# bar that rules out what the panel's extra leniency removed (pre-existing issues, nits, unseen code)
STRICT_PERSONA = ("Should this change be merged as it is? REJECT only for a defect that this change "
                  "introduces: something the added or modified lines do wrong when the code runs, which "
                  "you can point to. Do not reject for problems that were already in the code before this "
                  "change, for style, naming, comments, documentation, missing tests or design preferences, "
                  "or because a declaration or caller is not shown; assume code you cannot see is correct.")
# claude-commit-strict-tools (development): the decisive single competitor, one strict Claude given the
# same evidence as the panel (the whole commit and the searchable snapshot), no objection.
STRICT_TOOLS_PERSONA = (STRICT_PERSONA + " Your working folder holds the repository exactly as it was at this "
                        "commit; read and search it to check anything you are not shown.")

ap = argparse.ArgumentParser()
ap.add_argument("--arm", choices=tuple(SEATS), required=True)
ap.add_argument("--workers", type=int, default=1)
ap.add_argument("--worker", type=int, default=0)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--claude-exe", default=os.environ.get("CLAUDE_CODE_EXECPATH"))
ap.add_argument("--set", default=str(HERE), help="folder holding items.jsonl; outputs go there too")
ap.add_argument("--only-approved-by", default="", metavar="TAG[,TAG]",
                help="review only items every listed run (<arm>[@<effort>] in the set) has reviewed and APPROVED: "
                     "WaRF's sequential early stop for a 'reject if any rejects' panel")
ap.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default=None,
                help="Claude CLI --effort for every call (default: the CLI's own); outputs go to <arm>@<effort>.w<k>.jsonl")
args = ap.parse_args()
SET = Path(args.set).resolve()
TAG = args.arm + (f"@{args.effort}" if args.effort else "")      # the output files' name
AGENT, PROVIDER, MODEL = SEATS[args.arm]
CLAUDE = args.arm.startswith("claude")
STANDARD = args.arm == "claude-standard"
PANEL = args.arm in ("claude-standard", "claude-x5")    # several seats, WaRF's default review

for name in [k for k in os.environ if k.upper().startswith("CLAUDE")]:
    del os.environ[name]
for name in ("WARF_PROVIDER", "WARF_MODEL", "ANTHROPIC_API_KEY"):
    if os.environ.get(name):
        sys.exit(f"{name} is set; unset it so that the profile's provider and model apply")
if CLAUDE:
    if not args.claude_exe:
        sys.exit("no Claude CLI: pass --claude-exe")
    os.environ["PATH"] = str(Path(args.claude_exe).parent) + os.pathsep + os.environ.get("PATH", "")
if STANDARD:                    # WaRF's documented way to put every default agent on one model
    os.environ["WARF_PROVIDER"], os.environ["WARF_MODEL"] = PROVIDER, MODEL
if args.arm in TOOL_ARMS:   # a searching agent takes longer than WaRF's default 120 s
    os.environ["WARF_TIMEOUT"] = "900"
if args.arm == "jev":
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as _key:
        for _name in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL"):
            if not os.environ.get(_name):
                try:
                    os.environ[_name] = winreg.QueryValueEx(_key, _name)[0]
                except FileNotFoundError:
                    pass
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set (neither in this process nor in the user's environment)")
sys.path.insert(0, str(EXP / "laya-five"))

from run_five import INPUT_LABEL  # noqa: E402  (also points WARF_HOME away from .warf/)
from run_laya_sweep import DEFAULT_PERSONA  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import (ClaudeCLIProvider, ProviderError, SystemOneProvider,  # noqa: E402
                            detect_default_provider, resolve_model)
from warf.state import (PERSONA_ADVOCATE, PERSONA_SKEPTIC, AgentProfile, default_profiles,  # noqa: E402
                        load_profiles, persona_hash, save_profiles)


class _IsolatedSubprocess:
    """Stands in for the subprocess module inside warf.providers: the Claude CLI's command gets the
    isolation flags and a working folder (empty, or the item's snapshot for the search checker). Any
    other command stops the run."""

    def __init__(self, exe: str, flags: list) -> None:
        self.exe = os.path.normcase(exe)
        self.flags = flags
        self.cwd = tempfile.mkdtemp(prefix="warf-planted-")

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, cmd, **kw):
        if not cmd or os.path.normcase(str(cmd[0])) != self.exe:
            sys.exit(f"unexpected command {cmd[:1]}: the isolation flags would not apply")
        return subprocess.run([cmd[0], *self.flags, *cmd[1:]], **{**kw, "cwd": self.cwd})


def make_snapshot(commit: str) -> str:
    """The repository as it was at `commit`, without .git and without SNAPSHOT_SKIP, in a new folder."""
    names = subprocess.run(["git", "--git-dir", str(GISMO / ".git"), "ls-tree", "--name-only", commit],
                           capture_output=True, text=True, check=True).stdout.split()
    keep = [n for n in names if n not in SNAPSHOT_SKIP]
    tar = subprocess.run(["git", "--git-dir", str(GISMO / ".git"), "archive", "--format=tar", commit, *keep],
                         capture_output=True, check=True).stdout
    # the long form of the temp folder: the CLI refuses short (8.3) names like TEYMUR~1 as suspicious
    folder = tempfile.mkdtemp(prefix="warf-snapshot-", dir=str(Path(tempfile.gettempdir()).resolve()))
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(folder, filter="data")
    return folder


class Tap:
    """The raw answer of every call of a review: Claude's reply text (with the agent it came from), or
    the decision model's body."""

    def __init__(self, agents: dict) -> None:
        self.calls: list[dict] = []
        tap = self
        if CLAUDE:
            original = ClaudeCLIProvider.complete

            def complete(provider, system, user, model, timeout):
                completion = original(provider, system, user, model, timeout)
                text = completion.text
                exact = text.split()[0].upper().rstrip(".,:") in ("APPROVE", "REJECT")
                if not exact and len(text) < 400 and NON_ANSWER.search(text):
                    raise ProviderError(f"the CLI answered without a vote: {text[:200]}")
                tap.calls.append({"agent": agents.get(system, "?"), "model": model, "sent_chars": len(user),
                                  "reply": text, "exact": exact})
                return completion

            ClaudeCLIProvider.complete = complete
        else:
            original = SystemOneProvider._post

            def _post(provider, request, timeout):
                body = original(provider, request, timeout)
                tap.calls.append({"sent_chars": len(json.loads(request.data)["state"]), "body": body})
                return body

            SystemOneProvider._post = _post


def ensure_profile() -> tuple[Path, dict]:
    """The arm's panel at uniform priors. Returns the path and {persona text: agent name}."""
    if STANDARD:                # WaRF's default profile; the environment picks provider and model
        profiles = default_profiles()
    elif args.arm == "claude-x5":   # the single agent's question asked by five identical seats
        profiles = [AgentProfile(name=f"{AGENT}-{k}", persona=DEFAULT_PERSONA, persona_hash=persona_hash(DEFAULT_PERSONA),
                                 provider=PROVIDER, model=MODEL) for k in range(1, 6)]
    else:
        persona = {"claude-strict": STRICT_PERSONA, "claude-advocate": PERSONA_ADVOCATE,
                   "claude-skeptic": PERSONA_SKEPTIC, "claude-commit-strict": STRICT_PERSONA,
                   "claude-verify": VERIFY_PERSONA,
                   "claude-verify-tools": VERIFY_TOOLS_PERSONA,
                   "claude-commit-strict-tools": STRICT_TOOLS_PERSONA}.get(args.arm, DEFAULT_PERSONA)
        evidence = {"claude-verify": "objection", "claude-verify-tools": "objection-search",
                    "claude-commit-strict-tools": "whole-commit-search",
                    **{a: "whole-commit" for a in COMMIT_ARMS if a not in TOOL_ARMS}}.get(args.arm)
        profiles = [AgentProfile(name=AGENT, persona=persona, persona_hash=persona_hash(persona),
                                 provider=PROVIDER, model=MODEL, evidence=evidence)]
    path = SET / "profiles" / f"{args.arm}.json"
    want = [(p.name, p.persona_hash, p.provider, p.model) for p in profiles]
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        if [(x["name"], persona_hash(x["persona"]), x.get("provider"), x.get("model")) for x in d] != want:
            sys.exit(f"{path} holds another panel")
    else:
        path.parent.mkdir(exist_ok=True)
        save_profiles(path, profiles)
    return path, {p.persona: p.name for p in profiles}


def main() -> None:
    profile_path, agents = ensure_profile()
    # a tagged seat reviews its own input (run_review's seat_inputs); for these single-seat arms that
    # input is the item's code, already swapped for the arm's own input below
    sources = {p.evidence for p in load_profiles(profile_path) if p.evidence}
    if STANDARD and (detect_default_provider(), resolve_model(detect_default_provider())) != (PROVIDER, MODEL):
        sys.exit("WaRF would not put the default agents on claude_cli/claude-opus-5-5")
    if CLAUDE:
        wrapper = _IsolatedSubprocess(str(Path(args.claude_exe)),
                                      (TOOL_ISOLATION if args.arm in TOOL_ARMS else ISOLATION)
                                      + (["--effort", args.effort] if args.effort else []))
        providers.subprocess = wrapper
    tap = Tap(agents)
    items = [json.loads(line) for line in (SET / "items.jsonl").open(encoding="utf-8")]
    label = INPUT_LABEL
    if args.arm in COMMIT_ARMS:
        whole = {r["id"]: r["code"] for r in map(json.loads, (SET / "commit_inputs.jsonl").open(encoding="utf-8"))}
        items = [{**it, "code": whole[it["id"]]} for it in items]
        label = COMMIT_LABEL
    if args.arm in ("claude-verify", "claude-verify-tools"):
        check = {r["id"]: r["code"] for r in map(json.loads, (SET / "verify_inputs.jsonl").open(encoding="utf-8"))}
        items = [{**it, "code": check[it["id"]]} for it in items if it["id"] in check]
        label = VERIFY_LABEL
    done = set()
    for path in SET.glob(f"{TAG}.w*.jsonl"):
        for line in path.open(encoding="utf-8"):
            done.add(json.loads(line)["planted"]["id"])
    jobs = [it for it in items if it["id"] not in done]
    for tag in filter(None, args.only_approved_by.split(",")):
        approved = set()
        for path in SET.glob(f"{tag}.w*.jsonl"):
            for line in path.open(encoding="utf-8"):
                r = json.loads(line)
                if r["decision"] == "APPROVE":
                    approved.add(r["planted"]["id"])
        jobs = [it for it in jobs if it["id"] in approved]     # not yet reviewed by `tag` counts as not approved
    jobs = [it for i, it in enumerate(jobs) if i % args.workers == args.worker]
    out_path = SET / f"{TAG}.w{args.worker}.jsonl"
    print(f"  {PROVIDER}/{MODEL}; worker {args.worker} of {args.workers}: {len(jobs)} reviews to run "
          f"({len(done)} done) -> {out_path.name}", flush=True)

    t_start, n, errors = time.time(), 0, 0
    with out_path.open("a", encoding="utf-8") as out:
        for it in jobs:
            if args.limit and n >= args.limit:
                break
            tap.calls.clear()
            snapshot = make_snapshot(it["commit"]) if args.arm in TOOL_ARMS else None
            if snapshot:
                wrapper.cwd = snapshot
            t0 = time.time()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = run_review(it["code"], it["domain"], profile_path, verbose=False, debate=False,
                                        input_label=label, context=it["context"], no_early_stop=not PANEL,
                                        seat_inputs={src: it["code"] for src in sources} or None)
            except Exception as exc:             # one review must not end the run; a lost login will
                errors += 1
                with (SET / "errors.jsonl").open("a", encoding="utf-8") as e:
                    e.write(json.dumps({"id": it["id"], "arm": TAG, "error": f"{type(exc).__name__}: {exc}"[:1000],
                                        "at": datetime.now(timezone.utc).isoformat()}) + "\n")
                print(f"  {it['id']}: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
                if errors >= MAX_ERRORS:
                    sys.exit(f"  worker {args.worker} stopping: {errors} consecutive errors")
                continue
            finally:
                if snapshot:
                    shutil.rmtree(snapshot, ignore_errors=True)
            errors = 0
            if PANEL:
                if len(tap.calls) != len(result.votes):
                    sys.exit(f"{it['id']}: {len(tap.calls)} calls vs {len(result.votes)} votes")
                for c, v in zip(tap.calls, result.votes):
                    if STANDARD and c["agent"] != v.agent_name:
                        sys.exit(f"{it['id']}: call {c['agent']} vs vote {v.agent_name}")
                    c["agent"] = v.agent_name    # x5: identical personas, so the seat comes from the order
            elif len(result.votes) != 1 or len(tap.calls) != 1:
                sys.exit(f"{it['id']}: {len(result.votes)} votes, {len(tap.calls)} calls")
            record = session_dict(result, artifact_path=f"{it['commit']}:{it['file']}", profile_name=f"planted-{args.arm}")
            record["planted"] = {"id": it["id"], "base": it["base"], "kind": it["kind"], "operator": it.get("operator"),
                                 "provider": PROVIDER, "model": MODEL, "effort": args.effort, "seconds": round(time.time() - t0, 2),
                                 **({"calls": list(tap.calls)} if PANEL else {"call": tap.calls[0]})}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 10 == 0:
                rate = (time.time() - t_start) / n
                print(f"  worker {args.worker}: {n}/{len(jobs)}  {rate:.1f} s per review, "
                      f"~{rate * (len(jobs) - n) / 60:.0f} min left", flush=True)
    print(f"  worker {args.worker} done: {n} reviews in {(time.time() - t_start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
