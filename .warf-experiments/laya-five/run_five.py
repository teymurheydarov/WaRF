"""WaRF's default five-agent panel (SKEPTIC, ADVOCATE, AUDITOR, TEST-FOCUSED, BOUNDARY) with
every agent played by Laya, on the 100 gismo6 commits of selection.jsonl.

Each file is reviewed the way the sweep reviewed it (tools/run_laya_sweep.py: `git show -U30`,
the diff split, enrich_patch, detect_domain, the "Patch under review (unified diff)" label),
then run_review with the five-agent profile, debate Round 2 on and early stopping off, so every
agent's vote is recorded in both rounds. The weights start at WaRF's uniform priors (omega 0.5)
and no oracle feedback is applied. One laya-serve process answers all five agents: Laya keeps
no state between requests, so each request is a separate instance of the model.

    python .warf-experiments/laya-five/run_five.py            # the panel, with debate
    python .warf-experiments/laya-five/run_five.py --plant    # control: planted lines, Round 1 only

Writes sessions.jsonl (WaRF session records plus a `five` block with each agent's full-precision
probabilities and Laya's truncation report per round) or controls.jsonl. Resumes where it
stopped. WARF_HOME is this directory, so nothing reaches the corpus in .warf/."""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WARF = HERE.parent.parent
os.environ["WARF_HOME"] = str(HERE)          # before warf is imported
sys.path[:0] = [str(WARF), str(WARF / "tools")]

from run_laya_sweep import CONTEXT_LINES, INPUT_LABEL, MAX_STATE_CHARS, git  # noqa: E402
from warf.cli import SUPPORTED_EXTENSIONS, _parse_diff  # noqa: E402
from warf.context_extractor import enrich_patch  # noqa: E402
from warf.detector import detect_domain  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.paths import find_context  # noqa: E402
from warf.providers import SystemOneProvider  # noqa: E402
from warf.state import default_profiles, persona_hash, save_profiles  # noqa: E402

PROFILE = "laya_five"
MODEL = "multilingual"
PLAN = WARF / ".warf-experiments" / "laya-sweep" / "plan.jsonl"
ADDED = re.compile(r"^\+(?!\+\+)(.*)$", re.M)
PLANTS = {                                   # the lines laya_controls.py planted
    "null dereference": "int* p = nullptr; *p = 42;",
    "BUG comment": "// BUG: this crashes on every call. Do not merge.",
}


def ensure_profile() -> Path:
    """WaRF's default panel, every agent on provider `laya`: current personas, uniform priors."""
    path = HERE / "profiles" / f"{PROFILE}.json"
    profiles = default_profiles()
    for p in profiles:
        p.provider, p.model = "laya", MODEL
    if path.exists():
        have = json.loads(path.read_text(encoding="utf-8"))
        want = [(p.name, p.persona_hash, p.provider, p.model) for p in profiles]
        got = [(d["name"], persona_hash(d["persona"]), d.get("provider"), d.get("model")) for d in have]
        if got != want:
            sys.exit(f"{path} holds another panel: {got}")
        return path
    save_profiles(path, profiles)
    return path


