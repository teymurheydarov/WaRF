"""
WaRF CLI

Usage:
    py cli.py review <file-or-dir>  [--domain AUTO|LOGIC|SECURITY|PERFORMANCE]
                                    [--ground-truth APPROVE|REJECT]
                                    [--oracle DEVELOPER|SAST|TEST|COMPILER]
                                    [--debate]
                                    [--glob PATTERN]
                                    [--verbose]

    py cli.py weights   # show current agent weights
    py cli.py reset     # reset weights to uniform priors
"""
import argparse
import contextlib
import json
import os
import sys
import io
from dataclasses import dataclass
from pathlib import Path

# Let `py warf/cli.py` behave like `python -m warf.cli`. Run as a bare script
# there is no parent package and the relative imports below would fail, so
# put the directory that CONTAINS the package on sys.path and name the
# package. Installed, or via -m, __package__ is already set and this is a no-op.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"

# Force UTF-8 output on Windows (avoids cp1252 encoding errors)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import re
import time

from .orchestrator import run_review, apply_oracle, ReviewResult
from .state import (
    ORACLE_TIERS, default_profiles, load_profiles, save_profiles, reconcile_profiles,
    profile_path,
)
from .logger import (
    append_session, session_dict, load_lines, find_session, write_lines,
    result_from_session, oracle_entry, label_session,
    SessionNotFound, SessionAmbiguous, AlreadyLabelled,
)
from .detector import detect_domain
from .vcs import detect_vcs, get_diff, get_message
from .engine import omega_ci
from .context_extractor import enrich_patch
from .paths import (
    profiles_dir, sessions_path, html_dir, find_context, describe as describe_paths,
)
from . import providers as _providers

# Resolved once at import so everything in this process agrees on one data
# directory. See paths.py for the WARF_HOME / .warf/ / ~/.warf order.
SESSIONS_PATH = sessions_path()


def _profiles_path(name: str) -> Path:
    """Resolve a --profile argument to a file. Delegates to state.profile_path,
    which the MCP server uses too, so both resolve names identically."""
    return profile_path(name)
DOMAINS = ("LOGIC", "SECURITY", "PERFORMANCE")
_QUOTA_STOP = 3  # consecutive errors before auto-stopping

SUPPORTED_EXTENSIONS = frozenset({
    ".py", ".cpp", ".c", ".cc", ".cxx", ".h", ".hpp",
    ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".cs", ".kt",
})

_SKIP_DIRS = frozenset({
    "__pycache__", "node_modules", ".git", ".tox",
    "venv", ".venv", "dist", "build", ".mypy_cache",
})


@dataclass
class FileSummary:
    path: Path
    domain: str
    decision: str
    confidence: str
    sprt_lambda: float
    error: str | None = None
    record: dict | None = None   # full session dict, for --json


# ── machine-readable output ──────────────────────────────────────────────────

JSON_SCHEMA_VERSION = 1

# Confidence ordering used by --fail-on. A REJECT fails the build only when its
# confidence is at least as strong as the requested floor.
_CONF_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
FAIL_ON_CHOICES = ("HIGH", "MEDIUM", "LOW")
FAIL_ON_DEFAULT = "LOW"   # preserves historical behaviour: any REJECT exits 1


def _should_fail(decision: str, confidence: str, fail_on: str) -> bool:
    """True when this verdict should produce a non-zero exit code.

    --fail-on HIGH    fail only on REJECT [HIGH]
    --fail-on MEDIUM  fail on REJECT [HIGH|MEDIUM]
    --fail-on LOW     fail on any REJECT  (default)

    See warf/policy.md §2 — the routing table forbids acting on LOW, so CI
    gates should pass --fail-on HIGH rather than relying on the default.
    """
    if decision != "REJECT":
        return False
    return _CONF_RANK.get(confidence, 0) >= _CONF_RANK[fail_on]


@contextlib.contextmanager
def _quiet_stdout(json_mode: bool):
    """In --json mode send all human-facing output to stderr.

    stdout must carry the JSON document and nothing else, so it stays pipeable
    into jq or a calling agent. Redirecting the stream (rather than editing every
    print site) also captures output from orchestrator and the plot_* modules.
    """
    if json_mode:
        with contextlib.redirect_stdout(sys.stderr):
            yield
    else:
        yield


def _emit_json(payload: dict) -> None:
    """Write the single JSON document to real stdout."""
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()


# ── HTML refresh ─────────────────────────────────────────────────────────────

LEGACY_PROFILE = "legacy"   # sessions logged before the profile field existed


