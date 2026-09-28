"""
WaRF as an MCP server over stdio.

Exposes review, label, weights, sessions and paths as typed tools, and the
interpretation policy as the server's instructions, a prompt and a resource, so
any MCP client — Claude Desktop, Cursor, Zed, a custom agent — can use WaRF
without a shell. Needs the optional extra:

    pip install "warf-review[mcp]"

Client configuration (stdio):

    {"mcpServers": {"warf": {"command": "python",
                             "args": ["-m", "warf.mcp_server"]}}}

On Windows without `python` on PATH use "py". Launch the client from the
project root, or set WARF_HOME in the server's env, so the right .warf/ is used.

stdout is the protocol channel, so every WaRF print is redirected to stderr
here. Dashboards are not regenerated after a review; run `warf refresh` for
that. This module deliberately never imports warf.cli, whose import-time
stdout rewrap would sit under the transport.
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

from . import __version__
from .bootstrap import policy_text
from .detector import detect_domain
from .engine import omega_ci
from .logger import (
    AlreadyLabelled, SessionAmbiguous, SessionNotFound,
    append_session, label_session, load_lines,
)
from .orchestrator import run_review
from .paths import describe as describe_paths, find_context
from .state import load_profiles, profile_path, reconcile_profiles


def _fastmcp():
    """The SDK's high-level server class: MCPServer in mcp 2.x, FastMCP in 1.x.

    The rename is the only difference this module cares about. Both take
    (name, instructions=...), expose tool() / prompt() / resource(uri)
    decorators and run(transport="stdio"), so one code path serves either SDK
    line and the extra needs no version pin. 2.x is tried first: importing the
    old path under 2.x raises with a migration message rather than quietly
    failing over.
    """
    try:
        from mcp.server.mcpserver import MCPServer      # mcp >= 2
        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP          # mcp 1.x
        return FastMCP
    except ImportError as exc:
        raise SystemExit(
            'The MCP server needs the optional dependency:  pip install "warf-review[mcp]"\n'
            f"  (import failed with: {exc})"
        ) from exc


def _strip_reasoning(session: dict) -> dict:
    """Copy of a session with the long per-agent reasoning removed."""
    s = dict(session)
    s["votes"] = [{k: v for k, v in vote.items() if k != "reasoning"}
                  for vote in s.get("votes", [])]
    if "debate" in s and s["debate"]:
        d = dict(s["debate"])
        d["votes"] = [{k: v for k, v in vote.items() if k != "reasoning"}
                      for vote in d.get("votes", [])]
        s["debate"] = d
    return s


def _new_server(cls):
    """Construct the server so that it reports WaRF's version in serverInfo.

    mcp 2.x takes version= and defaults it to "", which is what clients then
    show. mcp 1.x has no such parameter: there the low-level server carries the
    version and falls back to the SDK's own, which is just as wrong.
    """
    try:
        return cls("warf", instructions=policy_text(), version=__version__)
    except TypeError:
        server = cls("warf", instructions=policy_text())
        low = getattr(server, "_mcp_server", None)
        if low is not None and hasattr(low, "version"):
            low.version = __version__
        return server


def build_server():
    server = _new_server(_fastmcp())

    @server.tool()
    def warf_review(
        path: str,
        domain: str = "AUTO",
        profile: str = "default",
        max_agents: int | None = None,
        debate: bool = False,
        no_early_stop: bool = False,
    ) -> dict:
        """Review one source file with the WaRF panel.

        Returns the session record: decision, confidence, sprt_lambda,
        sprt_fired, per-agent votes (vote, omega, reasoning) and session_id.
        Read `confidence` before acting on `decision`: HIGH REJECT blocks,
        HIGH APPROVE may proceed, MEDIUM goes to a human, LOW is not actionable.
        domain: AUTO | LOGIC | SECURITY | PERFORMANCE. max_agents caps the
        panel (faster, but HIGH APPROVE becomes unreachable below 5).
        """
        file = Path(path)
        if not file.is_file():
            return {"ok": False, "error": "not_found", "path": str(file)}
        code = file.read_text(encoding="utf-8")
        dom = domain.upper()
        if dom == "AUTO":
            dom, _ = detect_domain(file, code)
        pp = profile_path(profile)
        with contextlib.redirect_stdout(sys.stderr):
            result = run_review(
                code, dom, pp,
                verbose=False, debate=debate,
                context=find_context(file.parent),
                max_agents=max_agents, no_early_stop=no_early_stop,
            )
            record = append_session(result, artifact_path=str(file), profile_name=profile)
        return {"ok": True, **record}

    @server.tool()
    def warf_label(
        verdict: str,
        session_id: str | None = None,
        artifact: str | None = None,
        oracle: str = "DEVELOPER",
        profile: str = "default",
        force: bool = False,
    ) -> dict:
        """Attach ground truth to a past review and update the agents' weights.

        Use only when a human has actually decided the outcome; never on a
        guess. Select the session by session_id (a prefix is enough) or by an
        artifact path substring. verdict: APPROVE | REJECT.
        oracle: DEVELOPER | SAST | TEST | COMPILER. Refuses an already-labelled
        session unless force=True, which applies a second weight update.
        """
        try:
            with contextlib.redirect_stdout(sys.stderr):
                out = label_session(
                    verdict, profile_path(profile),
                    session_id=session_id, artifact=artifact,
                    oracle_type=oracle, force=force,
                )
            return {"ok": True, **out}
        except SessionAmbiguous as exc:
            return {
                "ok": False, "error": "ambiguous_selector",
                "candidates": [
                    {"session_id": s["session_id"], "artifact": s["artifact"],
                     "decision": s["decision"], "confidence": s["confidence"],
                     "labelled": "oracle" in s}
                    for _, s in exc.matches
                ],
            }
        except AlreadyLabelled as exc:
            return {
                "ok": False, "error": "already_labelled",
                "session_id": exc.session["session_id"],
                "existing_label": exc.session["oracle"]["x_star_label"],
            }
        except (SessionNotFound, ValueError) as exc:
            return {"ok": False, "error": "not_found", "message": str(exc)}

    @server.tool()
    def warf_weights(profile: str = "default") -> dict:
        """Current learned weight (omega) per agent per domain, with the
        persona version that earned it. A non-empty pending_reconcile means a
        persona's text changed and its weights will be retired on the next
        review."""
        pp = profile_path(profile)
        with contextlib.redirect_stdout(sys.stderr):
            profiles = load_profiles(pp, reconcile=False)
        pending = reconcile_profiles(profiles, apply=False)
        return {
            "profile": profile,
            "path":    str(pp),
            "agents": [
                {
                    "agent":        p.name,
                    "domain":       domain,
                    "alpha":        w.alpha,
                    "beta":         w.beta,
                    "omega":        round(w.omega, 4),
                    "ci_95":        [round(v, 4) for v in omega_ci(w.alpha, w.beta)],
                    "provider":     p.provider,
                    "model":        p.model,
                    "persona_hash": p.persona_hash,
                }
                for p in profiles for domain, w in p.weights.items()
            ],
            "pending_reconcile": [
                {"agent": e.agent, "kind": e.kind,
                 "old_hash": e.old_hash, "new_hash": e.new_hash}
                for e in pending
            ],
        }

    @server.tool()
    def warf_sessions(
        limit: int = 20,
        profile: str | None = None,
        artifact: str | None = None,
        labelled: bool | None = None,
        include_reasoning: bool = False,
    ) -> dict:
        """Most recent review sessions, newest first. Filter by profile name,
        artifact path substring, or labelled state. Per-agent reasoning is
        omitted unless include_reasoning=True (it is long)."""
        out: list[dict] = []
        for line in reversed(load_lines()):
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            if profile is not None and s.get("profile") != profile:
                continue
            if artifact and artifact.lower() not in s.get("artifact", "").lower():
                continue
            if labelled is not None and bool(s.get("oracle")) != labelled:
                continue
            out.append(s if include_reasoning else _strip_reasoning(s))
            if len(out) >= limit:
                break
        return {"count": len(out), "sessions": out}

    @server.tool()
    def warf_paths() -> dict:
        """Where this server reads and writes state — data directory, profiles,
        session log — and how that was resolved: WARF_HOME, a project .warf/,
        or ~/.warf."""
        return describe_paths()

    @server.prompt()
    def warf_policy() -> str:
        """WaRF's output interpretation policy: the routing table, what each
        confidence level means mechanically, and what never to do with a verdict."""
        return policy_text()

    @server.resource("warf://policy")
    def policy_resource() -> str:
        """The interpretation policy (policy.md), verbatim."""
        return policy_text()

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
