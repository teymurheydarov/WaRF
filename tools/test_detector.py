from pathlib import Path
# A dev tool, not part of the package: make the checkout importable.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from warf.detector import detect_domain  # noqa: E402

# Relative to the checkout, read from it whatever the working directory. detect_domain matches the path too, so it
# gets this relative one: the absolute path would let a parent folder ("cache", "perf", ...) change the domain.
tests = [
    ("validation/M-04_path_traversal/file_utils.py",    "SECURITY"),
    ("validation/M-05_slow_divide/calculator.cpp",       "PERFORMANCE"),
    ("validation/M-01_no_div_guard/calculator.cpp",      "LOGIC"),
    ("validation/M-03_missing_tests/test_calculator.py", "LOGIC"),
]

all_ok = True
for path_str, expected in tests:
    p = Path(path_str)
    code = (ROOT / p).read_text(encoding="utf-8")
    domain, reason = detect_domain(p, code)
    status = "OK  " if domain == expected else "FAIL"
    if domain != expected:
        all_ok = False
    print(f"  {status}  {p.name:<32}  -> {domain:<12}  ({reason})")

# A path keyword counts at the start of a word of the path (split at separators, camelCase and digits), and only
# inside the project: the folders above it, which an absolute path names down from the drive, say nothing about
# the file. Neutral code, so the path decides. Before the fix the keyword could sit anywhere in the path string.
import os  # noqa: E402
import tempfile  # noqa: E402

os.chdir(ROOT)                                   # the working directory is a fallback root: make it known
work = Path(tempfile.mkdtemp(prefix="warf-detector-")).resolve()
(work / "authoring" / "project" / ".git").mkdir(parents=True)
(work / "authoring" / "project" / "src" / "auth").mkdir(parents=True)
path_tests = [
    ("src/util/uncertainty.cpp",                    "LOGIC"),        # "cert" inside a word
    ("casadi/core/oracle_function.cpp",             "LOGIC"),        # "acl"
    ("external/Eigen/src/StlSupport/StdVector.h",   "LOGIC"),        # "tls" across Stl|Support
    ("external/zlib/inffast.c",                     "LOGIC"),        # "fast"
    ("src/gsLowRankFitting.h",                      "LOGIC"),        # "slow" across gs|Low
    ("src/auth/login.py",                           "SECURITY"),
    ("net/OAuthClient.java",                        "SECURITY"),
    ("src/PasswordHash.cpp",                        "SECURITY"),
    ("web/XSSFilter.java",                          "SECURITY"),
    ("bench/run.cc",                                "PERFORMANCE"),
    ("src/gsPerformanceTest.cpp",                   "PERFORMANCE"),
    (work / "authoring" / "project" / "src" / "math.cc",         "LOGIC"),     # "auth" above the project
    (work / "authoring" / "project" / "src" / "auth" / "util.cc", "SECURITY"),  # a folder inside it counts
]
if not any((p / ".git").exists() for p in work.parents):
    path_tests.append((work / "authoring" / "math.cc", "LOGIC"))   # in no project: its file name only
    path_tests.append(("cwd", "SECURITY"))                         # ... unless under the working directory
else:
    print("  --    a folder above the temporary directory holds a .git: the no-project cases are not run")
for path_str, expected in [t for t in path_tests if t[0] == "cwd"]:
    path_tests.remove((path_str, expected))
    os.chdir(work / "authoring")
    domain, reason = detect_domain(work / "authoring" / "auth" / "util.cc", "int x;\n")
    os.chdir(ROOT)
    status = "OK  " if domain == expected else "FAIL"
    if domain != expected:
        all_ok = False
    print(f"  {status}  {'<cwd>/auth/util.cc, no .git above':<44}  -> {domain:<12}  ({reason})")
for path_str, expected in path_tests:
    p = Path(path_str)
    domain, reason = detect_domain(p, "int x;\n")
    status = "OK  " if domain == expected else "FAIL"
    if domain != expected:
        all_ok = False
    print(f"  {status}  {str(p)[-44:]:<44}  -> {domain:<12}  ({reason})")

print()
print("All correct." if all_ok else "Some detections wrong — check patterns.")
sys.exit(0 if all_ok else 1)
