"""Write the PPSSPP set's prompt files and scripts from the Arrow set's (2026-11-16, before any PPSSPP judging;
the Arrow ones came from DuckDB's with only names and paths changed). Names and paths only; every file must
contain at least one of them, and no "Arrow"/"arrow"/"arw" may remain. build_pp.py is written by hand.

    python make_from_arw.py"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = HERE.parent / "arw-set"
REPS = [("arw-set", "pp-set"), ("arw_context", "pp_context"), ("build_clean_arw", "build_clean_pp"),
        ("select_matched_arw", "select_matched_pp"), ("build_arw", "build_pp"), ("run_arw", "run_pp"),
        ("score_arw", "score_pp"), ("warf-arw-", "warf-pp-"), (r"C:\workdir\warf\repos\arrow", r"C:\workdir\warf\repos\ppsspp"),
        ("Arrow", "PPSSPP")]
FILES = {"judge_prompt.md": None, "profile_prompt.md": None, "checks_prompt.md": None, "judge_agent_brief.md": None,
         "judge.py": None, "write_history.py": None, "select_defects.py": None, "panel.py": None,
         "select_matched_arw.py": "select_matched_pp.py", "build_clean_arw.py": "build_clean_pp.py",
         "run_arw.py": "run_pp.py", "score_arw.py": "score_pp.py"}
for name, new in FILES.items():
    s = (S / name).read_bytes().decode("utf-8")
    t = s
    for a, b in REPS:
        t = t.replace(a, b)
    if t == s:
        raise SystemExit(f"{name}: nothing replaced")
    left = re.findall(r".*(?:\bArrow\b|\barrow\b|arw).*", t)
    if left:
        raise SystemExit(f"{name}: still names Arrow: {left[:3]}")
    (HERE / (new or name)).write_bytes(t.encode("utf-8"))
    print("wrote", new or name)
