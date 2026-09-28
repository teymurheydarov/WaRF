from pathlib import Path
# A dev tool, not part of the package: make the checkout importable.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warf.detector import detect_domain  # noqa: E402

tests = [
    (r"..\validation\M-04_path_traversal\file_utils.py",   "SECURITY"),
    (r"..\validation\M-05_slow_divide\calculator.cpp",      "PERFORMANCE"),
    (r"..\validation\M-01_no_div_guard\calculator.cpp",     "LOGIC"),
    (r"..\validation\M-03_missing_tests\test_calculator.py","LOGIC"),
]

all_ok = True
for path_str, expected in tests:
    p = Path(path_str)
    code = p.read_text(encoding="utf-8")
    domain, reason = detect_domain(p, code)
    status = "OK  " if domain == expected else "FAIL"
    if domain != expected:
        all_ok = False
    print(f"  {status}  {p.name:<32}  -> {domain:<12}  ({reason})")

print()
print("All correct." if all_ok else "Some detections wrong — check patterns.")