def _refresh_html(profile: str | None = None) -> None:
    """Regenerate all dashboard HTML files from sessions.jsonl. Zero API cost.

    profile restricts the input to one profile's sessions; "legacy" means the
    sessions logged before profiles were recorded, i.e. the original corpus the
    talk's charts were built from. Every plot module reads its own module-level
    SESSIONS path, so a filtered copy of the log is written to a temp file and
    the modules are pointed at it for the duration; the plots stay unaware of
    profiles.
    """
    import tempfile
    try:
        # Only pages that work on any session log belong here: a page that needs
        # particular sessions to exist fails for everyone whose log lacks them.
        from . import (
            plot_dashboard, plot_weights, plot_tokens, plot_reliability,
            plot_slide06, plot_slide13,
        )
        modules = [plot_dashboard, plot_weights, plot_tokens, plot_reliability,
                   plot_slide06, plot_slide13]

        tmp: Path | None = None
        kept: list[str] = []
        if profile:
            for line in load_lines():
                try:
                    have = json.loads(line).get("profile")
                except json.JSONDecodeError:
                    continue
                match = (have is None) if profile == LEGACY_PROFILE else (have == profile)
                if match:
                    kept.append(line)
            fd, name = tempfile.mkstemp(suffix=".jsonl", prefix="warf-sessions-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
            tmp = Path(name)
            for m in modules:
                m.SESSIONS = tmp

        try:
            for m in modules:
                m.main()
        finally:
            if tmp is not None:
                for m in modules:
                    m.SESSIONS = SESSIONS_PATH
                tmp.unlink(missing_ok=True)

        scope = f"  ({len(kept)} sessions, profile={profile})" if profile else ""
        print("  HTML updated -> dashboard + weight_trajectories + token_cost_chart "
              f"+ confidence_calibration + slide06 + why_not_two_agents{scope}")
    except Exception as exc:
        print(f"  [html] update skipped: {exc}", file=sys.stderr)


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_context(start: Path) -> str | None:
    """Project context for the agents; see paths.find_context, shared with the
    MCP server so a review gets the same warf_context.md either way."""
    return find_context(start)


def _discover_files(directory: Path, glob_pat: str | None) -> list[Path]:
    """Return sorted list of reviewable files under directory."""
    if glob_pat:
        return sorted(f for f in directory.glob(glob_pat) if f.is_file())
    files = []
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix not in SUPPORTED_EXTENSIONS:
            continue
        rel_parts = set(f.relative_to(directory).parts[:-1])
        if rel_parts & _SKIP_DIRS:
            continue
        if any(p.startswith(".") for p in rel_parts):
            continue
        files.append(f)
    return sorted(files)


def _run_single_file(
    file_path: Path,
    domain_arg: str,
    debate: bool,
    verbose: bool,
    demo: bool = False,
    reason: bool = False,
    context: str | None = None,
    profiles_path: Path | None = None,
    sast: bool = False,
    agents: list[str] | None = None,
    max_agents: int | None = None,
    no_early_stop: bool = False,
) -> tuple[ReviewResult, str]:
    """Read and review one file. Returns (result, domain_used)."""
    if profiles_path is None:
        profiles_path = _DEFAULT_PROFILE
    code = file_path.read_text(encoding="utf-8")
    if domain_arg == "AUTO":
        domain_used, domain_reason = detect_domain(file_path, code)
        if verbose:
            print(f"  Auto-detected domain: {domain_used}  ({domain_reason})")
    else:
        domain_used = domain_arg
    sast_path = file_path if sast else None
    result = run_review(code, domain_used, profiles_path, verbose=verbose, debate=debate, demo=demo, reason=reason, context=context, sast_path=sast_path, agents=agents, max_agents=max_agents, no_early_stop=no_early_stop)
    return result, domain_used


# ── single-file review ────────────────────────────────────────────────────────

def _cmd_review_file(args: argparse.Namespace, file_path: Path) -> None:
    json_mode = getattr(args, "json", False)
    fail_on   = getattr(args, "fail_on", FAIL_ON_DEFAULT)
    with _quiet_stdout(json_mode):
        record = _review_file_inner(args, file_path)

    if json_mode:
        _emit_json({
            "schema": JSON_SCHEMA_VERSION,
            "mode":   "file",
            "fail_on": fail_on,
            **record,
        })

    sys.exit(1 if _should_fail(record["decision"], record["confidence"], fail_on) else 0)


def _review_file_inner(args: argparse.Namespace, file_path: Path) -> dict:
    """Review one file, log it, and return the session record."""
    domain_arg    = (args.domain or "AUTO").upper()
    profiles_path = _profiles_path(args.profile)
    context       = _find_context(file_path.parent)

    demo_mode = getattr(args, "demo",    False)
    verbose   = getattr(args, "verbose", False) or (not demo_mode)

    print(f"\n=== WaRF Review: {file_path.name}  [{domain_arg}]  profile={args.profile} ===\n")
    if context:
        print(f"  [context] warf_context.md loaded ({len(context)} chars)\n")
    result, domain_used = _run_single_file(file_path, domain_arg, args.debate, verbose=verbose, demo=demo_mode, reason=getattr(args, "reason", False), context=context, profiles_path=profiles_path, sast=getattr(args, "sast", False), agents=getattr(args, "agents", None), max_agents=getattr(args, "max_agents", None), no_early_stop=getattr(args, "no_early_stop", False))

    print(f"\n{'-' * 42}")
    print(f"  DECISION  : {result.decision.value}")
    print(f"  CONFIDENCE: {result.confidence.value}")
    if result.normalised_score is not None:
        print(f"  SCORE     : {result.normalised_score:+.3f}")
    print(f"  L (SPRT)  : {result.sprt_lambda:+.3f}")
    if result.debate_votes:
        r1_map = {v.agent_name: v.vote for v in result.votes}
        changed = [v.agent_name for v in result.debate_votes
                   if v.vote != r1_map.get(v.agent_name)]
        print(f"  D2 L      : {result.debate_sprt_lambda:+.3f}")
        if result.debate_normalised_score is not None:
            print(f"  D2 SCORE  : {result.debate_normalised_score:+.3f}")
        print(f"  CHANGED   : {', '.join(changed) if changed else 'none'}")
    print(f"{'-' * 42}\n")

    updates = None
    x_star  = None
    oracle  = None

    if args.ground_truth:
        x_star = 1 if args.ground_truth.upper() == "APPROVE" else -1
        oracle = (args.oracle or "DEVELOPER").upper()
        print(f"Oracle update ({oracle}, x*={args.ground_truth.upper()}):")
        updates = apply_oracle(result, x_star, oracle, profiles_path, verbose=True)
        print()

    record = append_session(
        result,
        artifact_path=str(file_path),
        oracle_type=oracle,
        x_star=x_star,
        weight_updates=updates,
        profile_name=args.profile,
    )
    print(f"  Logged -> sessions.jsonl  (session {record['session_id']})")
    _refresh_html()

    return record


# ── multi-file review ─────────────────────────────────────────────────────────

def _cmd_review_dir(args: argparse.Namespace, directory: Path) -> None:
    json_mode = getattr(args, "json", False)
    fail_on   = getattr(args, "fail_on", FAIL_ON_DEFAULT)
    with _quiet_stdout(json_mode):
        summaries = _review_dir_inner(args, directory)

    n_fail = sum(1 for s in summaries
                 if _should_fail(s.decision, s.confidence, fail_on))

    if json_mode:
        _emit_json({
            "schema":  JSON_SCHEMA_VERSION,
            "mode":    "directory",
            "root":    str(directory),
            "fail_on": fail_on,
            "summary": {
                "total":   len(summaries),
                "approve": sum(1 for s in summaries if s.decision == "APPROVE"),
                "reject":  sum(1 for s in summaries if s.decision == "REJECT"),
                "error":   sum(1 for s in summaries if s.error),
                "failing": n_fail,
            },
            "reviews": [
                s.record if s.record else
                {"artifact": str(s.path), "decision": "ERROR", "error": s.error}
                for s in summaries
            ],
        })

    sys.exit(1 if n_fail else 0)


def _review_dir_inner(args: argparse.Namespace, directory: Path) -> list["FileSummary"]:
    """Review every supported file under directory; return one summary each."""
    glob_pat      = getattr(args, "glob", None)
    profiles_path = _profiles_path(args.profile)
    context       = _find_context(directory)
    all_files     = _discover_files(directory, glob_pat)

    if not all_files:
        print(f"No supported files found in {directory}", file=sys.stderr)
        return []

    # Skip files already successfully reviewed (errors are retried)
    reviewed = _load_reviewed_paths()
    files = [f for f in all_files if str(f) not in reviewed]
    n_skipped = len(all_files) - len(files)

    if not files:
        print(f"All {len(all_files)} file(s) already reviewed. Nothing to do.")
        return []

    if context:
        print(f"  [context] warf_context.md loaded ({len(context)} chars)")

    if len(all_files) > 20 and not getattr(args, "json", False):
        skip_note = f"  ({n_skipped} already reviewed, {len(files)} remaining)" if n_skipped else ""
        print(f"Found {len(all_files)} files in {directory}.{skip_note}")
        try:
            answer = input("Continue? (y/N) ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            return []
    elif n_skipped:
        print(f"  Skipping {n_skipped} already-reviewed file(s).")

    verbose_each = getattr(args, "verbose", False)
    domain_arg   = (args.domain or "AUTO").upper()
    name_w       = max(len(f.name) for f in files)

    print(f"\n=== WaRF Review: {directory}  [{len(files)} file(s)] ===\n")

    summaries: list[FileSummary] = []
    consecutive_errors = 0
    stopped_early = False

    try:
        for file_path in files:
            print(f"  {file_path.name:<{name_w}}  ...", end="", flush=True)

            if verbose_each:
                print()

            try:
                result, domain_used = _run_single_file(
                    file_path, domain_arg, args.debate, verbose=verbose_each, context=context, profiles_path=profiles_path, sast=getattr(args, "sast", False), agents=getattr(args, "agents", None), max_agents=getattr(args, "max_agents", None),
                )
                consecutive_errors = 0
            except Exception as exc:
                print(f"\r  {file_path.name:<{name_w}}  ERROR: {exc}")
                summaries.append(FileSummary(
                    path=file_path, domain="?", decision="ERROR",
                    confidence="?", sprt_lambda=0.0, error=str(exc),
                ))
                consecutive_errors += 1
                if consecutive_errors >= _QUOTA_STOP:
                    stopped_early = True
                    break
                continue

            flag = "  ← REJECT" if result.decision.value == "REJECT" else ""
            line = (
                f"\r  {file_path.name:<{name_w}}"
                f"  [{domain_used:<10}]"
                f"  {result.decision.value:<7}"
                f"  {result.confidence.value:<6}"
                f"  L={result.sprt_lambda:+.3f}"
                f"{flag}"
            )
            print(line)

            record = append_session(
                result,
                artifact_path=str(file_path),
                oracle_type=None,
                x_star=None,
                weight_updates=None,
                profile_name=args.profile,
            )

            summaries.append(FileSummary(
                path=file_path,
                domain=domain_used,
                decision=result.decision.value,
                confidence=result.confidence.value,
                sprt_lambda=result.sprt_lambda,
                record=record,
            ))

    except KeyboardInterrupt:
        print("\n")
        stopped_early = True

    # ── early-stop notice ─────────────────────────────────────────────────────
    if stopped_early:
        processed = {s.path for s in summaries}
        remaining = [f for f in files if f not in processed]
        if consecutive_errors >= _QUOTA_STOP:
            print(f"\n⚠  Stopped: {consecutive_errors} consecutive errors — quota likely exhausted.")
        else:
            print(f"  Stopped by user.")
        if remaining:
            print(f"  {len(remaining)} file(s) not yet reviewed.")
            print(f"  Resume after quota resets with:")
            print(f'    py cli.py review "{directory}"')

    # ── summary ───────────────────────────────────────────────────────────────
    n_reject  = sum(1 for s in summaries if s.decision == "REJECT")
    n_approve = sum(1 for s in summaries if s.decision == "APPROVE")
    n_error   = sum(1 for s in summaries if s.error)

    bar = "━" * 50
    print(f"\n{bar}")
    print(f"  Total   : {len(summaries)}")
    print(f"  APPROVE : {n_approve}")
    print(f"  REJECT  : {n_reject}" + ("  ← needs review" if n_reject else ""))
    if n_error:
        print(f"  ERROR   : {n_error}")

    if n_reject:
        print()
        print("  Flagged:")
        for s in summaries:
            if s.decision == "REJECT":
                rel = s.path.relative_to(directory)
                print(f"    {rel}  [{s.domain}]  {s.confidence}  L={s.sprt_lambda:+.3f}")

    _refresh_html()
    print(f"{bar}\n")
    return summaries


# ── commit review ────────────────────────────────────────────────────────────

def _parse_diff(diff_text: str) -> list[tuple[str, str]]:
    """Split unified diff into (filepath, patch_text) per file. Handles git and SVN format."""
    if "diff --git " in diff_text:
        chunks = re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE)
        result = []
        for chunk in chunks:
            if not chunk.startswith("diff --git "):
                continue
            m = re.match(r"diff --git a/.+ b/(.+)", chunk)
            if m:
                result.append((m.group(1).strip(), chunk))
        return result
    # SVN format: sections start with "Index: path"
    chunks = re.split(r"(?=^Index: )", diff_text, flags=re.MULTILINE)
    result = []
    for chunk in chunks:
        if not chunk.startswith("Index: "):
            continue
        m = re.match(r"Index: (.+)", chunk)
        if m:
            result.append((m.group(1).strip(), chunk))
    return result


def _load_reviewed_paths() -> set[str]:
    """Return artifact paths that already have a decision in sessions.jsonl."""
    reviewed: set[str] = set()
    if not SESSIONS_PATH.exists():
        return reviewed
    with SESSIONS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                if s.get("decision") and s.get("artifact"):
                    reviewed.add(s["artifact"])
            except json.JSONDecodeError:
                pass
    return reviewed


def _cmd_review_commit(args: argparse.Namespace) -> None:
    json_mode = getattr(args, "json", False)
    fail_on   = getattr(args, "fail_on", FAIL_ON_DEFAULT)
    with _quiet_stdout(json_mode):
        summaries = _review_commit_inner(args)

    n_fail = sum(1 for s in summaries
                 if _should_fail(s.decision, s.confidence, fail_on))

    if json_mode:
        _emit_json({
            "schema":  JSON_SCHEMA_VERSION,
            "mode":    "commit",
            "commit":  args.commit,
            "repo":    args.repo,
            "fail_on": fail_on,
            "summary": {
                "total":   len(summaries),
                "approve": sum(1 for s in summaries if s.decision == "APPROVE"),
                "reject":  sum(1 for s in summaries if s.decision == "REJECT"),
                "error":   sum(1 for s in summaries if s.error),
                "failing": n_fail,
            },
            "reviews": [
                s.record if s.record else
                {"artifact": str(s.path), "decision": "ERROR", "error": s.error}
                for s in summaries
            ],
        })

    sys.exit(1 if n_fail else 0)


def _review_commit_inner(args: argparse.Namespace) -> list["FileSummary"]:
    """Review every supported file changed in one commit; return one summary each."""
    repo   = Path(args.repo).resolve()
    commit = args.commit
    ctx    = args.context
    domain_arg = (args.domain or "AUTO").upper()

    repo_str = str(repo) if repo.exists() else args.repo
    if repo.exists() and not repo.is_dir():
        print(f"Error: repo path is not a directory: {repo}", file=sys.stderr)
        raise SystemExit(2)

    vcs           = detect_vcs(repo_str)
    profiles_path = _profiles_path(args.profile)
    context       = _find_context(repo) if repo.exists() else None
    try:
        diff_text = get_diff(repo_str, commit, ctx)
    except RuntimeError as exc:
        print(f"Error getting diff: {exc}", file=sys.stderr)
        raise SystemExit(2)

    patches = _parse_diff(diff_text)
    supported = [(f, p) for f, p in patches if Path(f).suffix in SUPPORTED_EXTENSIONS]

    if not supported:
        print("No supported source files changed in this commit.")
        return []

    short = commit[:8] if vcs == "git" else f"r{commit}"
    name_w = max(len(Path(f).name) for f, _ in supported)
    print(f"\n=== WaRF {vcs.upper()} Review: {short}  [{len(supported)} file(s)]  profile={args.profile} ===\n")
    if context:
        print(f"  [context] warf_context.md loaded ({len(context)} chars)\n")

    reviewed_paths = _load_reviewed_paths()

    summaries: list[FileSummary] = []
    consecutive_errors = 0
    stopped_early = False

    try:
        for filepath, patch in supported:
            fpath = Path(filepath)

            if not getattr(args, "force", False) and f"{commit}:{filepath}" in reviewed_paths:
                print(f"  {fpath.name:<{name_w}}  [already reviewed — skipped]")
                continue

            verbose_review = getattr(args, "verbose", False)
            demo_review    = getattr(args, "demo",    False)
            rich_output    = verbose_review or demo_review

            if domain_arg == "AUTO":
                domain_used, _ = detect_domain(fpath, patch)
            else:
                domain_used = domain_arg

            if rich_output:
                print(f"\n  ── {filepath}  [{domain_used}]")
            else:
                print(f"  {fpath.name:<{name_w}}  ...", end="", flush=True)

            t_file = time.time()
            enriched = enrich_patch(repo_str, commit, filepath, patch) if vcs == "git" else patch
            try:
                result = run_review(
                    enriched, domain_used, profiles_path,
                    verbose=verbose_review,
                    debate=args.debate,
                    input_label="Patch under review (unified diff)",
                    debug=getattr(args, "debug", False),
                    demo=demo_review,
                    reason=getattr(args, "reason", False),
                    context=context,
                    agents=getattr(args, "agents", None),
                    max_agents=getattr(args, "max_agents", None),
                )
                consecutive_errors = 0
            except Exception as exc:
                elapsed = time.time() - t_file
                if rich_output:
                    print(f"  ERROR ({elapsed:.0f}s): {exc}")
                else:
                    print(f"\r  {fpath.name:<{name_w}}  ERROR ({elapsed:.0f}s): {exc}")
                summaries.append(FileSummary(
                    path=fpath, domain="?", decision="ERROR",
                    confidence="?", sprt_lambda=0.0, error=str(exc),
                ))
                consecutive_errors += 1
                if consecutive_errors >= _QUOTA_STOP:
                    stopped_early = True
                    break
                continue

            elapsed = time.time() - t_file
            flag = "  ← REJECT" if result.decision.value == "REJECT" else ""
            if rich_output:
                print(
                    f"  {result.decision.value:<7} [{result.confidence.value}]"
                    f"  L={result.sprt_lambda:+.3f}  ({elapsed:.0f}s){flag}"
                )
            else:
                print(
                    f"\r  {fpath.name:<{name_w}}"
                    f"  [{domain_used:<10}]"
                    f"  {result.decision.value:<7}"
                    f"  {result.confidence.value:<6}"
                    f"  L={result.sprt_lambda:+.3f}"
                    f"  ({elapsed:.0f}s){flag}"
                )
            oracle_verdict = getattr(args, "oracle", None)
            x_star_val = None
            oracle_type_val = None
            oracle_updates = None
            if oracle_verdict:
                x_star_val = 1 if oracle_verdict == "APPROVE" else -1
                oracle_type_val = "DEVELOPER"
                if rich_output:
                    print(f"  Oracle ({oracle_verdict}):")
                oracle_updates = apply_oracle(
                    result, x_star_val, oracle_type_val, profiles_path, verbose=rich_output
                )

            record = append_session(result, artifact_path=f"{commit}:{filepath}",
                           oracle_type=oracle_type_val, x_star=x_star_val,
                           weight_updates=oracle_updates, profile_name=args.profile)
            summaries.append(FileSummary(
                path=fpath, domain=domain_used,
                decision=result.decision.value,
                confidence=result.confidence.value,
                sprt_lambda=result.sprt_lambda,
                record=record,
            ))

    except KeyboardInterrupt:
        print("\n")
        stopped_early = True

    if stopped_early:
        processed = {s.path for s in summaries}
        remaining = [Path(f) for f, _ in supported if Path(f) not in processed]
        if consecutive_errors >= _QUOTA_STOP:
            print(f"\n⚠  Stopped: {consecutive_errors} consecutive errors — quota likely exhausted.")
        else:
            print("  Stopped by user.")
        if remaining:
            print(f"  {len(remaining)} file(s) not reviewed.")

    n_reject  = sum(1 for s in summaries if s.decision == "REJECT")
    n_approve = sum(1 for s in summaries if s.decision == "APPROVE")
    n_error   = sum(1 for s in summaries if s.error)
    bar = "━" * 50
    print(f"\n{bar}")
    print(f"  {'Revision' if vcs == 'svn' else 'Commit':<8}: {short}")
    print(f"  Total   : {len(summaries)}")
    print(f"  APPROVE : {n_approve}")
    print(f"  REJECT  : {n_reject}" + ("  ← needs review" if n_reject else ""))
    if n_error:
        print(f"  ERROR   : {n_error}")
    if n_reject:
        print("\n  Flagged:")
        for s in summaries:
            if s.decision == "REJECT":
                print(f"    {s.path}  [{s.domain}]  {s.confidence}  L={s.sprt_lambda:+.3f}")
    _refresh_html()
    print(f"{bar}\n")
    return summaries


# ── dispatch ──────────────────────────────────────────────────────────────────

def cmd_review(args: argparse.Namespace) -> None:
    file_path = Path(args.file)
    if not file_path.exists():
        # Exit 2, not 1: the review never happened. Exit 1 is reserved for a
        # REJECT verdict. See warf/policy.md section 2.
        print(f"Error: not found: {file_path}", file=sys.stderr)
        sys.exit(2)

    if file_path.is_dir():
        _cmd_review_dir(args, file_path)
    else:
        _cmd_review_file(args, file_path)


_PERSONA_STATUS = {
    None:       "ok",          # hash matches the text: weights describe this agent
    "stamped":  "unstamped",   # no provenance recorded yet; next review records it
    "retired":  "CHANGED",     # text edited; next review retires these weights
    "restored": "reverted",    # text matches a parked version; next review restores it
}


def cmd_weights(args: argparse.Namespace) -> None:
    pp = _profiles_path(args.profile)
    # A display command must not rewrite the profile as a side effect, so load
    # without reconciling and show what the next review WOULD do instead.
    profiles = load_profiles(pp, reconcile=False)
    pending  = {e.agent: e for e in reconcile_profiles(profiles, apply=False)}

    if getattr(args, "reconcile", False) and pending:
        events = reconcile_profiles(profiles, apply=True)
        save_profiles(pp, profiles)
        for e in events:
            print(f"  [persona] {e.describe()}", file=sys.stderr)
        pending = {}

    def status(p) -> str:
        e = pending.get(p.name)
        return _PERSONA_STATUS[e.kind if e else None]

    if getattr(args, "json", False):
        _emit_json({
            "schema":  JSON_SCHEMA_VERSION,
            "mode":    "weights",
            "profile": args.profile,
            "path":    str(pp),
            "agents": [
                {
                    "agent":            p.name,
                    "domain":           domain,
                    "alpha":            w.alpha,
                    "beta":             w.beta,
                    "omega":            round(w.omega, 4),
                    "ci_95":            [round(v, 4) for v in omega_ci(w.alpha, w.beta)],
                    "persona_hash":     p.persona_hash,
                    "persona_status":   status(p),
                    "retired_versions": len(p.retired),
                }
                for p in profiles for domain, w in p.weights.items()
            ],
            "pending_reconcile": [
                {"agent": e.agent, "kind": e.kind,
                 "old_hash": e.old_hash, "new_hash": e.new_hash}
                for e in pending.values()
            ],
        })
        return

    print(f"\nProfile: {args.profile}  ({pp})")
    print(f"\n{'Agent':<12}  {'Domain':<14}  {'α':>6}  {'β':>6}  {'ω':>7}  {'95% CI':>13}  {'persona':<12}  status")
    print("-" * 96)
    for p in profiles:
        for domain, w in p.weights.items():
            lo, hi = omega_ci(w.alpha, w.beta)
            ci = f"[{lo:.3f}, {hi:.3f}]"
            print(f"{p.name:<12}  {domain:<14}  {w.alpha:>6.2f}  {w.beta:>6.2f}  {w.omega:>7.3f}  {ci:>13}"
                  f"  {(p.persona_hash or '-'):<12}  {status(p)}")
    if pending:
        changed = [e.agent for e in pending.values() if e.kind == "retired"]
        print()
        if changed:
            print(f"  ! {', '.join(changed)}: persona text no longer matches the weights.")
            print(f"    The next review will retire these weights and restart the agent")
            print(f"    at uniform priors. Old weights are kept under their hash.")
        print(f"  Apply now:  warf weights --reconcile --profile {args.profile}")
    print()


def cmd_label(args: argparse.Namespace) -> None:
    """Attach developer ground truth to a past session and update the weights.

    This is the learning loop: a review on its own changes nothing, the label
    is what moves alpha/beta. See warf/policy.md §7.
    """
    json_mode     = getattr(args, "json", False)
    profiles_path = _profiles_path(args.profile)

    # The work is logger.label_session, shared with the MCP server; this wrapper
    # only renders the outcome for a terminal or as JSON and maps failures to
    # exit codes.
    try:
        with _quiet_stdout(json_mode):
            out = label_session(
                args.verdict, profiles_path,
                session_id=args.session_id, artifact=args.artifact,
                oracle_type=args.oracle, force=args.force, verbose=True,
            )
    except SessionNotFound as exc:
        _fail_label(json_mode, str(exc))
    except AlreadyLabelled as exc:
        s = exc.session
        _fail_label(
            json_mode,
            f"session {s['session_id'][:8]}… already has an oracle label "
            f"(x*={s['oracle']['x_star_label']}). Re-labelling applies a second "
            f"weight update and cannot be undone. Pass --force to proceed.",
            error="already_labelled",
        )
    except SessionAmbiguous as exc:
        candidates = [
            {
                "session_id": s["session_id"],
                "artifact":   s["artifact"],
                "decision":   s["decision"],
                "confidence": s["confidence"],
                "labelled":   "oracle" in s,
            }
            for _, s in exc.matches
        ]
        if json_mode:
            _emit_json({
                "schema": JSON_SCHEMA_VERSION,
                "mode":   "label",
                "ok":     False,
                "error":  "ambiguous_selector",
                "message": f"{len(candidates)} sessions matched; narrow the selector",
                "candidates": candidates,
            })
            sys.exit(2)
        print("Multiple sessions match — narrow the selector:\n", file=sys.stderr)
        for c in candidates:
            tag = " [already labelled]" if c["labelled"] else ""
            print(f"  {c['session_id'][:8]}…  {c['artifact']}"
                  f"  {c['decision']} [{c['confidence']}]{tag}", file=sys.stderr)
        sys.exit(2)

    with _quiet_stdout(json_mode):
        print(f"\nSession  : {out['artifact']}")
        print(f"Decision : {out['decision']} [{out['confidence']}]   domain={out['domain']}")
        print(f"Oracle   : {out['oracle']['type']}   x*={out['oracle']['x_star_label']}   "
              f"gamma={out['oracle']['gamma']}")
        if out["relabelled"]:
            print("Preserved-> sessions.jsonl  (original oracle entry kept; weights updated again)")
        else:
            print("Updated  -> sessions.jsonl")
        print(f"Saved    -> {profiles_path}")
        _refresh_html()

    if json_mode:
        _emit_json({"schema": JSON_SCHEMA_VERSION, "mode": "label", "ok": True, **out})
    sys.exit(0)


def _fail_label(json_mode: bool, message: str, error: str = "not_found") -> None:
    """Report a label failure and exit 2."""
    if json_mode:
        _emit_json({
            "schema": JSON_SCHEMA_VERSION,
            "mode":   "label",
            "ok":     False,
            "error":  error,
            "message": message,
        })
    else:
        print(f"Error: {message}", file=sys.stderr)
    sys.exit(2)


def cmd_providers(args: argparse.Namespace) -> None:
    """Show which model backend the current environment would use, and per-agent overrides."""
    info = _providers.describe()
    pp = _profiles_path(args.profile)
    profiles = load_profiles(pp)

    agents = [
        {
            "agent":    p.name,
            "provider": p.provider or f"({info['default_provider']})",
            "model":    p.model or f"({_providers.resolve_model(p.provider or info['default_provider'])})",
            "explicit": bool(p.provider or p.model),
        }
        for p in profiles
    ]

    if getattr(args, "json", False):
        _emit_json({
            "schema": JSON_SCHEMA_VERSION,
            "mode":   "providers",
            "profile": args.profile,
            **info,
            "agents": agents,
        })
        return

    print(f"\n  Default provider : {info['default_provider']}")
    print(f"  Default model    : {info['default_model']}")
    if info["claude_exe"]:
        print(f"  claude binary    : {info['claude_exe']}")
    print(f"  OpenAI base URL  : {info['base_url']}")

    print(f"\n  Available backends:")
    for name, ok in info["available"].items():
        mark = "yes" if ok else "no "
        note = "" if ok else "   (no credential / binary found)"
        print(f"    {name:<16} {mark}{note}")

    print(f"\n  Environment:")
    for k, v in info["env"].items():
        print(f"    {k:<20} {v if v else '-'}")

    print(f"\n  Panel ({args.profile}):  values in (parentheses) are inherited defaults")
    print(f"    {'AGENT':<16}{'PROVIDER':<22}{'MODEL'}")
    for a in agents:
        print(f"    {a['agent']:<16}{a['provider']:<22}{a['model']}")
    print()


def cmd_reset(args: argparse.Namespace) -> None:
    pp = _profiles_path(args.profile)
    save_profiles(pp, default_profiles())
    print(f"Profile '{args.profile}' reset to uniform priors (α=1.0, β=1.0, ω=0.500).")


_CONTEXT_TEMPLATE = """\
# WaRF Project Context — {name}

## What this project does
[One paragraph describing the project purpose and main components.]

## Stack
[Languages, frameworks, key libraries.]

## Key conventions
[Naming, structure, patterns the agents should know about.]

## What to flag
[Domain-specific concerns: security boundaries, data integrity invariants, etc.]

## Known false positives to ignore
[Patterns that look suspicious but are intentional.]
"""


def cmd_init_context(args: argparse.Namespace) -> None:
    dest = Path(args.path).resolve()
    if not dest.is_dir():
        print(f"Error: not a directory: {dest}", file=sys.stderr)
        sys.exit(1)
    out = dest / "warf_context.md"
    if out.exists() and not args.force:
        print(f"Already exists: {out}")
        print("Use --force to overwrite.")
        sys.exit(0)
    out.write_text(_CONTEXT_TEMPLATE.format(name=dest.name), encoding="utf-8")
    print(f"Created: {out}")
    print("Edit it to describe the project, then WaRF will inject it into every agent prompt.")


# ── argument parser ───────────────────────────────────────────────────────────

def main() -> None:
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="warf",
        description="WaRF — Weighted n-Agent Reliability Framework",
    )
    parser.add_argument("--version", action="version", version=f"warf {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_review = sub.add_parser("review", help="Review a file or directory")
    p_review.add_argument(
        "file",
        help="Path to a source file, or a directory to review all matching files",
    )
    p_review.add_argument(
        "--domain",
        default="AUTO",
        choices=["AUTO", *DOMAINS],
        help="Review domain (default: AUTO)",
    )
    p_review.add_argument(
        "--ground-truth",
        choices=["APPROVE", "REJECT"],
        metavar="APPROVE|REJECT",
        help="Developer verdict — triggers Bayesian weight update (single-file only)",
    )
    p_review.add_argument(
        "--oracle",
        choices=list(ORACLE_TIERS),
        default="DEVELOPER",
        help="Oracle type (default: DEVELOPER)",
    )
    p_review.add_argument(
        "--debate",
        action="store_true",
        default=False,
        help="Enable debate Round 2 when SPRT pool exhausts without firing",
    )
    p_review.add_argument(
        "--glob",
        metavar="PATTERN",
        default=None,
        help="Glob pattern to filter files in directory mode (e.g. '*.py')",
    )
    p_review.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show full per-agent output including reasoning and time analysis",
    )
    p_review.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Live per-agent display with ω bars and running λ (no full reasoning)",
    )
    p_review.add_argument(
        "--reason",
        action="store_true",
        default=False,
        help="Show 2-line reasoning excerpt per agent in --demo mode",
    )
    p_review.add_argument(
        "--profile",
        default="default",
        metavar="NAME",
        help="Weight profile to use (default: default); stored as <data dir>/profiles/NAME.json, see 'warf paths'",
    )
    p_review.add_argument(
        "--sast",
        action="store_true",
        default=False,
        help="Run Bandit as a 6th voting agent before LLM agents (SECURITY domain only). Requires: pip install bandit",
    )
    p_review.add_argument(
        "--agents",
        metavar="NAME[,NAME...]",
        default=None,
        type=lambda s: [n.strip().upper() for n in s.split(",") if n.strip()],
        help="Explicit comma-separated agent names to use (e.g. SKEPTIC,AUDITOR). Overrides --max-agents.",
    )
    p_review.add_argument(
        "--max-agents",
        metavar="N",
        dest="max_agents",
        type=int,
        default=None,
        help="Use only the top-N agents ranked by ω for the selected domain.",
    )
    p_review.add_argument(
        "--no-early-stop",
        dest="no_early_stop",
        action="store_true",
        default=False,
        help="Poll every agent even after the SPRT boundary is crossed. The verdict is "
             "unchanged; use this when measuring per-agent behaviour, since early "
             "stopping under-samples low-weight agents.",
    )
    p_review.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit the session record as JSON on stdout; all other output goes to stderr.",
    )
    p_review.add_argument(
        "--fail-on",
        dest="fail_on",
        choices=FAIL_ON_CHOICES,
        default=FAIL_ON_DEFAULT,
        help=("Minimum confidence at which a REJECT sets exit code 1 "
              f"(default: {FAIL_ON_DEFAULT}). Use HIGH for CI gates — see warf/policy.md §2."),
    )

    p_commit = sub.add_parser("review-commit", help="Review changed files in a git commit")
    p_commit.add_argument("commit", help="Commit hash to review")
    p_commit.add_argument(
        "--repo", default=".",
        help="Path to the git repository (default: current directory)",
    )
    p_commit.add_argument(
        "--context", type=int, default=30, metavar="N",
        help="Lines of context around each diff hunk (default: 30)",
    )
    p_commit.add_argument(
        "--domain", default="AUTO", choices=["AUTO", *DOMAINS],
        help="Review domain (default: AUTO)",
    )
    p_commit.add_argument(
        "--debate", action="store_true", default=False,
        help="Enable debate Round 2",
    )
    p_commit.add_argument(
        "--debug", action="store_true", default=False,
        help="Write agent inputs and subprocess output to warf/debug.log",
    )
    p_commit.add_argument(
        "--force", action="store_true", default=False,
        help="Re-review files even if already in sessions.jsonl",
    )
    p_commit.add_argument(
        "--verbose", action="store_true", default=False,
        help="Show full per-agent reasoning and time analysis for each file",
    )
    p_commit.add_argument(
        "--demo", action="store_true", default=False,
        help="Live per-agent display with ω bars and running λ (no full reasoning)",
    )
    p_commit.add_argument(
        "--reason", action="store_true", default=False,
        help="Show 2-line reasoning excerpt per agent in --demo mode",
    )
    p_commit.add_argument(
        "--oracle",
        choices=["APPROVE", "REJECT"],
        metavar="APPROVE|REJECT",
        default=None,
        help="Developer verdict — triggers Bayesian weight update for all reviewed files",
    )
    p_commit.add_argument(
        "--profile",
        default="default",
        metavar="NAME",
        help="Weight profile to use (default: default); stored as <data dir>/profiles/NAME.json, see 'warf paths'",
    )
    p_commit.add_argument(
        "--agents",
        metavar="NAME[,NAME...]",
        default=None,
        type=lambda s: [n.strip().upper() for n in s.split(",") if n.strip()],
        help="Explicit comma-separated agent names to use (e.g. SKEPTIC,AUDITOR). Overrides --max-agents.",
    )
    p_commit.add_argument(
        "--max-agents",
        metavar="N",
        dest="max_agents",
        type=int,
        default=None,
        help="Use only the top-N agents ranked by ω for the selected domain.",
    )
    p_commit.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit the session records as JSON on stdout; all other output goes to stderr.",
    )
    p_commit.add_argument(
        "--fail-on",
        dest="fail_on",
        choices=FAIL_ON_CHOICES,
        default=FAIL_ON_DEFAULT,
        help=("Minimum confidence at which a REJECT sets exit code 1 "
              f"(default: {FAIL_ON_DEFAULT}). Use HIGH for CI gates — see warf/policy.md §2."),
    )

    p_weights = sub.add_parser("weights", help="Show current agent weights")
    p_weights.add_argument("--profile", default="default", metavar="NAME", help="Profile to display")
    p_weights.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit the weight table as JSON on stdout.",
    )
    p_weights.add_argument(
        "--reconcile",
        action="store_true",
        default=False,
        help="Apply pending persona reconciliation now: record provenance for "
             "unstamped agents, retire weights whose persona text has changed, "
             "restore weights for a reverted persona. Without this flag the "
             "table only reports what the next review would do.",
    )

    p_label = sub.add_parser(
        "label",
        help="Attach developer ground truth to a past session and update weights",
    )
    p_label.add_argument(
        "session_id", nargs="?", default=None,
        help="Session id or unique prefix (from the review output). "
             "Omit if using --artifact.",
    )
    p_label.add_argument(
        "--artifact", default=None, metavar="SUBSTRING",
        help="Select the session by a case-insensitive substring of its artifact path",
    )
    p_label.add_argument(
        "--verdict", required=True, choices=["APPROVE", "REJECT"], type=str.upper,
        help="The true verdict, as established by a human or tool",
    )
    p_label.add_argument(
        "--oracle", default="DEVELOPER", choices=list(ORACLE_TIERS), type=str.upper,
        help="Oracle tier (default: DEVELOPER). Use DEVELOPER only for a human judgement.",
    )
    p_label.add_argument(
        "--profile", default="default", metavar="NAME",
        help="Weight profile to update (default: default)",
    )
    p_label.add_argument(
        "--force", action="store_true", default=False,
        help="Apply a second weight update to a session that is already labelled",
    )
    p_label.add_argument(
        "--json", action="store_true", default=False,
        help="Emit the weight deltas as JSON on stdout.",
    )

    p_prov = sub.add_parser(
        "providers",
        help="Show which model backend will be used, and any per-agent overrides",
    )
    p_prov.add_argument("--profile", default="default", metavar="NAME",
                        help="Profile whose panel to display")
    p_prov.add_argument("--json", action="store_true", default=False,
                        help="Emit the provider configuration as JSON on stdout.")

    p_reset = sub.add_parser("reset", help="Reset weights to uniform priors")
    p_reset.add_argument("--profile", default="default", metavar="NAME", help="Profile to reset")

    p_paths = sub.add_parser(
        "paths",
        help="Show where WaRF stores profiles, the session log and dashboards, and why",
    )
    p_paths.add_argument("--json", action="store_true", default=False,
                         help="Emit the resolved paths as JSON on stdout.")

    p_refresh = sub.add_parser(
        "refresh",
        help="Regenerate every dashboard from the session log (no API calls)",
    )
    p_refresh.add_argument(
        "--profile", default=None, metavar="NAME",
        help="Only include sessions of this profile. 'legacy' = sessions logged before "
             "profiles were recorded, i.e. the original corpus the talk charts were built "
             "from. Default: every session.",
    )

    p_init = sub.add_parser(
        "init",
        help="Create the data directory and a first profile; optionally choose the model backend",
    )
    scope = p_init.add_mutually_exclusive_group()
    scope.add_argument(
        "--local", action="store_true", default=False,
        help="Create a project-local .warf/ in the repo root (overrides the global store for this project)",
    )
    scope.add_argument(
        "--global", dest="global_", action="store_true", default=False,
        help="Use the per-user ~/.warf store even inside a project that has its own",
    )
    p_init.add_argument("--profile", default="default", metavar="NAME",
                        help="Profile to create (default: default)")
    p_init.add_argument("--provider", default=None, choices=list(_providers.PROVIDER_NAMES),
                        help="Model backend for every agent in the new profile")
    p_init.add_argument("--model", default=None, metavar="MODEL",
                        help="Model name for every agent in the new profile")
    p_init.add_argument("--force", action="store_true", default=False,
                        help="Overwrite an existing profile of that name")

    p_skill = sub.add_parser(
        "install-skill",
        help="Write the Claude Code skill (/warf) into .claude/skills, embedding the interpretation policy",
        description="Write the Claude Code skill. If a copy already exists it is not overwritten: "
                    "the command reports whether it is still current (exit 0) or out of date "
                    "(exit 1). --force regenerates it, keeping the invocation it was installed "
                    "with unless --command is given.",
    )
    p_skill.add_argument(
        "--global", dest="global_", action="store_true", default=False,
        help="Install for the user (~/.claude/skills) instead of this project",
    )
    p_skill.add_argument(
        "--command", dest="command_name", default=None, metavar="CMD",
        help="Invocation to bake into the skill (default: the one an existing copy already uses, "
             "else detected: warf, py -m warf, or python -m warf)",
    )
    p_skill.add_argument(
        "--print", dest="print_only", action="store_true", default=False,
        help="Print the skill to stdout instead of writing it",
    )
    p_skill.add_argument("--force", action="store_true", default=False,
                         help="Regenerate an existing SKILL.md (hand edits to it are lost)")

    sub.add_parser(
        "mcp",
        help='Run WaRF as an MCP server over stdio (needs: pip install "warf-review[mcp]")',
    )

    p_ctx = sub.add_parser("init-context", help="Create a warf_context.md template in a repo")
    p_ctx.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repo root to write warf_context.md into (default: current directory)",
    )
    p_ctx.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing warf_context.md",
    )

    args = parser.parse_args()

    if args.command == "label" and not (args.session_id or args.artifact):
        p_label.error("give a session id or --artifact to select the session")

    try:
        _dispatch(args, parser)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        # Exit 2, never 1. Exit 1 means "WaRF ran and rejected the code"; letting an
        # exception fall through as 1 would make a quota outage or a bad credential
        # indistinguishable from a genuine REJECT, and a CI gate would block the
        # build for a defect that does not exist. See warf/policy.md section 2.
        import traceback
        if os.environ.get("WARF_TRACEBACK"):
            traceback.print_exc()
        else:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            print("(set WARF_TRACEBACK=1 for the full traceback)", file=sys.stderr)
        sys.exit(2)


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "review":
        cmd_review(args)
    elif args.command == "review-commit":
        _cmd_review_commit(args)
    elif args.command == "weights":
        cmd_weights(args)
    elif args.command == "label":
        cmd_label(args)
    elif args.command == "providers":
        cmd_providers(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "init-context":
        cmd_init_context(args)
    elif args.command == "paths":
        cmd_paths(args)
    elif args.command == "refresh":
        cmd_refresh(args)
    elif args.command == "init":
        from .bootstrap import cmd_init
        cmd_init(args)
    elif args.command == "install-skill":
        from .bootstrap import cmd_install_skill
        cmd_install_skill(args)
    elif args.command == "mcp":
        # Imported lazily: the MCP extra is optional, and mcp_server must stay
        # importable without this module's stdout rewrap in the picture.
        from .mcp_server import main as mcp_main
        mcp_main()
    else:
        parser.print_help()


def cmd_paths(args: argparse.Namespace) -> None:
    """Show where WaRF reads and writes state, and how that was decided."""
    info = describe_paths()
    if getattr(args, "json", False):
        _emit_json({"schema": JSON_SCHEMA_VERSION, "mode": "paths", **info})
        return
    reason = {
        "env":     f"{info['env_var']} is set",
        "project": "a .warf/ directory was found walking up from the working directory",
        "global":  f"no {info['env_var']} and no .warf/ found: per-user default",
    }[info["tier"]]
    state = "exists" if info["exists"] else "does not exist yet; created on first write"
    print(f"\n  Data directory : {info['data_dir']}")
    print(f"                   [{info['tier']}] {reason}; {state}")
    print(f"  Profiles       : {info['profiles']}")
    print(f"  Session log    : {info['sessions']}")
    print(f"  Dashboards     : {info['html']}")
    opens = "opened in the browser after each review" if info["open_pages"] else "regenerated silently"
    print(f"                   {opens}  ({info['open_pages_why']})")
    print(f"  Working dir    : {info['cwd']}")
    print()
    print(f"  Per-project override : mkdir .warf   (in the project root; commit it to share calibration)")
    print(f"  One-off override     : {info['env_var']}=<dir> warf ...")
    print(f"  Open pages in browser: put {{\"open_pages\": true}} into settings.json in the data directory,")
    print(f"                         or set WARF_OPEN_BROWSER=1 for one run (off by default)")
    print()


def cmd_refresh(args: argparse.Namespace) -> None:
    """Regenerate every dashboard from the session log. Zero API cost.

    Note that any later review regenerates the dashboards from ALL sessions
    again; a --profile view is a snapshot, not a setting.
    """
    _refresh_html(getattr(args, "profile", None))
    print(f"  -> {html_dir()}")


if __name__ == "__main__":
    main()
