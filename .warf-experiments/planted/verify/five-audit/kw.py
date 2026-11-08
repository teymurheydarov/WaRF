"""For each discordant item: does each seat's full reply mention the issue Claude alone rejected on?"""
import json, re
from pathlib import Path
H = Path(__file__).resolve().parents[2]
def load(arm):
    d = {}
    for f in sorted(H.glob(f"{arm}.w*.jsonl")):
        for l in f.open(encoding="utf-8"):
            r = json.loads(l); d[r["planted"]["id"]] = r
    return d
five = load("claude-standard"); one = load("claude")
KW = {"d6c93de:gsFileManager.cpp:clean": r"header|declar",
      "893626d:test_spectra.cpp:clean": r"alias",
      "be9bf4b:Householder.h:planted": r"<=|upstream",
      "838db33:gsKnotDomainIterator.h:clean": r"wrap|unsigned",
      "9790e5a:gsFileManager.cpp:clean": r"POSIX|::mkdir",
      "9e5b11e:gsBSplineBasis.h:clean": r"TensorBoundaryGeometryType|naming|T` prefix|T prefix|name"}
for i, kw in KW.items():
    row = [f"CLAUDE:{one[i]['decision'][0]}:{len(re.findall(kw, one[i]['planted']['call']['reply']))}"]
    for c in five[i]["planted"]["calls"]:
        row.append(f"{c['agent']}:{c['reply'].split()[0][0]}:{len(re.findall(kw, c['reply']))}:{len(c['reply'])}")
    print(i, kw, "|", "  ".join(row))
