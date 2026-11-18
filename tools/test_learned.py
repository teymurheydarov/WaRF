"""
Question seats and learned aggregation test (docs/spec/learned-aggregation.md, section 8).

A fake /v1/systemone server checks what the `check` and `locate` questions send and how their answers
are read; run_review is then driven with the agent call stubbed out. No model, no network, no
credentials; the profiles and session logs live in a temporary directory.

Usage:  python tools/test_learned.py
"""
import contextlib
import io
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_HOME = tempfile.mkdtemp(prefix="warf-learned-")
os.environ["WARF_HOME"] = _HOME
os.environ["WARF_NO_BROWSER"] = "1"
for _var in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "WARF_PROVIDER", "WARF_MODEL"):
    os.environ.pop(_var, None)

from warf import calibration, orchestrator  # noqa: E402
from warf.calibration import Calibrator, fit_logistic, p_reject_from_text, seat_logodds  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402
from warf.engine import A, B, LLR_REJECT, Confidence, Decision, learned_decision, logodds_tau  # noqa: E402
from warf.logger import session_dict  # noqa: E402
from warf.orchestrator import _evidence_group, _parse_vote  # noqa: E402
from warf.providers import ProviderError, SystemOneProvider  # noqa: E402
from warf.questions import LOCATE_WINDOW, mark_added_lines, persona_questions  # noqa: E402
from warf.sast import SAST_AGENT_NAME, SAST_OMEGA  # noqa: E402
from warf.state import AgentProfile, load_profiles, persona_hash, save_profiles  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def close(x, y, tol=1e-9):
    return abs(x - y) <= tol


class FakeSystemOne(BaseHTTPRequestHandler):
    """Answers every question of a request: verdict, YES/NO check or line choice. `seen` collects requests."""
    seen: list = []
    verdict = {"choice": "REJECT", "probabilities": {"APPROVE": 0.2, "REJECT": 0.8}}
    check_answer = {"choice": "YES", "probabilities": {"YES": 0.8, "NO": 0.2}}
    locate_p = None        # function(option keys) -> probabilities, or None for "NONE 0.8, the rest shared"
    by_text = {}           # instructions -> function(option keys) -> probabilities, before the rules above

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        cls = type(self)
        cls.seen.append(body)
        answers = {}
        for qid, q in body["questions"].items():
            keys = list(q["criteria"])
            if q["instructions"] in cls.by_text:
                p = cls.by_text[q["instructions"]](keys)
                answers[qid] = {"choice": max(p, key=p.get), "probabilities": p}
            elif "NONE" in keys:
                p = cls.locate_p(keys) if cls.locate_p else {k: (0.8 if k == "NONE" else 0.2 / (len(keys) - 1))
                                                             for k in keys}
                answers[qid] = {"choice": max(p, key=p.get), "probabilities": p}
            elif set(keys) == {"YES", "NO"}:
                answers[qid] = dict(cls.check_answer)
            else:
                answers[qid] = dict(cls.verdict)
        data = json.dumps({"model": "jev-test", "answers": answers,
                           "usage": {"input_tokens": 100, "output_tokens": 1}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), FakeSystemOne)
base = f"http://127.0.0.1:{server.server_port}"
threading.Thread(target=server.serve_forever, daemon=True).start()

DIFF = ("diff --git a/f.cc b/f.cc\n--- a/f.cc\n+++ b/f.cc\n@@ -1,3 +1,3 @@\n int a;\n+int b = 1;\n-int c;\n"
        "+int d;\n")
CODE = DIFF + _SEPARATOR + "+context, not a diff line\n"

