"""
Decision-provider test — the `jev` and `laya` providers against a fake
/v1/systemone server. No credentials, no model, no network.

Starts a local HTTP server that speaks TypeSafe's System One wire protocol with
canned answers, points both providers at it, and checks the request WaRF sends,
the vote it parses and the error paths. Then runs a whole review through
run_review with a throwaway panel on the fake endpoint, so the orchestrator's
handling of a decision backend is covered too.

Usage:  python tools/test_systemone.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Greek letters in the report must survive a cp1252 console.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# A dev tool, not part of the package: make the checkout importable, and keep
# the throwaway panel out of any real data directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_HOME = tempfile.mkdtemp(prefix="warf-systemone-")
os.environ["WARF_HOME"] = _HOME
os.environ["WARF_NO_BROWSER"] = "1"
for _var in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "LAYA_API_KEY", "LAYA_BASE_URL",
             "WARF_PROVIDER", "WARF_MODEL"):
    os.environ.pop(_var, None)

from warf.providers import (  # noqa: E402
    SystemOneProvider, ProviderError, get_provider, resolve_model, describe, PROVIDER_NAMES,
)
from warf.orchestrator import _parse_vote, run_review, REPLY_FORMAT  # noqa: E402
from warf.state import AgentProfile, persona_hash, save_profiles  # noqa: E402
from warf.engine import Decision, Confidence  # noqa: E402

REJECT_ANSWER  = {"choice": "REJECT",  "probabilities": {"APPROVE": 0.12, "REJECT": 0.88}, "confidence": 0.76}
APPROVE_ANSWER = {"choice": "APPROVE", "probabilities": {"APPROVE": 0.70, "REJECT": 0.30}, "confidence": 0.40}


class FakeSystemOne(BaseHTTPRequestHandler):
    """A canned Jev. The class attributes are the script's knobs; `seen` collects requests."""
    seen: list = []
    answer: dict = REJECT_ANSWER
    fail_once = None      # HTTP status to return on the next request only
    fail_always = None    # (status, message) to return on every request

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        cls = type(self)
        cls.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if cls.fail_once is not None:
            code, cls.fail_once = cls.fail_once, None
            return self._send(code, {"error": "try again"})
        if cls.fail_always is not None:
            code, msg = cls.fail_always
            return self._send(code, {"error": msg})
        qid = next(iter(body["questions"]))
        self._send(200, {
            "model":   "jev-1.13.0",
            "answers": {qid: {"type": "choice", **cls.answer}},
            "usage":   {"input_tokens": 282, "output_tokens": 0},
        })

    def _send(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):   # keep the test output clean
        pass


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def question(req):
    return next(iter(req["body"]["questions"].values()))


server = HTTPServer(("127.0.0.1", 0), FakeSystemOne)
base = f"http://127.0.0.1:{server.server_port}"
threading.Thread(target=server.serve_forever, daemon=True).start()

print("\n=== provider: jev ===")
try:
    SystemOneProvider()
    check(False, "jev without TYPESAFE_API_KEY is refused")
except ProviderError as exc:
    check("TYPESAFE_API_KEY" in str(exc), "jev without TYPESAFE_API_KEY is refused")

jev = SystemOneProvider(base_url=base, api_key="test-key")
c = jev.complete(system="Should this be merged?", user="Domain: LOGIC\n\ncode", model="jev-latest")
req = FakeSystemOne.seen[-1]
check(req["path"] == "/v1/systemone", "POST /v1/systemone")
check(req["auth"] == "Bearer test-key", "Authorization: Bearer <key>")
check(req["body"]["model"] == "jev-latest" and req["body"]["state"] == "Domain: LOGIC\n\ncode",
      "model and state sent as given")
check(len(req["body"]["questions"]) == 1 and question(req)["type"] == "choice", "one choice question")
check(question(req)["instructions"] == "Should this be merged?", "the persona is the instructions")
check(set(question(req)["criteria"]) == {"APPROVE", "REJECT"}, "the criteria are APPROVE / REJECT")
vote, reasoning = _parse_vote(c.text)
check(vote == -1, f"vote parses as REJECT: {c.text.splitlines()[0]!r}")
check("p(APPROVE)=0.12" in reasoning and "p(REJECT)=0.88" in reasoning and "confidence=0.76" in reasoning,
      f"readout as reasoning: {reasoning}")
