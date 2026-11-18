"""The arms of the PPSSPP test (README.md "The arms"), fixed 2026-11-16 before mining: ../ddb-set/panel.py with
"PPSSPP" for "DuckDB" in the locate build question.

    from panel import panel3, lo_ctx, five      # AgentProfile lists; panel3() and five() need checks.md"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent))
from warf.state import AgentProfile, load_profiles, persona_hash  # noqa: E402

LOCATE_BUILD = ("Which added line makes this change fail to build on a configuration PPSSPP supports: a compiler "
                "error, or a warning that -Werror or /WX turns into an error (sign-compare, shadowing, an unused "
                "variable or parameter in release builds, a missing override, a narrowing conversion, a format "
                "specifier that does not match its argument, a name unavailable on another platform, compiler or "
                "build configuration PPSSPP supports)? Choose NONE if every added line builds everywhere.")
LOCATE_RUNTIME = ("Which added line introduces a runtime defect: a wrong result, a crash, a leak, a read of an "
                  "uninitialised or freed value, a data race or deadlock, or a test that can hang or fail "
                  "intermittently? Choose NONE if no added line does.")
DEFAULT_PERSONA = "Should this change be merged as it is? A defect you can point to is a REJECT."   # run_narrow


def personas():
    return load_profiles(EXP / "pooled-dev" / "history" / "profiles" / "uniform.json", reconcile=False)


def seat(name, persona, model, question=None):
    return AgentProfile(name=name, persona=persona, provider="jev", model=model, persona_hash=persona_hash(persona),
                        question=question)


def checks():
    lines = [l.strip() for l in (HERE / "checks.md").read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) != 7:
        raise SystemExit(f"checks.md must hold seven questions, has {len(lines)}")
    return lines


def question_seats():
    return [seat("LOCATE", LOCATE_BUILD + "\n" + LOCATE_RUNTIME, "jev-1.14", "locate"),
            seat("CHECKLIST", "\n".join(checks()), "jev-1.14", "check"),
            seat("DEFAULT", DEFAULT_PERSONA, "jev-1.14")]


def lo_ctx():
    return personas()


def panel3():
    by = {p.name: p for p in personas() + question_seats()}
    return [by["BOUNDARY"], by["LOCATE"], by["CHECKLIST"]]


def five():
    by = {p.name: p for p in personas() + question_seats()}
    return [by[n] for n in ("SKEPTIC", "BOUNDARY", "DEFAULT", "LOCATE", "CHECKLIST")]