print("\n=== marking the added lines ===")
marked, lines = mark_added_lines(CODE)
check(lines == ["int b = 1;", "int d;"], f"the added lines of the diff, in order: {lines}")
check("+[L1] int b = 1;" in marked and "+[L2] int d;" in marked, "each added line is tagged [Lk]")
check("+++ b/f.cc" in marked and "-int c;" in marked and " int a;" in marked, "headers, removed and context lines unchanged")
check(marked.endswith(_SEPARATOR + "+context, not a diff line\n"), "the function context after the separator is not marked")
trimmed = "@@ -1,9 +1,9 @@\n a;\n+b;\n" + _SEPARATOR + "+context;\n"     # the hunk promises more lines than shown
check(mark_added_lines(trimmed)[1] == ["b;"], f"nor when a trimmed hunk runs into it: {mark_added_lines(trimmed)[1]}")
check(mark_added_lines("x = 1\n") == ("x = 1\n", []), "an input without a diff has no added lines")
check(mark_added_lines("+x = 1\n+y = 2\n")[1] == [], "'+' lines outside a hunk are not added lines")
plain = ("--- a/f.c\n+++ b/f.c\n@@ -1,2 +1,2 @@\n a;\n-b;\n+++c;\n--- a/g.c\n+++ b/g.c\n@@ -1 +1,2 @@\n x;\n+y;\n")
check(mark_added_lines(plain)[1] == ["++c;", "y;"],
      f"hunk line counts decide: an added '++c;' is a line, the next file's headers are not: {mark_added_lines(plain)[1]}")

print("\n=== provider: check question ===")
jev = SystemOneProvider(base_url=base, api_key="test-key")
FakeSystemOne.seen.clear()
c = jev.complete(system="Does it leak?", user="Domain: LOGIC\n\nstate", model="jev-latest", question="check")
q = next(iter(FakeSystemOne.seen[-1]["questions"].values()))
check(len(FakeSystemOne.seen[-1]["questions"]) == 1 and q["type"] == "choice", "one choice question")
check(q["instructions"] == "Does it leak?" and set(q["criteria"]) == {"YES", "NO"}, "the persona asked as YES / NO")
vote, reasoning = _parse_vote(c.text)
check(vote == -1 and close(p_reject_from_text(reasoning), 0.8), f"YES 0.8 is a REJECT with p(REJECT) 0.80: {c.text!r}")
FakeSystemOne.check_answer = {"choice": "NO", "probabilities": {"YES": 0.3, "NO": 0.7}}
vote, reasoning = _parse_vote(jev.complete("q", "s", "jev-latest", question="check").text)
check(vote == 1 and close(p_reject_from_text(reasoning), 0.3), "NO 0.7 is an APPROVE with p(REJECT) 0.30")
FakeSystemOne.check_answer = {"choice": "YES", "probabilities": {"YES": 0.8, "NO": 0.2}}

print("\n=== provider: locate question ===")
FakeSystemOne.seen.clear()
FakeSystemOne.locate_p = lambda keys: {k: {"L2": 0.6, "NONE": 0.3}.get(k, 0.05) for k in keys}
c = jev.complete(system="Which line breaks the build?", user="state", model="jev-latest", question="locate",
                 lines=["int a = 1;", "long b = 2;", "int c = b;"])
q = next(iter(FakeSystemOne.seen[-1]["questions"].values()))
check(list(q["criteria"]) == ["L1", "L2", "L3", "NONE"], f"options: each added line, then NONE: {list(q['criteria'])}")
check("long b = 2;" in q["criteria"]["L2"] and q["instructions"] == "Which line breaks the build?",
      "an option names its line; the persona is the instructions")
vote, reasoning = _parse_vote(c.text)
check(vote == -1 and close(p_reject_from_text(reasoning), 0.7), f"p(NONE) 0.3 -> p(REJECT) 0.70: {c.text!r}")
check("L2" in c.text and "long b = 2;" in c.text, "the readout names the most likely line")

FakeSystemOne.seen.clear()
# Window 1 (L1-L60): NONE 0.8, the rest shared. Window 2 (L61-L70): NONE 0.6 and L65 the likeliest line.
FakeSystemOne.locate_p = lambda keys: ({k: {"NONE": 0.8}.get(k, 0.2 / 60) for k in keys} if "L1" in keys else
                                       {k: {"NONE": 0.6, "L65": 0.15}.get(k, 0.25 / 9) for k in keys})
many = [f"int x{k} = {k};" for k in range(LOCATE_WINDOW + 10)]
c = jev.complete(system="Which line?", user="state", model="jev-latest", question="locate", lines=many)
opts = [list(next(iter(b["questions"].values()))["criteria"]) for b in FakeSystemOne.seen]
check(len(opts) == 2 and opts[0][0] == "L1" and opts[0][-2] == f"L{LOCATE_WINDOW}" and opts[1][0] == f"L{LOCATE_WINDOW + 1}"
      and opts[1][-2] == f"L{LOCATE_WINDOW + 10}" and opts[0][-1] == opts[1][-1] == "NONE",
      f"{LOCATE_WINDOW + 10} lines are asked in two windows, each with NONE")
