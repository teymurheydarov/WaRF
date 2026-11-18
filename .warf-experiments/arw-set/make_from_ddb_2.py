"""Second part of the Arrow scripts from the DuckDB set's (2026-11-16, before any Arrow candidate is judged):
build_clean_arw.py, run_arw.py, score_arw.py. Every replacement must match; the script stops otherwise.

    python make_from_ddb_2.py"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = HERE.parent / "ddb-set"


def conv(name, reps, new):
    s = (S / name).read_bytes().decode("utf-8")
    for a, b in reps:
        if a not in s:
            raise SystemExit(f"{name}: {a[:70]!r} not found")
        s = s.replace(a, b)
    (HERE / new).write_bytes(s.encode("utf-8"))
    print("wrote", new)


conv("build_clean_ddb.py", [
    ('"""Mine DuckDB\'s clean controls', '"""Mine Arrow\'s clean controls'),
    ("../rdb-set/build_clean_matched.py pointed at DuckDB (build_ddb.py's settings), with the test defects of\n"
     "defects.jsonl, and no file under third_party/;",
     "../ddb-set/build_clean_ddb.py pointed at Arrow (build_arw.py's settings), with the test defects of\n"
     "defects.jsonl, and no vendored or generated file (build_arw.excluded);"),
    ("python build_clean_ddb.py", "python build_clean_arw.py"),
    ("import build_ddb  # noqa: E402,F401  (points build_rdb at DuckDB)\nfrom build_ddb import B, VENDORED  # noqa: E402",
     "import build_arw  # noqa: E402,F401  (points build_rdb at Arrow)\nfrom build_arw import B, excluded  # noqa: E402"),
    ("and not m.group(2).startswith(VENDORED)", "and not excluded(m.group(2))")], "build_clean_arw.py")
conv("run_ddb.py", [
    ('"""Jev through WaRF on the frozen DuckDB set', '"""Jev through WaRF on the frozen Arrow set'),
    ("(ddb_context.md + the defect profile)", "(arw_context.md + the defect profile)"),
    ("python run_ddb.py", "python run_arw.py"),
    ('tempfile.mkdtemp(prefix="warf-ddb-")', 'tempfile.mkdtemp(prefix="warf-arw-")'),
    ('(HERE / "ddb_context.md")', '(HERE / "arw_context.md")')], "run_arw.py")
conv("score_ddb.py", [
    ('"""Score the DuckDB test', '"""Score the Arrow test'),
    ("python score_ddb.py", "python score_arw.py")], "score_arw.py")
