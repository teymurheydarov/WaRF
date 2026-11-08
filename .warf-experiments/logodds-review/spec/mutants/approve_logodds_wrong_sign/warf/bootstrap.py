"""
First-run commands: `warf init` and `warf install-skill`.

Kept out of cli.py so that file only grows its argument parser, and so the
skill text can be rendered from anywhere — the MCP server serves the same
policy text as its instructions.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .paths import DIR_NAME, ENV_VAR, project_root, resolution
from .providers import resolve_model
from .state import default_profiles, save_profiles

POLICY_FILE = Path(__file__).parent / "policy.md"   # ships as package data
SKILL_NAME  = "warf"

# Tail of the line in the rendered skill that carries the invocation. Used to
# read the invocation back out of an existing copy; keep in step with render_skill.
_INVOCATION_MARKER = " review <path> --json --fail-on HIGH"


def policy_text() -> str:
    return POLICY_FILE.read_text(encoding="utf-8")


# ── warf init ────────────────────────────────────────────────────────────────

def cmd_init(args) -> None:
    """Create the data directory and a first profile.

    Default target is whatever `warf paths` resolves to. --local creates a
    project .warf/ in the repo root (the git-config style override); --global
    forces ~/.warf. The resolver caches per process, so the target is computed
    explicitly here rather than read back through data_dir() after a mkdir.
    """
    if getattr(args, "local", False):
        target, how = project_root() / DIR_NAME, "project-local"
    elif getattr(args, "global_", False):
        target, how = Path.home() / DIR_NAME, "global"
    else:
        target, tier = resolution()
        how = {"env": f"from {ENV_VAR}", "project": "project-local", "global": "global"}[tier]

    target.mkdir(parents=True, exist_ok=True)
    (target / "profiles").mkdir(exist_ok=True)

    profiles = default_profiles()
    if args.provider or args.model:
        for p in profiles:
            p.provider = args.provider or p.provider
            p.model    = args.model    or p.model

    prof_file = target / "profiles" / f"{args.profile}.json"
    existed = prof_file.exists()
    if existed and not args.force:
        status = "kept: already exists (use --force to overwrite)"
    else:
        save_profiles(prof_file, profiles)
        status = "overwritten" if existed else "created (uniform priors, current personas)"

    sample = profiles[0]
    if sample.provider:
        prov, model = sample.provider, (sample.model or resolve_model(sample.provider))
    else:
        prov = model = "environment default (see: warf providers)"

    print(f"\n  Data directory : {target}   [{how}]")
    print(f"  Profile        : {prof_file.name}   {status}")
    print(f"  Panel          : {len(profiles)} agents   provider={prov}   model={model}")
    print()
    print("  Next:   warf review <file> --json       run a review")
    print("          warf install-skill              add /warf to Claude Code")
    print("          warf providers                  check which backend will answer")
    if getattr(args, "local", False):
        print(f"\n  Commit {DIR_NAME}/ to share this project's calibration with the team.")
    print()


# ── warf install-skill ───────────────────────────────────────────────────────

def detect_invocation() -> str:
    """The shortest command that runs WaRF on this machine.

    `warf` only if pip's Scripts directory is on PATH. Otherwise the module form,
    which works wherever the package is importable; on Windows the `py` launcher
    is the reliable interpreter name.
    """
    if shutil.which("warf"):
        return "warf"
    if os.name == "nt" and shutil.which("py"):
        return "py -m warf"
    return "python -m warf"


def _baked_command(skill_text: str) -> str | None:
    """The invocation an existing SKILL.md was rendered with, or None if it cannot be told."""
    for line in skill_text.splitlines():
        line = line.rstrip()
        if line.endswith(_INVOCATION_MARKER):
            return line[: -len(_INVOCATION_MARKER)].strip() or None
    return None


def render_skill(cmd: str) -> str:
    """The Claude Code skill: a short invocation guide, then policy.md verbatim.

    policy.md is the single source of truth for how to read WaRF's output; the
    skill embeds it rather than pointing at it so the skill is self-contained
    and identical to what the MCP server tells its clients. The text is a pure
    function of (cmd, package version, policy.md), which is what lets
    cmd_install_skill tell whether an installed copy is still current.
    """
    front = """---
name: warf
description: Review a file, diff, or commit with WaRF, a weighted multi-agent panel with SPRT early stopping and a calibrated confidence level. Use when the user asks for a WaRF review, invokes /warf, or wants a verdict with confidence before merging.
---
"""
    body = f"""# WaRF review

WaRF runs a panel of reviewer personas, weights each vote by that agent's
learned reliability in the domain, and stops as soon as the accumulated
evidence crosses a statistical boundary. The result is a verdict **and a
confidence level** — and the confidence level is what decides the action.