check(all(b["state"] == "state" for b in FakeSystemOne.seen), "every window is asked on the same state")
_, reasoning = _parse_vote(c.text)
check(close(p_reject_from_text(reasoning), 0.4),
      f"p(REJECT) = 1 - min(0.8, 0.6) = 0.40, the worst window (a product would give 0.52): {reasoning!r}")
check("line=L65" in c.text and "[L65] int x64 = 64;" in c.text,
      f"the readout names the likeliest line over all windows, numbered across them: {c.text.splitlines()[-1]!r}")
check(c.tokens_in == 200, "tokens of both windows are counted")
FakeSystemOne.locate_p = None

FakeSystemOne.locate_p = lambda keys: {k: 0.5 for k in keys if k != "NONE"}
try:
    jev.complete("q", "s", "jev-latest", question="locate", lines=["a"])
    check(False, "an answer without p(NONE) is refused")
except ProviderError as exc:
    check("NONE" in str(exc), "an answer without p(NONE) is refused")
FakeSystemOne.locate_p = None

print("\n=== provider: several questions in one seat ===")
check(persona_questions("  Leak?\n\n Race? \n") == ["Leak?", "Race?"] and persona_questions("One question?") == ["One question?"],
      "a persona's questions are its non-empty lines, stripped")
FakeSystemOne.seen.clear()
FakeSystemOne.by_text = {"Leak?": lambda k: {"YES": 0.2, "NO": 0.8}, "Race?": lambda k: {"YES": 0.5, "NO": 0.5},
                         "Overflow?": lambda k: {"YES": 0.1, "NO": 0.9}}
c = jev.complete(system="Leak?\n\n  Race?  \nOverflow?\n", user="state", model="jev-latest", question="check")
qs = FakeSystemOne.seen[-1]["questions"]
check(len(FakeSystemOne.seen) == 1 and [q["instructions"] for q in qs.values()] == ["Leak?", "Race?", "Overflow?"]
      and all(set(q["criteria"]) == {"YES", "NO"} for q in qs.values()),
      "a persona of three questions is asked as three YES/NO questions in one call")
_, reasoning = _parse_vote(c.text)
check(close(p_reject_from_text(reasoning), 0.64),
      f"p(REJECT) = 1 - 0.8 x 0.5 x 0.9 = 0.64, the chance of any problem: {c.text!r}")
FakeSystemOne.seen.clear()
FakeSystemOne.by_text = {
    "Build?": lambda k: {x: ({"NONE": 0.8} if "L1" in k else {"NONE": 0.9}).get(x, 0.001) for x in k},
    "Runtime?": lambda k: {x: ({"NONE": 0.5, "L2": 0.4} if "L1" in k else {"NONE": 0.9}).get(x, 0.001) for x in k}}
c = jev.complete(system="Build?\nRuntime?", user="state", model="jev-latest", question="locate", lines=many)
check(len(FakeSystemOne.seen) == 2 and all([q["instructions"] for q in b["questions"].values()] == ["Build?", "Runtime?"]
                                           for b in FakeSystemOne.seen),
      "two locate questions are asked together, in each of the two windows")
_, reasoning = _parse_vote(c.text)
check(close(p_reject_from_text(reasoning), 0.6),
      f"a window's p(NONE) is the product over its questions (0.8 x 0.5 = 0.40, 0.9 x 0.9 = 0.81); "
      f"p(REJECT) = 1 - min = 0.60: {reasoning!r}")
check("line=L2" in c.text, "the readout names the likeliest line over questions and windows")
FakeSystemOne.by_text = {}

print("\n=== profiles and refusals ===")
os.environ["TYPESAFE_BASE_URL"] = base
os.environ["TYPESAFE_API_KEY"] = "test-key"
profiles_path = Path(_HOME) / "profiles" / "learned_test.json"
profiles_path.parent.mkdir(parents=True, exist_ok=True)


def seat(name, question=None, provider="jev", model="jev-latest"):
    text = f"P {name}"
    p = AgentProfile(name=name, persona=text, provider=provider, model=model, persona_hash=persona_hash(text))
    p.question = question
    return p