check(c.tokens_in == 282 and c.tokens_out == 0, "usage recorded")

FakeSystemOne.answer = APPROVE_ANSWER
vote, _ = _parse_vote(jev.complete("q", "s", "jev-latest").text)
check(vote == 1, "APPROVE parses as +1")
FakeSystemOne.answer = REJECT_ANSWER

FakeSystemOne.fail_once = 429
before = len(FakeSystemOne.seen)
jev.complete("q", "s", "jev-latest")
check(len(FakeSystemOne.seen) == before + 2, "HTTP 429 is retried after a back-off")

for code, msg, needle in ((401, "invalid key", "TYPESAFE_API_KEY"),
                          (400, "max_tokens_exceeded", "context"),
                          (422, "bad question", "malformed")):
    FakeSystemOne.fail_always = (code, msg)
    try:
        jev.complete("q", "s", "jev-latest")
        check(False, f"HTTP {code} raises ProviderError")
    except ProviderError as exc:
        check(needle in str(exc), f"HTTP {code} -> {str(exc)[:72]}")
FakeSystemOne.fail_always = None

FakeSystemOne.answer = {"choice": "MAYBE", "probabilities": {}}
try:
    jev.complete("q", "s", "jev-latest")
    check(False, "an answer outside APPROVE/REJECT is refused")
except ProviderError as exc:
    check("APPROVE/REJECT" in str(exc), "an answer outside APPROVE/REJECT is refused")
FakeSystemOne.answer = REJECT_ANSWER

print("\n=== registry: jev / laya ===")
check("jev" in PROVIDER_NAMES and "laya" in PROVIDER_NAMES, f"both registered: {PROVIDER_NAMES}")
check(resolve_model("jev") == "jev-latest" and resolve_model("laya") == "multilingual",
      "default models: jev-latest, multilingual")
os.environ["LAYA_BASE_URL"] = base
laya = get_provider("laya")
check(laya.name == "laya" and laya.kind == "decision", "the laya alias builds a decision provider")
laya.complete("q", "s", resolve_model("laya"))
req = FakeSystemOne.seen[-1]
check(req["auth"] is None and req["body"]["model"] == "multilingual",
      "laya: no Authorization header without a key, multilingual checkpoint")
info = describe()
check(info["available"]["jev"] is False and info["available"]["laya"] is True
      and "TYPESAFE_API_KEY" in info["env"], "warf providers lists both backends")

print("\n=== run_review on a five-agent jev panel ===")
os.environ["TYPESAFE_BASE_URL"] = base
os.environ["TYPESAFE_API_KEY"] = "test-key"
panel = []
for i in range(1, 6):
    text = f"Question {i}: should this change be merged as it is?"
    panel.append(AgentProfile(name=f"JEV-{i}", persona=text, provider="jev",
                              persona_hash=persona_hash(text)))
profiles_path = Path(_HOME) / "profiles" / "systemone_test.json"
profiles_path.parent.mkdir(parents=True, exist_ok=True)
save_profiles(profiles_path, panel)

FakeSystemOne.seen.clear()
result = run_review("def f(a, b):\n    return a / b\n", "LOGIC", profiles_path, verbose=False)
check(result.decision is Decision.REJECT and result.confidence is Confidence.HIGH,
      f"{result.decision.value} [{result.confidence.value}]  L={result.sprt_lambda:+.3f}")
check(len(result.votes) == 4, f"SPRT fired after {len(result.votes)} of 5 votes (uniform ω=0.5)")
states = [r["body"]["state"] for r in FakeSystemOne.seen]
check(all(REPLY_FORMAT not in s for s in states), "no reply-format instruction in a decision model's state")
check(all(s.startswith("Domain: LOGIC") and "return a / b" in s for s in states),
      "the state carries the domain and the code")
check(all(v.provider == "jev" and v.model == "jev-latest" for v in result.votes),
      "votes attributed to jev / jev-latest")
check(all("decision model, no reasoning" in v.reasoning for v in result.votes),
      "votes carry the readout as their reasoning")

server.shutdown()
print("\nall checks passed")
