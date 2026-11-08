"""Dump Claude-one replies plus label evidence (fixes, blamed lines) for reading."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FA = HERE.parent.parent; EXP = FA.parent
rows = {r["id"]: r for r in json.loads((HERE / "table.json").read_text(encoding="utf-8"))}
lab = {}
want = {(r["commit"], r["file"]) for r in rows.values()}
for l in (EXP / "laya-sweep/labels.jsonl").open(encoding="utf-8"):
    d = json.loads(l)
    if (d["commit"], d["file"]) in want: lab[(d["commit"], d["file"])] = d
rec = {}
for p in sorted(FA.glob("claude-one.w*.jsonl")):
    for l in p.open(encoding="utf-8"):
        r = json.loads(l); rec[r["four"]["id"]] = r
sel_ids = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] else None
mode = sys.argv[2] if len(sys.argv) > 2 else "both"
n = int(sys.argv[3]) if len(sys.argv) > 3 else 900
for i, r in rows.items():
    if sel_ids and i not in sel_ids: continue
    L = lab[(r["commit"], r["file"])]
    print(f"##### {i} {r['group']} {r['file']} {r['commit'][:10]} claude-one {r['claude-one']} p_claude {r['p_claude']} jev {r['jev_p']}")
    print(f"  label {L['label']} later_days {L['later_days']:.0f} blamed {L['blamed_lines']} lines {L['lines'][:12]} defect_at {L.get('defect_at')}")
    for f in L["fixes"][:4]:
        print("  fix", {k: (v if k != 'fix' else v[:10]) for k, v in f.items()})
    if mode in ("both", "reply"):
        rep = rec[i]["four"]["calls"][0]["reply"]
        print("  REPLY:", rep[:n].replace("\n", "\n    "))