save_profiles(profiles_path, [seat("V"), seat("C", "check"), seat("L", "locate")])
loaded = load_profiles(profiles_path)
check([p.question for p in loaded] == [None, "check", "locate"], "a seat's question survives save/load")
check("question" not in json.loads(profiles_path.read_text(encoding="utf-8"))[0], "a verdict seat's profile has no question key")

def stub_never(persona, code, domain, **kw):
    """Stands in for every model during the refusals: a refusal that fails lets the review reach it."""
    return 1, "p(APPROVE)=0.90  p(REJECT)=0.10  [stub: decision model, no reasoning]", 0, 0, kw.get("provider"), kw.get("model")


real_call = orchestrator._call_agent
orchestrator._call_agent = stub_never
for bad, needle, what in (([seat("T", "check", provider="claude_cli", model="haiku")], "decision",
                           "a question seat on a text model is refused before any model is asked"),
                          ([seat("M", "maybe")], "maybe", "an unknown question is refused")):
    save_profiles(profiles_path, bad)
    try:
        orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False)
        check(False, what)
    except ValueError as exc:
        check(needle in str(exc), what)
orchestrator._call_agent = real_call
save_profiles(profiles_path, [seat("V"), seat("L", "locate")])
try:
    orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False, debate=True)
    check(False, "the debate round refuses question seats")
except ValueError as exc:
    check("debate" in str(exc) and "L" in str(exc), "the debate round refuses question seats")

print("\n=== run_review with question seats (fake server) ===")
save_profiles(profiles_path, [seat("V"), seat("V2"), seat("C", "check"), seat("L", "locate")])
FakeSystemOne.seen.clear()
r = orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False, aggregate="logodds", no_early_stop=True,
                            log_path=Path(_HOME) / "none.jsonl")
by = {v.agent_name: v for v in r.votes}
check(set(by) == {"V", "V2", "C", "L"}, "every seat voted")
locate_states = [b["state"] for b in FakeSystemOne.seen if "NONE" in next(iter(b["questions"].values()))["criteria"]]
other_states = [b["state"] for b in FakeSystemOne.seen if "NONE" not in next(iter(b["questions"].values()))["criteria"]]
check(len(locate_states) == 1 and "+[L1] int b = 1;" in locate_states[0], "the locate seat is shown the marked diff")
check(all("[L1]" not in s and "+int b = 1;" in s for s in other_states), "the other seats are shown the diff unmarked")
check(_evidence_group(by["V"]) == _evidence_group(by["V2"]), "two verdict seats of one model form one group")
check(len({_evidence_group(by[n]) for n in ("V", "C", "L")}) == 3, "a check seat and a locate seat form groups of their own")
rec = session_dict(r, "f.cc")
q_of = {v["agent"]: v.get("question") for v in rec["votes"]}
check(q_of == {"V": None, "V2": None, "C": "check", "L": "locate"} and "question" not in rec["votes"][0],
      f"the log records the question of question seats only: {q_of}")

FakeSystemOne.seen.clear()
try:
    r = orchestrator.run_review("x = 1\n", "LOGIC", profiles_path, verbose=False, aggregate="logodds",
                                no_early_stop=True, log_path=Path(_HOME) / "none.jsonl")
    voted = {v.agent_name for v in r.votes}
except RuntimeError as exc:          # the locate seat was asked without lines and failed the review
    voted = {f"error: {exc}"}
check(voted == {"V", "V2", "C"}, f"a locate seat abstains on an input without added lines: {voted}")
check(all("NONE" not in next(iter(b["questions"].values()))["criteria"] for b in FakeSystemOne.seen),
      "and is not asked")
save_profiles(profiles_path, [seat("L", "locate")])
try:
    orchestrator.run_review("x = 1\n", "LOGIC", profiles_path, verbose=False)
    check(False, "a panel whose every seat abstains gives no verdict")
except RuntimeError as exc:
    check("abstained" in str(exc) and "L" in str(exc), f"a panel whose every seat abstains says so: {exc}")

print("\n=== calibration keeps questions apart ===")
qlog = Path(_HOME) / "questions.jsonl"


def sess(votes, y):
    return {"votes": votes, "oracle": {"type": "DEVELOPER", "x_star": y}}


def vrec(name, vote, p, question=None, provider="jev", model="jev-latest"):
    text = (f"{'REJECT' if p > 0.5 else 'APPROVE'}\np(APPROVE)={1 - p:.2f}  p(REJECT)={p:.2f}  "
            f"[jev-test: decision model, no reasoning]")
    return {"agent": name, "vote": vote, "persona": persona_hash(f"P {name}"), "provider": provider, "model": model,
            "reasoning": text, **({"question": question} if question else {})}