## Invoke

Run from the project root, so the project's own `.warf/` calibration is used:

```
{cmd} review <path> --json --fail-on HIGH
{cmd} review-commit <sha> --json --fail-on HIGH
{cmd} review <path> --domain SECURITY --json     # override the domain
```

Read the JSON from stdout; everything else goes to stderr. If `{cmd}` is not
found, try `python -m warf` or, on Windows, `py -m warf`.

Exit codes: 0 = nothing met the `--fail-on` threshold; 1 = a REJECT did;
2 = WaRF could not run (bad path, no credentials, quota). 2 is never a verdict.

## Report

Lead with decision + confidence + how many agents it took, then the
highest-weighted agent that dissented, if any, with its ω in that domain. Never
report `decision` without `confidence`. For example:

> REJECT, HIGH confidence (λ = −2.33, stopped after 3 of 5 agents).
> BOUNDARY (ω = 0.70), SKEPTIC (ω = 0.62) and TEST-FOCUSED (ω = 0.54) all flagged
> the auth header handling. The other two agents were not asked.

> REJECT, MEDIUM confidence — all 5 agents voted, no boundary crossed (λ = −1.06).
> AUDITOR, the highest-weighted dissenter (ω = 0.66 in SECURITY), approved.
> MEDIUM goes to a human; this is not a block.

If the JSON has a `debate` block, the λ behind the verdict is `debate.sprt_lambda`,
not the top-level one.

## Close the loop

Only when a human has actually decided the review's outcome:

```
{cmd} label <session_id> --verdict APPROVE|REJECT
```

Never label on a guess. `session_id` is in the review JSON.

## Diagnostics

`{cmd} paths` — where state lives · `{cmd} providers` — which model answers ·
`{cmd} weights` — current ω per agent per domain.

This skill was generated by warf {__version__}. `{cmd} install-skill` reports
whether this copy is still current; after upgrading WaRF, regenerate it with
`{cmd} install-skill --force`. Do not edit it by hand.

---

Everything below is WaRF's interpretation policy. Follow it literally.

"""
    return front + body + policy_text()


def cmd_install_skill(args) -> None:
    """Write the skill, or — if a copy exists and --force was not given — check it.

    Exit 0 when written or up to date, 1 when an existing copy is out of date,
    so a team that commits the skill can verify it in CI.
    """
    explicit = getattr(args, "command_name", None)

    if getattr(args, "print_only", False):
        sys.stdout.write(render_skill(explicit or detect_invocation()))
        return

    if getattr(args, "global_", False):
        base, scope = Path.home() / ".claude" / "skills", "user (every project)"
    else:
        base, scope = project_root() / ".claude" / "skills", "this project"
    target = base / SKILL_NAME / "SKILL.md"

    existing = target.read_text(encoding="utf-8") if target.exists() else None
    # An existing copy keeps the invocation it was installed with unless --command
    # says otherwise. A team that committed a portable invocation must not have it
    # rewritten to whatever happens to be detected on one developer's machine —
    # and the currency check below has to compare like with like.
    cmd  = explicit or (_baked_command(existing) if existing else None) or detect_invocation()
    text = render_skill(cmd)

    if existing is not None and not getattr(args, "force", False):
        if existing == text:
            print(f"Up to date: {target}", file=sys.stderr)
            print(f"  generated by warf {__version__}, invocation: {cmd}", file=sys.stderr)
            sys.exit(0)
        print(f"Out of date: {target}", file=sys.stderr)
        print(f"  It differs from what warf {__version__} writes: the policy changed, WaRF was",
              file=sys.stderr)
        print("  upgraded, or the file was edited. Regenerate with --force (hand edits are lost),",
              file=sys.stderr)
        print("  or use --print to see the new text.", file=sys.stderr)
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")

    print(f"{'Regenerated' if existing is not None else 'Installed'} skill -> {target}")
    print(f"  scope      : {scope}")
    print(f"  invocation : {cmd}" + ("   (kept from the existing copy)" if existing and not explicit else ""))
    print(f"  version    : warf {__version__}")
    print("  Start a new Claude Code session for /warf to appear.")

    if not getattr(args, "global_", False):
        gi = project_root() / ".gitignore"
        if gi.exists():
            rules = {line.strip().rstrip("/") for line in gi.read_text(encoding="utf-8").splitlines()}
            if ".claude" in rules:
                print("  Note: .claude/ is gitignored here, so this copy stays on this machine. That is")
                print("        fine: each developer runs `warf install-skill`. To commit the skill for a")
                print("        team instead, see \"Using WaRF from an agent\" in the README.")
