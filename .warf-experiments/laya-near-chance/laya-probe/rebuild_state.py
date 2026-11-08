"""Rebuild the exact state the sweep sent Laya for one (commit, file), and ask laya-serve."""
import json, sys, urllib.request
from pathlib import Path

WARF = Path(r"C:\workdir\warf\WaRF")
sys.path[:0] = [str(WARF), str(WARF / "tools")]
from run_laya_sweep import CONTEXT_LINES, DEFAULT_PERSONA, INPUT_LABEL, MAX_STATE_CHARS, git  # noqa: E402
from warf.cli import SUPPORTED_EXTENSIONS, _parse_diff  # noqa: E402
from warf.context_extractor import enrich_patch  # noqa: E402
from warf.providers import DECISION_CRITERIA, resolve_model  # noqa: E402

HOME = WARF / ".warf-experiments" / "laya-sweep"
URL = "http://127.0.0.1:8000/v1/systemone"
MODEL = resolve_model("laya", None)


def load_plan() -> dict:
    with (HOME / "plan.jsonl").open(encoding="utf-8") as f:
        return {e["sha"]: e for e in map(json.loads, f)}


_last: dict = {}


def patches(entry: dict) -> list:
    if _last.get("sha") != entry["sha"]:
        cwd = entry["worktree"] or entry["git_dir"]
        diff = git(entry["git_dir"], "show", f"-U{CONTEXT_LINES}", "--no-color", "--no-ext-diff",
                   "--src-prefix=a/", "--dst-prefix=b/", "--format=", entry["sha"], cwd=cwd)
        _last.clear()
        _last.update(sha=entry["sha"], patches=[(f, p) for f, p in _parse_diff(diff)
                                                 if Path(f).suffix in SUPPORTED_EXTENSIONS])
    return _last["patches"]


def frame(domain: str) -> tuple[str, str]:
    return f"Domain: {domain}\n\n{INPUT_LABEL}:\n```\n", "\n```"


def rebuild(entry: dict, path: str, domain: str, index: int = 0) -> str:
    """The orchestrator's user message for a decision agent, as the runner cut it."""
    hits = [p for f, p in patches(entry) if f == path]
    patch = hits[index]
    cwd = entry["worktree"] or entry["git_dir"]
    try:
        enriched = enrich_patch(cwd, entry["sha"], path, patch)
    except Exception:
        enriched = patch
    head, tail = frame(domain)
    room = MAX_STATE_CHARS - len(head) - len(tail)
    return head + (enriched if len(enriched) <= room else enriched[:room]) + tail


def ask(state: str) -> tuple[float, dict]:
    body = json.dumps({"model": MODEL, "state": state, "questions": {"verdict": {
        "type": "choice", "instructions": DEFAULT_PERSONA, "criteria": DECISION_CRITERIA}}}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())
    return float(out["answers"]["verdict"]["probabilities"]["REJECT"]), out.get("usage") or {}