qlog.write_text("".join(json.dumps(s) + "\n" for s in (sess([vrec("L", -1, 0.7, "locate")], -1),
                                                       sess([vrec("L", -1, 0.7)], -1),
                                                       sess([vrec("L", 1, 0.2, "check")], 1))), encoding="utf-8")
cal = Calibrator(qlog)
check(cal.history_size(seat("L", "locate"), "jev", "jev-latest") == 1, "a locate seat counts only locate votes")
check(cal.history_size(seat("L"), "jev", "jev-latest") == 1, "a verdict seat of the same name counts only verdict votes")

print("\n=== learned weights ===")
w = fit_logistic([[1.0, 0.0]] * 10, [1] * 8 + [-1] * 2, 1.0)
check(w is not None and close(w[0], math.log(4), 1e-6) and close(w[1], 0.0, 1e-9),
      f"the intercept has a flat prior: 8 clean of 10 gives ln 4 = {math.log(4):.4f} exactly ({w[0] if w else None})")
# Five clean rows at r = +1, five defective at r = -1: by symmetry the intercept is 0, and the MAP weight solves
# w = 10 (1 - σ(w)), its N(0, 1) prior against the ten rows (root by bisection).
lo_, hi_ = 0.0, 10.0
for _ in range(100):
    mid = (lo_ + hi_) / 2
    lo_, hi_ = (mid, hi_) if mid < 10 * (1 - 1 / (1 + math.exp(-mid))) else (lo_, mid)
w = fit_logistic([[1.0, 1.0]] * 5 + [[1.0, -1.0]] * 5, [1] * 5 + [-1] * 5, 1.0)
check(w is not None and close(w[0], 0.0, 1e-6) and close(w[1], lo_, 1e-6),
      f"a weight is shrunk by its prior: a perfectly separating seat gets w = 10(1 - σ(w)) = {lo_:.4f} "
      f"({w[1] if w else None})")
check(close(seat_logodds(-1, 0.8), math.log(0.25)) and seat_logodds(1, 0.8) == 1.0 and seat_logodds(1, None) == 1.0
      and close(seat_logodds(-1, 0.5), 0.0),
      "a seat's log-odds: ln((1-p)/p) for a p that agrees with its vote; the vote itself for a p that contradicts it, "
      "or for none")
rng, rng2 = random.Random(11), random.Random(12)
reviewers = [(seat("GOOD"), "jev", "jev-latest"), (seat("NOISE", "check"), "jev", "jev-latest")]


def history(n_clean, n_def, with_noise=True, extra=0, informative=True, second=False):
    out = []
    for y in [1] * n_clean + [-1] * n_def:
        centre = (0.75 if y == -1 else 0.25) if informative else rng.choice((0.25, 0.75))
        p_good = min(0.95, max(0.05, centre + rng.gauss(0, 0.15)))
        p_noise = min(0.95, max(0.05, 0.5 + rng.gauss(0, 0.2)))
        votes = [vrec("GOOD", -1 if p_good > 0.5 else 1, p_good)]
        if second:                                                # a second informative verdict seat, same model
            p2 = min(0.95, max(0.05, (0.7 if y == -1 else 0.3) + rng2.gauss(0, 0.15)))
            votes.append(vrec("GOOD2", -1 if p2 > 0.5 else 1, p2))
        if with_noise:
            votes.append(vrec("NOISE", -1 if p_noise > 0.5 else 1, p_noise, "check"))
        out.append(sess(votes, y))
    out += [sess([vrec("OTHER", -1, 0.9)], -1)] * extra       # sessions of another panel
    return out


def se(fit, sessions, rv):
    """A weight's standard error from the fit's curvature in that weight alone: 1 / sqrt(1 + Σ p(1-p) r²)."""
    names = {k[0]: k for k in fit.weights}
    total = 1.0
    for s in sessions:
        r = {v["agent"]: seat_logodds(v["vote"], p_reject_from_text(v["reasoning"])) for v in s["votes"]}
        z = fit.intercept + sum(fit.weights[names[a]] * x for a, x in r.items() if a in names)
        p = 1 / (1 + math.exp(-z))
        total += p * (1 - p) * r.get(rv[0].name, 0.0) ** 2
    return 1 / math.sqrt(total)


