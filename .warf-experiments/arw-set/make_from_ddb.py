"""Write the Arrow set's prompt files and scripts from the DuckDB set's (2026-11-16, before mining). Every
replacement must match exactly once or more; the script stops otherwise. Run once.

    python make_from_ddb.py"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = HERE.parent / "ddb-set"
DDB_REPO, ARW_REPO = r"C:\workdir\warf\repos\duckdb", r"C:\workdir\warf\repos\arrow"


def conv(name, reps, new=None):
    s = (S / name).read_bytes().decode("utf-8")
    for a, b in reps:
        if a not in s:
            raise SystemExit(f"{name}: {a[:70]!r} not found")
        s = s.replace(a, b)
    (HERE / (new or name)).write_bytes(s.encode("utf-8"))
    print("wrote", new or name)


conv("judge_prompt.md", [
    ("DuckDB set, fixed 2026-11-14; text of ../rdb-set/judge_prompt.md", "Arrow set, fixed 2026-11-16; text of ../ddb-set/judge_prompt.md"),
    ("You may read the DuckDB repository at " + DDB_REPO, "You may read the Arrow repository at " + ARW_REPO)])
conv("profile_prompt.md", [
    ("DuckDB set, fixed 2026-11-14", "Arrow set, fixed 2026-11-16"), ("DuckDB's past changes", "Arrow's past changes"),
    ("a new DuckDB change", "a new Arrow change"), ('"DuckDB defect profile', '"Arrow defect profile')])
conv("checks_prompt.md", [
    ("DuckDB set, fixed 2026-11-14", "Arrow set, fixed 2026-11-16"), ("DuckDB's past changes", "Arrow's past changes"),
    ("a new DuckDB change", "a new Arrow change")])
conv("judge_agent_brief.md", [
    ("DuckDB set, 2026-11-14", "Arrow set, 2026-11-16"), ("a labelled set of DuckDB changes", "a labelled set of Arrow changes"),
    ("ddb-set", "arw-set"), (DDB_REPO, ARW_REPO), ("DuckDB repository", "Arrow repository")])
conv("judge.py", [("DuckDB set", "Arrow set")])
for name in ("write_history.py", "select_defects.py"):
    conv(name, [("DuckDB", "Arrow")])
conv("select_matched_ddb.py", [("DuckDB", "Arrow"), ("select_matched_ddb.py", "select_matched_arw.py")], "select_matched_arw.py")
