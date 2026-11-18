"""Mutation check of tools/test_learned.py: break the question-seat and learned-aggregation code one way
at a time, in a copy of the package, and require the test to fail on each.

    python mutants.py      # writes mutants.log"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MUTANTS = [
    ("group key ignores the question", "warf/orchestrator.py",
     '+ (f"@{question}" if question else "")', ""),
    ("calibration ignores the question", "warf/calibration.py",
     'v.get("evidence_source") or "", v.get("question") or "")', 'v.get("evidence_source") or "", "")'),
    ("bias keeps the base rate", "warf/calibration.py",
     "return self.intercept - self.prior_logodds", "return self.intercept"),
    ("intercept penalised", "warf/calibration.py", [
        ("g = [0.0] + [-wj / prior_sd ** 2 for wj in w[1:]]", "g = [-wj / prior_sd ** 2 for wj in w]"),
        ("(1.0 / prior_sd ** 2 if a == b and a > 0 else 0.0)", "(1.0 / prior_sd ** 2 if a == b else 0.0)"),
        ("sum(wj * wj for wj in w[1:])", "sum(wj * wj for wj in w)")]),
    ("weights not penalised", "warf/calibration.py", [
        ("g = [0.0] + [-wj / prior_sd ** 2 for wj in w[1:]]", "g = [0.0] * k"),
        ("(1.0 / prior_sd ** 2 if a == b and a > 0 else 0.0)", "0.0"),
        ("sum(wj * wj for wj in w[1:])", "0.0")]),
    ("learned mode stops early", "warf/orchestrator.py",
     "return SPRTState(lambda_=lam, k=len(votes_so_far)), None", "return SPRTState(lambda_=lam, k=len(votes_so_far)), sprt_boundary(lam)"),
    ("locate reads p(NONE) as p(REJECT)", "warf/providers.py",
     'self._rendered(1.0 - p_none, f"line=', 'self._rendered(p_none, f"line='),
    ("locate asks only the first window", "warf/providers.py",
     "for start in range(0, len(lines), LOCATE_WINDOW):", "for start in range(0, min(len(lines), 1), LOCATE_WINDOW):"),
    ("check reads p(NO)", "warf/providers.py",
     'p_no *= 1.0 - float(probs["YES"])', 'p_no *= 1.0 - float(probs["NO"])'),
    ("marking also tags the function context", "warf/questions.py",
     "diff, sep, rest = code.partition(_SEPARATOR)", 'diff, sep, rest = code, "", ""'),
    ("no abstention without added lines", "warf/orchestrator.py",
     'if profile.question == "locate" and not mark_added_lines(seat_input)[1]:', "if False:"),
    ("question seats allowed on text models", "warf/orchestrator.py",
     'if provider_kind(prov) != "decision":', "if False:"),
    ("a missing seat counts as its vote", "warf/calibration.py",
     "x, seen = [0.0] * len(keys), set()", "x, seen = [1.0] * len(keys), set()"),
    ("no fallback to logodds", "warf/orchestrator.py",
     'aggregate, calibrator = "logodds", labelled', 'aggregate, calibrator = "learned", None'),
    ("the log drops the question", "warf/logger.py", 'rec["question"] = v.question', "pass"),
    # found by the cold review (2026-11-14), and the changes made after it
    ("learned allowed with debate", "warf/orchestrator.py",
     'if aggregate != "vote" and debate:', 'if aggregate == "logodds" and debate:'),
    ("SAST vote left out of the learned Λ", "warf/orchestrator.py",
     'sast_record.evidence, sast_record.calibration = vote_evidence(sast_v, SAST_OMEGA), "fixed"\n'
     '                sprt_state, boundary = _learned_step(votes)',
     'sast_record.evidence, sast_record.calibration = None, "fixed"\n'
     '                sprt_state, boundary = _learned_step(votes)'),
    ("a p that contradicts its vote is used", "warf/calibration.py",
     "if p_reject is not None and not (p_reject - 0.5) * vote > 0:", "if p_reject is not None:"),
    ("best line numbered within its window", "warf/providers.py",
     "best_p, best = float(p), start + k", "best_p, best = float(p), k"),
    ("learned Λ pooled by group means", "warf/orchestrator.py",
     "lam = learned_fit.bias + sum(v.evidence for v in votes_so_far if v.evidence is not None)",
     "lam = learned_fit.bias + _pooled([v for v in votes_so_far if v.evidence is not None])[0]"),
    ("windows multiplied", "warf/providers.py", "p_none = min(p_none, window_none)", "p_none *= window_none"),
    ("hunk counts ignored", "warf/questions.py", "elif old_left > 0 or new_left > 0:", "elif True:"),
    # several questions in one seat (the five-seat limit, 2026-11-14)
    ("a check seat asks only its first question", "warf/providers.py",
     "texts = persona_questions(system) or [system]\n        body = self._ask(model, user, texts, CHECK_CRITERIA",
     "texts = (persona_questions(system) or [system])[:1]\n        body = self._ask(model, user, texts, CHECK_CRITERIA"),
    ("checks pooled by their maximum", "warf/providers.py",
     'p_no *= 1.0 - float(probs["YES"])', 'p_no = min(p_no, 1.0 - float(probs["YES"]))'),
    ("locate questions pooled by their minimum", "warf/providers.py",
     "window_none *= float(probs[LOCATE_NONE])", "window_none = min(window_none, float(probs[LOCATE_NONE]))"),
    ("question lines not stripped", "warf/questions.py",
     "return [line.strip() for line in persona.splitlines() if line.strip()]",
     "return [line for line in persona.splitlines() if line.strip()]"),
    ("fallback reason not reported", "warf/orchestrator.py",
     'print(f"  [learned] {labelled.learned_status}: pooling as logodds")',
     'print("  [learned] too few labelled sessions: pooling as logodds")'),
]


def run(tree):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("TYPESAFE_", "LAYA_"))}
    return subprocess.run([sys.executable, "-B", "tools/test_learned.py"], cwd=tree, capture_output=True,
                          text=True, env={**env, "PYTHONIOENCODING": "utf-8"}, timeout=600)


def copy():
    tree = Path(tempfile.mkdtemp(prefix="warf-mutant-"))
    shutil.copytree(ROOT / "warf", tree / "warf", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "tools", tree / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    return tree


out = []
control = copy()
r = run(control)
shutil.rmtree(control, ignore_errors=True)
if r.returncode != 0:
    sys.exit(f"the unmutated copy fails, so no mutant can be judged: {(r.stdout + r.stderr)[-400:]}")
out.append("  control: the unmutated copy passes"); print(out[-1], flush=True)
caught = 0
for name, rel, *edit in MUTANTS:
    edits = edit[0] if len(edit) == 1 else [tuple(edit)]
    tree = copy()
    f = tree / rel
    src = f.read_text(encoding="utf-8")
    bad = [old for old, _ in edits if src.count(old) != 1]
    if bad:
        out.append(f"  ????  {name}: pattern not found once: {bad[0][:60]}"); print(out[-1], flush=True)
        continue
    if name == "learned mode stops early":
        src = src.replace("from .engine import (", "from .engine import sprt_boundary\nfrom .engine import (", 1)
    for old, new in edits:
        src = src.replace(old, new)
    f.write_text(src, encoding="utf-8")
    r = run(tree)
    fail = [l for l in r.stdout.splitlines() if "FAIL" in l] or (r.stderr.strip().splitlines()[-1:] if r.returncode else [])
    ok = r.returncode != 0
    caught += ok
    out.append(f"  {'caught' if ok else 'MISSED'}  {name}: {(fail[0].strip() if fail else '')[:110]}")
    print(out[-1], flush=True)
    shutil.rmtree(tree, ignore_errors=True)
out.append(f"\n{caught} of {len(MUTANTS)} mutants caught")
print(out[-1])
(Path(__file__).resolve().parent / "mutants.log").write_text("\n".join(out) + "\n", encoding="utf-8")