llog = Path(_HOME) / "learned.jsonl"
h = history(60, 60, extra=30)
llog.write_text("".join(json.dumps(s) + "\n" for s in h), encoding="utf-8")
fit = Calibrator(llog).learned(reviewers)
check(fit is not None and fit.n_clean == 60 and fit.n_defective == 60,
      "fitted on the 120 sessions where a panel seat voted, not on another panel's")
w_good, w_noise = fit.weight(*reviewers[0]), fit.weight(*reviewers[1])
se_good, se_noise = se(fit, h[:120], reviewers[0]), se(fit, h[:120], reviewers[1])
check(w_good > 3 * se_good and abs(w_noise) < 3 * se_noise,
      f"the informative seat's weight is beyond three standard errors ({w_good:.3f}, SE {se_good:.3f}), "
      f"the uninformative seat's within three of 0 ({w_noise:+.3f}, SE {se_noise:.3f})")

# Uninformative seats on 160 clean and 40 defective sessions: the intercept estimates logit(0.8) = ln 4 with standard
# error 1 / sqrt(200 · 0.8 · 0.2) = 0.18; the bounds are two of them. A bias that kept the base rate would be ≈ 1.4.
SE_B = 1 / math.sqrt(200 * 0.8 * 0.2)
llog.write_text("".join(json.dumps(s) + "\n" for s in history(160, 40, informative=False)), encoding="utf-8")
fit80 = Calibrator(llog).learned(reviewers)
check(fit80 is not None and abs(fit80.intercept - math.log(4)) < 2 * SE_B and abs(fit80.bias) < 2 * SE_B,
      f"uninformative seats, 80%-clean history: the intercept is the base rate ({fit80.intercept:+.3f}, "
      f"ln 4 = {math.log(4):+.3f}) and the bias removes it ({fit80.bias:+.3f}; bound {2 * SE_B:.2f})")

llog.write_text("".join(json.dumps(s) + "\n" for s in history(60, 60, with_noise=False)), encoding="utf-8")
fit_missing = Calibrator(llog).learned(reviewers)
check(fit_missing is not None and fit_missing.n_clean == 60 and abs(fit_missing.weight(*reviewers[1])) < 1e-6,
      "a seat absent from every session counts as no evidence and gets no weight")

part = history(200, 200)                   # enough sessions that three standard errors stay well under 1
for s in part:
    if s["oracle"]["x_star"] == 1:          # the check seat votes only on the defective changes, uninformatively
        s["votes"] = s["votes"][:1]
llog.write_text("".join(json.dumps(s) + "\n" for s in part), encoding="utf-8")
fit_part = Calibrator(llog).learned(reviewers)
w_part, se_part = fit_part.weight(*reviewers[1]), se(fit_part, part, reviewers[1])
check(abs(w_part) < 3 * se_part,
      f"a seat that voted only on defective changes is not rewarded for its absence: weight {w_part:+.3f} "
      f"within three standard errors ({se_part:.3f}) of 0")

llog.write_text("".join(json.dumps(s) + "\n" for s in history(19, 60)), encoding="utf-8")
few = Calibrator(llog)
check(few.learned(reviewers) is None and "too few" in few.learned_status and "19 clean" in few.learned_status,
      f"19 clean labels are too few: no fit, and the status says why ({few.learned_status})")

print("\n=== learned decision ===")
for lam, dom, want in ((-3.0, "LOGIC", (Decision.REJECT, Confidence.HIGH)),
                       (3.0, "LOGIC", (Decision.APPROVE, Confidence.HIGH)),
                       (0.3, "LOGIC", (Decision.APPROVE, Confidence.LOW)),
                       (-1.0, "LOGIC", (Decision.REJECT, Confidence.MEDIUM)),
                       (0.3, "SECURITY", (Decision.REJECT, Confidence.LOW))):
    d, c, norm = learned_decision(lam, dom)
    check((d, c) == want and close(norm, 2 / (1 + math.exp(-(lam - logodds_tau(dom)))) - 1),
          f"Λ {lam:+.1f} in {dom}: {d.value} [{c.value}]")

