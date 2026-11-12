"""Jev with G+Smo-specific narrow checks, whole change and per hunk (development, ../DEV.md 2026-11-09).

The checks group the one-sentence descriptions of the 66 dev defects (items.jsonl "defect") into ten
G+Smo failure kinds. They are built from the dev set, so their dev scores are in-sample; only a later
confirm-set run can say whether they generalise. Request, framing and hunk split are run_narrow.py's;
only the check list differs.

    python .warf-experiments/real-set/jev-narrow/run_gismo.py [--workers N]   # resumes; answers_gismo.jsonl"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_narrow  # noqa: E402

GISMO = {
    "physical": "Does the changed code use parametric quantities (parametric gradients, normals, measures or "
                "domain sizes) where physical ones mapped through the geometry are needed, or the reverse?",
    "dimension": "Does the changed code hard-code a dimension (1, 2 or 3 components, d instead of d-1, a fixed "
                 "row or column index) or mix up the domain and target dimension, so it is wrong for other dimensions?",
    "patch": "Does the changed code handle only one patch, side or corner, or mix a global index with a "
             "patch-local index, so it is wrong for multipatch geometries?",
    "scalar": "Does the changed code assume the scalar type is double (fixed double types, mixed T and int or "
              "double arguments to templates or ternaries), so it fails for other scalar types T?",
    "portable": "Does the changed code rely on something one supported compiler or standard rejects: a GNU or "
                "MSVC extension, alternative tokens, C++11 features in C++98 code, or an invalid preprocessor line?",
    "layout": "Does the changed code get an Eigen or gsMatrix layout wrong: rows and columns swapped, a wrong "
              "block or reshape, conservativeResize used as a reshape, or arguments in the wrong order?",
    "template": "Does the change break the match between declarations and definitions: an explicit instantiation "
                "or specialization that matches no template, an ambiguous overload, a lost override, or a "
                "declaration in a different namespace?",
    "state": "Does the change clear, reset or overwrite member state or a buffer (clear, setZero, resize) that "
             "callers or later calls still rely on?",
    "spline": "Does the changed code get knot vector, degree, multiplicity, level or basis-function counting "
              "wrong, for example raising instead of lowering, or counting functions for one case only?",
    "input": "Does the changed code read input it does not check: an option of the wrong type, a missing XML "
             "attribute or a null pointer, or memory it does not own?",
}


if __name__ == "__main__":
    run_narrow.CHECKS = GISMO           # questions() reads the module's CHECKS at call time
    if "--out" not in sys.argv:
        sys.argv += ["--out", str(run_narrow.HERE / "answers_gismo.jsonl")]
    run_narrow.main()