class Tap:
    """Keeps every /v1/systemone exchange of one review. WaRF renders each answer into a
    two-line vote text with two decimals; the scoring wants full precision and Laya's
    truncation report. The agents of a review are asked one after another."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        original = SystemOneProvider._post
        tap = self

        def _post(provider, request, timeout):
            body = original(provider, request, timeout)
            sent = json.loads(request.data)
            tap.calls.append({"instructions": sent["questions"]["verdict"]["instructions"],
                              "state": sent["state"], "body": body})
            return body

        SystemOneProvider._post = _post


def plant(code: str, text: str) -> str | None:
    """Insert a line after the first added line, with its indentation (as laya_controls.py);
    None for a patch that only removes lines, which laya_controls.py skipped too."""
    m = ADDED.search(code)
    if m is None:
        return None
    indent = re.match(r"\s*", m.group(1)).group(0) or "    "
    return code[:m.end()] + f"\n+{indent}{text}" + code[m.end():]


def file_patch(entry: dict, path: str) -> str:
    """The file's patch from `git show -U30`, split as review-commit splits it."""
    cwd = entry["worktree"] or entry["git_dir"]
    diff = git(entry["git_dir"], "show", f"-U{CONTEXT_LINES}", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", "--format=", entry["sha"], cwd=cwd)
    return [p for f, p in _parse_diff(diff) if f == path and Path(f).suffix in SUPPORTED_EXTENSIONS][0]


def has_code(patch: str) -> bool:
    """At least one added or removed line of a regular file: not a binary diff, a mode change,
    a pure rename, a symbolic link (an editor's lock file, say) or a submodule."""
    parts = patch.split("\n@@", 1)
    if len(parts) != 2 or re.search(r"mode 1[26]0000", parts[0]):
        return False
    return any(line.startswith(("+", "-")) for line in parts[1].splitlines()[1:])


def prepare(entry: dict, path: str) -> tuple[str, str, str | None, str | None]:
    """(code, domain, context, enrich_error) for one file, as the sweep built them."""
    cwd = entry["worktree"] or entry["git_dir"]
    patch = file_patch(entry, path)
    try:
        enriched, enrich_error = enrich_patch(cwd, entry["sha"], path, patch), None
    except Exception as exc:                 # the sweep's fallback for enrich_patch's IndexError
        enriched, enrich_error = patch, f"{type(exc).__name__}: {exc}"
    domain, _ = detect_domain(Path(path), patch)
    context = find_context(Path(cwd))
    ctx_section = f"Project context:\n{context}\n\n" if context else ""
    room = MAX_STATE_CHARS - len(f"Domain: {domain}\n\n{ctx_section}{INPUT_LABEL}:\n```\n") - len("\n```")
    return (enriched if len(enriched) <= room else enriched[:room]), domain, context, enrich_error


def answers(calls: list[dict], agents: dict) -> dict:
    """{round: {agent: answer}}; a call is Round 2 when its state carries the debate summary."""
    out: dict = {"round1": {}, "round2": {}}
    for c in calls:
        rnd = "round2" if "=== Round 1 Summary ===" in c["state"] else "round1"
        a = c["body"]["answers"]["verdict"]
        out[rnd][agents[c["instructions"]]] = {
            "choice": a["choice"], "p_reject": a["probabilities"]["REJECT"],
            "confidence": a.get("confidence"), "usage": c["body"].get("usage"),
            "state_chars": len(c["state"]),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plant", action="store_true", help="control: planted lines in the never-fixed changes")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profile_path = ensure_profile()
    agents = {p.persona: p.name for p in default_profiles()}
    plan = {}
    with PLAN.open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            plan[e["sha"]] = e
    selection = [json.loads(line) for line in (HERE / "selection.jsonl").open(encoding="utf-8")]
    out_path = HERE / ("controls.jsonl" if args.plant else "sessions.jsonl")
    done = set()
    if out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["five"]["id"], r["five"].get("plant")))
    jobs = [(s, name) for s in selection for name in (PLANTS if args.plant else [None])
            if (not args.plant or s["label"] == "APPROVE") and (s["id"], name) not in done]
    print(f"  {len(jobs)} reviews to run ({len(done)} done) -> {out_path.name}", flush=True)

    tap = Tap()
    t_start, n, skipped = time.time(), 0, 0
    with out_path.open("a", encoding="utf-8") as out:
        for s, name in jobs:
            if args.limit and n >= args.limit:
                break
            entry = plan[s["commit"]]
            code, domain, context, enrich_error = prepare(entry, s["file"])
            if domain != s["domain"]:
                sys.exit(f"{s['id']}: domain {domain}, the sweep had {s['domain']}")
            if name:
                code = plant(code, PLANTS[name])
                if code is None:
                    skipped += 1
                    continue
            tap.calls.clear()
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_review(code, domain, profile_path, verbose=False, debate=not args.plant,
                                    input_label=INPUT_LABEL, context=context, no_early_stop=True)
            seconds = time.time() - t0
            got = answers(tap.calls, agents)
            for rnd, votes in (("round1", result.votes), ("round2", result.debate_votes)):
                for v in votes:                       # the tap and WaRF's votes must agree
                    if (got[rnd][v.agent_name]["choice"] == "APPROVE") != (v.vote == 1):
                        sys.exit(f"{s['id']}: {rnd} {v.agent_name} vote {v.vote} vs {got[rnd][v.agent_name]}")
            if len(got["round1"]) != 5:
                sys.exit(f"{s['id']}: {len(got['round1'])} Round-1 answers")
            record = session_dict(result, artifact_path=f"{s['commit']}:{s['file']}", profile_name=PROFILE)
            record["five"] = {
                "id": s["id"], "commit": s["commit"], "file": s["file"], "label": s["label"],
                "plant": name, "enrich_error": enrich_error, "seconds": round(seconds, 2), **got,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 10 == 0:
                rate = (time.time() - t_start) / n
                print(f"  {n}/{len(jobs)}  {rate:.1f} s per review, ~{rate * (len(jobs) - n) / 60:.0f} min left",
                      flush=True)
    print(f"  done: {n} reviews in {(time.time() - t_start) / 60:.1f} min"
          + (f"; {skipped} skipped, the patch adds no line to plant after" if skipped else ""), flush=True)


if __name__ == "__main__":
    main()
