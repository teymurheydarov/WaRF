"""Jev paraphrase ensemble of the 7 generic narrow checks (development, ../../DEV.md 2026-11-09).

Two paraphrases of each generic check of run_narrow.py, written before any result was seen: same
question, different words, generic C++ only (no dev defect descriptions were used). The 14 paraphrases
and the verdict are asked in one call per state (whole change and each hunk), exactly as run_narrow.py
asks; only the check list differs.

    python .warf-experiments/real-set/jev-narrow/paraphrase/run_paraphrase.py [--limit N] [--workers 4]
    # resumes; writes answers_paraphrase.jsonl in this folder"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_narrow  # noqa: E402

PARA = {
    "offbyone_a": "Can an index, counter or range bound in the changed lines step one past the end, stop one too "
                  "early, or otherwise go outside the valid range?",
    "offbyone_b": "Do the changed lines access an element or iterate over a range with a limit that is one too "
                  "large or too small, or that exceeds the size of the container?",
    "condition_a": "Does a changed line test the wrong thing: a reversed comparison, a negated condition, a wrong "
                   "sign, or a wrong logical or arithmetic operator?",
    "condition_b": "Would a boolean expression, comparison or sign in the changed lines give the opposite or "
                   "otherwise incorrect result for some inputs?",
    "wrongvar_a": "Does a changed line refer to a different variable, field, parameter or function than the one "
                  "intended, such as a similarly named one or one from the wrong scope?",
    "wrongvar_b": "Is an identifier in the changed lines mixed up with another one, so that the wrong object, "
                  "member, argument or call is used?",
    "missing_a": "Does the change leave out something the rest of the code expects: an unhandled case, a variable "
                 "that is not initialised, a container that is not resized, or state that is not updated?",
    "missing_b": "Is there a step the change should perform but omits, such as handling a branch, setting up a "
                 "value, adjusting a size or keeping related data in sync?",
    "memory_a": "Can the changed code mishandle memory or object lifetimes: a reference or pointer to a destroyed "
                "object, a leaked allocation, freeing twice, or reading an uninitialised value?",
    "memory_b": "Does the change create a resource or lifetime problem, for example returning a reference to a "
                "temporary, losing ownership of allocated memory, deleting something twice, or using a variable "
                "before it is set?",
    "interface_a": "Does the change alter behaviour that other code depends on, such as a function's parameters, "
                   "return type, return value or semantics, so that existing callers become wrong?",
    "interface_b": "Would code that uses the changed functions or classes break or behave differently because the "
                   "change modified their signature, result or contract?",
    "compile_a": "Would a compiler on some supported platform or build configuration reject the changed code, for "
                 "example with a template, const-correctness or missing-header error?",
    "compile_b": "Does the change contain code that does not build everywhere it must, such as an invalid template "
                 "use, a const violation, a missing declaration or include, or a syntax error?",
}


if __name__ == "__main__":
    run_narrow.CHECKS = PARA            # questions() reads the module's CHECKS at call time
    if "--out" not in sys.argv:
        sys.argv += ["--out", str(HERE / "answers_paraphrase.jsonl")]
    if "--workers" not in sys.argv:
        sys.argv += ["--workers", "4"]
    run_narrow.main()