print("\n=== run_review, aggregate='learned' ===")
llog.write_text("".join(json.dumps(s) + "\n" for s in history(60, 60, second=True)), encoding="utf-8")
panel3 = reviewers[:1] + [(seat("GOOD2"), "jev", "jev-latest")] + reviewers[1:]
calls = []
R99 = math.log(0.01 / 0.99)                 # every stubbed seat answers p(REJECT) 0.99


def stub(persona, code, domain, **kw):
    calls.append(persona)
    return -1, "p(APPROVE)=0.01  p(REJECT)=0.99  [jev-test: decision model, no reasoning]", 1, 1, \
        kw["provider"], kw["model"]


orchestrator._call_agent = stub
save_profiles(profiles_path, [rv[0] for rv in panel3])
r = orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False, aggregate="learned", log_path=llog)
fit = Calibrator(llog).learned(panel3)
want = fit.bias + sum(fit.weight(*rv) * R99 for rv in panel3)
check(len(calls) == 3 and r.aggregate == "learned", "every seat is asked: no early stop on learned weights")
check(fit.weight(*panel3[0]) > 0 and fit.weight(*panel3[1]) > 0 and close(r.sprt_lambda, want, 1e-9),
      f"Λ = bias + Σ w·r, summed over seats, two of them on one model: {want:+.3f}: got {r.sprt_lambda:+.3f}")
check(r.decision is Decision.REJECT and r.confidence is (Confidence.HIGH if want <= B else Confidence.MEDIUM),
      f"{r.decision.value} [{r.confidence.value}]")
rec = session_dict(r, "f.cc")
check(rec.get("aggregate") == "learned" and all(v["calibration"] == "learned" for v in rec["votes"])
      and close(rec["learned"]["bias"], round(fit.bias, 4)) and rec["learned"]["n_clean"] == 60,
      "the record carries the mode, each vote's learned evidence and the fit")
check(all(close(v["evidence"], round(fit.weight(*rv) * R99, 4)) for v, rv in zip(rec["votes"], panel3)),
      "each vote's evidence is its weight times its log-odds")

real_bandit = orchestrator.bandit_vote
orchestrator.bandit_vote = lambda path: (-1, "one HIGH finding", 1, 1)
r = orchestrator.run_review(CODE, "SECURITY", profiles_path, verbose=False, aggregate="learned", log_path=llog,
                            sast_path=Path(_HOME) / "x.py")
orchestrator.bandit_vote = real_bandit
want_sast = want + SAST_OMEGA * LLR_REJECT
check(r.votes[0].agent_name == SAST_AGENT_NAME and r.votes[0].calibration == "fixed"
      and close(r.sprt_lambda, want_sast, 1e-9),
      f"the SAST vote adds its fixed evidence to the learned Λ: {want_sast:+.3f}, got {r.sprt_lambda:+.3f}")

calls.clear()
r = orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False, aggregate="learned",
                            log_path=Path(_HOME) / "empty.jsonl")
check(r.aggregate == "logodds" and all(v.calibration != "learned" for v in r.votes),
      "without enough labels the review runs in logodds mode and says so")
real_fit = calibration.fit_logistic
calibration.fit_logistic = lambda *a, **k: None          # a fit that does not converge
printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    r = orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=True, aggregate="learned", log_path=llog)
calibration.fit_logistic = real_fit
check(r.aggregate == "logodds" and "did not converge" in printed.getvalue() and "too few" not in printed.getvalue(),
      "a fit that does not converge falls back too, and is reported as such, not as too few labels")
save_profiles(profiles_path, [seat("GOOD")])          # verdict seats only: the refusal must be the mode's own
try:
    orchestrator.run_review(CODE, "LOGIC", profiles_path, verbose=False, aggregate="learned", debate=True)
    check(False, "learned with debate is refused")
except ValueError as exc:
    check("learned" in str(exc) and "debate" in str(exc), f"learned with debate is refused: {exc}")
orchestrator._call_agent = real_call

target = Path(_HOME) / "x.py"
target.write_text("x = 1\n", encoding="utf-8")
proc = subprocess.run([sys.executable, "-B", "-m", "warf", "review", str(target), "--aggregate", "learned", "--debate"],
                      capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check(proc.returncode == 2 and "--debate" in proc.stderr and "invalid choice" not in proc.stderr,
      "CLI: --aggregate learned is a choice, and with --debate exits 2 with a message")

server.shutdown()
print("\nAll question-seat and learned-aggregation checks passed.")
