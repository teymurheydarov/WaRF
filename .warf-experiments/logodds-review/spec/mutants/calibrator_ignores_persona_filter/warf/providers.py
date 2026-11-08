"""
Model providers — the single seam between WaRF and whatever runs the agents.

WaRF's contribution is weighting, sequential testing and calibration; none of it
depends on who answers the prompt. Everything below exists so an agent panel can
be Claude, a hosted OpenAI-compatible endpoint, or five local models on Ollama,
without the orchestrator knowing the difference.

A provider does one thing:

    complete(system, user, model, timeout) -> Completion(text, tokens_in, tokens_out)

Vote parsing stays in the orchestrator and is deliberately text-based ("first word
is APPROVE or REJECT"), not JSON or tool-calls — small local models are unreliable
at structured output and fine at this. A decision model (kind "decision") produces
no prose at all: its provider asks one APPROVE/REJECT question and renders the
answer in that same first-word shape, so the orchestrator still tells no difference.

Built-in providers
------------------
claude_cli      Claude Desktop / Claude Code binary. Subscription quota, no API key.
anthropic       Anthropic Python SDK. Requires ANTHROPIC_API_KEY.
openai_compat   Any /v1/chat/completions endpoint — OpenAI, Groq, DeepSeek, Together,
                Mistral, Fireworks, vLLM, LM Studio, Ollama (http://localhost:11434/v1).
jev             TypeSafe's Jev, a decision model, over /v1/systemone. Requires
                TYPESAFE_API_KEY. Alias `laya`: ConvAI's open Laya checkpoints behind
                a local laya-serve (http://127.0.0.1:8000), the same wire protocol.

Selection order (first match wins)
----------------------------------
1. provider/model on the agent's profile entry
2. WARF_PROVIDER / WARF_MODEL environment variables
3. ANTHROPIC_API_KEY present            -> anthropic
4. a claude binary is discoverable      -> claude_cli

No third-party imports: openai_compat speaks HTTP over urllib so that installing
WaRF into a CI image pulls in nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Per-agent wall-clock limit. This is a safety net against a hung backend, not a
# performance target: setting it too tight silently drops the slowest agents from
# the panel, which biases any per-agent measurement toward the cases they finished.
DEFAULT_TIMEOUT = float(os.environ.get("WARF_TIMEOUT", "120"))
DEFAULT_MAX_TOKENS = 1024

# Model used when neither the profile nor the environment names one.
DEFAULT_MODELS = {
    "claude_cli":    "claude-haiku-4-5-20251001",
    "anthropic":     "claude-haiku-4-5-20251001",
    "openai_compat": "gpt-4o-mini",
    "jev":           "jev-latest",
}

# Neutral working directory — stops the reviewed project's CLAUDE.md from being
# picked up by the Claude CLI and silently entering the agent's context.
_NEUTRAL_CWD = str(Path.home())


class ProviderError(RuntimeError):
    """A provider could not produce a completion."""


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class Provider(Protocol):
    name: str
    # kind: "text" (the default when the attribute is absent) answers in prose and
    # is told the reply format; "decision" answers a typed question and is not.

    def complete(self, system: str, user: str, model: str,
                 timeout: float = DEFAULT_TIMEOUT) -> Completion: ...


# ── claude CLI ───────────────────────────────────────────────────────────────

def find_claude_exe() -> Path | None:
    """Locate a claude binary, or None. Never raises — callers decide if it matters."""
    found = shutil.which("claude")
    if found:
        return Path(found)
    # Claude Desktop on Windows: LOCALAPPDATA\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    pkgs = local / "Packages"
    if pkgs.exists():
        for pkg in pkgs.iterdir():
            if not pkg.name.startswith("Claude_"):
                continue
            cc_dir = pkg / "LocalCache" / "Roaming" / "Claude" / "claude-code"
            if cc_dir.exists():
                for v in sorted(cc_dir.iterdir(), reverse=True):
                    exe = v / "claude.exe"
                    if exe.exists():
                        return exe
    return None


class ClaudeCLIProvider:
    """Shells out to the Claude binary. Uses OAuth subscription quota, not an API key."""

    name = "claude_cli"

    def __init__(self, exe: Path | None = None):
        self._exe = exe or find_claude_exe()
        if self._exe is None:
            raise ProviderError(
                "No claude binary found. Install Claude Desktop, or run "
                "`npm install -g @anthropic-ai/claude-code`, or choose another "
                "provider with WARF_PROVIDER=openai_compat."
            )

    def complete(self, system: str, user: str, model: str,
                 timeout: float = DEFAULT_TIMEOUT) -> Completion:
        # Strip the API key so the CLI cannot silently switch to billed API mode.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        result = subprocess.run(
            [str(self._exe), "-p", "--system-prompt", system, "--model", model],
            input=user,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=_NEUTRAL_CWD,
            env=env,
        )
        if result.returncode != 0:
            raise ProviderError(
                f"claude CLI error (rc={result.returncode}): {result.stderr[:400]}"
            )
        text = (result.stdout or "").strip()
        if not text:
            raise ProviderError("claude CLI returned an empty response")
        # The CLI does not report usage; token counts stay zero.
        return Completion(text=text)


# ── Anthropic SDK ────────────────────────────────────────────────────────────

class AnthropicProvider:
    """Anthropic Python SDK. Faster than the CLI and reports real token usage."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set.")

    def complete(self, system: str, user: str, model: str,
                 timeout: float = DEFAULT_TIMEOUT) -> Completion:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "The anthropic package is not installed: pip install anthropic"
            ) from exc
        client = anthropic.Anthropic(api_key=self._api_key, timeout=timeout)
        response = client.messages.create(
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text.strip() if response.content else ""
        if not text:
            raise ProviderError("Anthropic SDK returned an empty response")
        return Completion(
            text=text,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )


# ── OpenAI-compatible HTTP ───────────────────────────────────────────────────

class OpenAICompatProvider:
    """Any /v1/chat/completions endpoint.

    Covers OpenAI, Groq, DeepSeek, Together, Mistral, Fireworks, vLLM, LM Studio
    and Ollama. The API key is optional: local servers generally accept requests
    without an Authorization header, so none is sent when no key is configured.
    """

    name = "openai_compat"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        base = (
            base_url
            or os.environ.get("WARF_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self._base_url = base.rstrip("/")
        self._api_key = (
            api_key
            or os.environ.get("WARF_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    def complete(self, system: str, user: str, model: str,
                 timeout: float = DEFAULT_TIMEOUT) -> Completion:
        payload = json.dumps({
            "model": model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise ProviderError(
                f"{self._base_url} returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Cannot reach {self._base_url}: {exc.reason}. "
                "Is the server running?"
            ) from exc

        choices = body.get("choices") or []
        if not choices:
            raise ProviderError(f"{self._base_url} returned no choices: {str(body)[:300]}")
        text = (choices[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise ProviderError(f"{self._base_url} returned an empty message")

        usage = body.get("usage") or {}
        return Completion(
            text=text,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )

# ── System One decision endpoint (Jev, Laya) ─────────────────────────────────

# The two options a decision agent chooses between. They say what a vote means
# and are the same for every decision agent; the persona text is the question
# asked alongside them. Like the reply-format instruction the orchestrator adds
# for text agents, they belong to the protocol, not to the persona fingerprint.
DECISION_CRITERIA = {
    "APPROVE": "The code is correct and safe to merge as it is.",
    "REJECT":  "The code has a defect, vulnerability or regression that must be "
               "fixed before it is merged.",
}
_DECISION_QUESTION = "verdict"
_RETRY_STATUSES = {429, 503, 529}   # rate limited, busy, overloaded: back off, retry
_RETRY_ATTEMPTS = 3


class SystemOneProvider:
    """A System One decision endpoint: POST {base_url}/v1/systemone.

    TypeSafe's hosted Jev defines the protocol; ConvAI's open Laya checkpoints
    speak the same one locally through `laya-serve`. These models write no text.
    They take a state and typed questions and return, per question, the chosen
    option and a probability for every option. WaRF asks one Choice question —
    APPROVE or REJECT, with the agent's persona as the instructions and the
    orchestrator's message (domain, context, code) as the state — and renders
    the answer in the shape _parse_vote expects: the label on the first line,
    the probability readout on the second. The readout is all the "reasoning"
    such an agent can give.

    A decision agent's weight is learned like any other: it is a persona (here,
    a question) on a model, and `warf label` scores its votes.
    """

    name = "jev"
    kind = "decision"   # the orchestrator sends these no reply-format instruction

    def __init__(self, base_url: str | None = None, api_key: str | None = None, *,
                 name: str = "jev", env_prefix: str = "TYPESAFE",
                 default_base: str = "https://api.typesafe.ai",
                 key_required: bool = True):
        self.name = name
        self._env_prefix = env_prefix
        base = base_url or os.environ.get(f"{env_prefix}_BASE_URL") or default_base
        self._base_url = base.rstrip("/")
        self._api_key = api_key or os.environ.get(f"{env_prefix}_API_KEY")
        if key_required and not self._api_key:
            raise ProviderError(
                f"{env_prefix}_API_KEY is not set. Create a key at console.typesafe.ai/keys, "
                "or run the open model locally (pip install \"laya[serve]\", then laya-serve) "
                "and choose provider `laya`."
            )

    def complete(self, system: str, user: str, model: str,
                 timeout: float = DEFAULT_TIMEOUT) -> Completion:
        payload = json.dumps({
            "model": model,
            "state": user,
            "questions": {
                _DECISION_QUESTION: {
                    "type":         "choice",
                    "instructions": system,
                    "criteria":     DECISION_CRITERIA,
                },
            },
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/v1/systemone", data=payload, headers=headers, method="POST",
        )
        body = self._post(request, timeout)

        answer = (body.get("answers") or {}).get(_DECISION_QUESTION) or {}
        choice = str(answer.get("choice") or "").upper()
        if choice not in DECISION_CRITERIA:
            raise ProviderError(
                f"{self._base_url} returned no APPROVE/REJECT choice: {str(body)[:300]}"
            )
        probs = answer.get("probabilities") or {}
        readout = "  ".join(
            f"p({label})={float(probs.get(label) or 0.0):.2f}" for label in DECISION_CRITERIA
        )
        confidence = answer.get("confidence")
        if isinstance(confidence, (int, float)):
            readout += f"  confidence={float(confidence):.2f}"
        reported = body.get("model") or model
        text = f"{choice}\n{readout}  [{reported}: decision model, no reasoning]"

        usage = body.get("usage") or {}
        return Completion(
            text=text,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
        )

    def _post(self, request: urllib.request.Request, timeout: float) -> dict:
        """Send once; on 429/503/529 back off and retry, as the API asks clients to."""
        delay = 1.0
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                if exc.code in _RETRY_STATUSES and attempt < _RETRY_ATTEMPTS:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise ProviderError(self._explain(exc.code, detail)) from exc
            except urllib.error.URLError as exc:
                hint = ("Is laya-serve running?" if self._env_prefix == "LAYA"
                        else f"Check {self._env_prefix}_BASE_URL.")
                raise ProviderError(f"Cannot reach {self._base_url}: {exc.reason}. {hint}") from exc
            except OSError as exc:   # a read timeout surfaces as socket.timeout
                raise ProviderError(f"{self._base_url} timed out after {timeout:.0f}s") from exc
            try:
                return json.loads(raw)
            except ValueError as exc:
                raise ProviderError(f"{self._base_url} returned no JSON: {raw[:200]}") from exc
        raise AssertionError("unreachable")

    def _explain(self, code: int, detail: str) -> str:
        where = self._base_url
        if code == 401:
            return (f"{where} rejected the API key (HTTP 401): {detail} — "
                    f"check {self._env_prefix}_API_KEY.")
        if code == 400 and "max_tokens_exceeded" in detail:
            return (f"{where}: the input exceeds the model's context (HTTP 400: {detail}). "
                    "Review a diff or a smaller file.")
        if code == 413:
            return f"{where}: the request is too large (HTTP 413: {detail})."
        if code == 422:
            return f"{where} rejected the request as malformed (HTTP 422): {detail}"
        if code in _RETRY_STATUSES:
            return (f"{where} is rate limited or overloaded (HTTP {code}) after "
                    f"{_RETRY_ATTEMPTS} attempts: {detail}")
        return f"{where} returned HTTP {code}: {detail}"


# ── resolution ───────────────────────────────────────────────────────────────

_BUILDERS = {
    "claude_cli":    ClaudeCLIProvider,
    "anthropic":     AnthropicProvider,
    "openai_compat": OpenAICompatProvider,
    "jev":           SystemOneProvider,
}

# Convenience names: a builder plus preset configuration and a default model.
# `ollama` is what people type; what it is, is an OpenAI-compatible endpoint on
# localhost.
_ALIASES: dict[str, tuple[str, dict, str]] = {
    "ollama": ("openai_compat", {"base_url": "http://localhost:11434/v1"}, "qwen2.5-coder:7b"),
    # Likewise `laya`: ConvAI's open decision model, served by `laya-serve` on
    # localhost with Jev's wire protocol. No key unless the server demands one.
    # 127.0.0.1 rather than the name: laya-serve binds IPv4, and on Windows
    # `localhost` resolves to ::1 first, which cost 2.6 s per vote against 0.6 s
    # for the same request. LAYA_BASE_URL still overrides.
    "laya": ("jev", {"name": "laya", "env_prefix": "LAYA",
                     "default_base": "http://127.0.0.1:8000", "key_required": False},
             "multilingual"),
}

PROVIDER_NAMES = tuple(_BUILDERS) + tuple(_ALIASES)

_cache: dict[str, Provider] = {}


def detect_default_provider() -> str:
    """Pick a provider when nothing is configured.

    Preserves the historical behaviour: prefer the SDK when an API key is present,
    otherwise fall back to the Claude binary.
    """
    env = os.environ.get("WARF_PROVIDER")
    if env:
        return env.strip().lower()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if find_claude_exe() is not None:
        return "claude_cli"
    # Nothing detected. Return the Anthropic path so the resulting error names the
    # missing credential rather than a missing binary.
    return "anthropic"


def get_provider(name: str | None = None, **config) -> Provider:
    """Return a provider instance, cached per (name, config).

    Resolution is lazy and happens on first use, not at import, so importing WaRF
    on a machine with neither a Claude binary nor an API key does not fail — only
    actually running a review does.
    """
    resolved = (name or detect_default_provider()).strip().lower()
    builder_name, preset = resolved, {}
    if resolved in _ALIASES:
        builder_name, preset, _ = _ALIASES[resolved]
    if builder_name not in _BUILDERS:
        raise ProviderError(
            f"Unknown provider '{resolved}'. Available: {', '.join(PROVIDER_NAMES)}"
        )
    # The alias preset beats the process-wide environment (WARF_BASE_URL may point a
    # mixed panel's other agents somewhere else entirely); explicit config beats both.
    config = {**preset, **config}
    key = resolved + "|" + json.dumps(config, sort_keys=True, default=str)
    if key not in _cache:
        _cache[key] = _BUILDERS[builder_name](**config)
    return _cache[key]


def resolve_model(provider_name: str, model: str | None = None) -> str:
    """Model for this provider: explicit, else WARF_MODEL, else the provider default."""
    name = (provider_name or "").strip().lower()
    alias_default = _ALIASES[name][2] if name in _ALIASES else None
    return (
        model
        or os.environ.get("WARF_MODEL")
        or alias_default
        or DEFAULT_MODELS.get(name, DEFAULT_MODELS["anthropic"])
    )


def describe() -> dict:
    """What the current environment would select. Used by `warf providers`."""
    default = detect_default_provider()
    claude = find_claude_exe()
    return {
        "default_provider": default,
        "default_model":    resolve_model(default),
        "available": {
            "claude_cli":    claude is not None,
            "anthropic":     bool(os.environ.get("ANTHROPIC_API_KEY")),
            "openai_compat": True,  # always constructible; reachability unknown until used
            "jev":           bool(os.environ.get("TYPESAFE_API_KEY")),
            "laya":          True,  # a local laya-serve; reachability unknown until used
        },
        "claude_exe": str(claude) if claude else None,
        "base_url": (
            os.environ.get("WARF_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ),
        "env": {
            "WARF_PROVIDER":     os.environ.get("WARF_PROVIDER"),
            "WARF_MODEL":        os.environ.get("WARF_MODEL"),
            "WARF_BASE_URL":     os.environ.get("WARF_BASE_URL"),
            "WARF_API_KEY":      "set" if os.environ.get("WARF_API_KEY") else None,
            "ANTHROPIC_API_KEY": "set" if os.environ.get("ANTHROPIC_API_KEY") else None,
            "OPENAI_API_KEY":    "set" if os.environ.get("OPENAI_API_KEY") else None,
            "TYPESAFE_API_KEY":  "set" if os.environ.get("TYPESAFE_API_KEY") else None,
            "LAYA_BASE_URL":     os.environ.get("LAYA_BASE_URL"),
        },
    }
