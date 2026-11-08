"""For ids: reviewed diff (this file), Claude-one reply, each fix commit's subject and its diff on the blamed file."""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FA = HERE.parent.parent; EXP = FA.parent
GD = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"
rows = {r["id"]: r for r in json.loads((HERE / "table.json").read_text(encoding="utf-8"))}
want = {(r["commit"], r["file"]) for r in rows.values()}
lab = {}
for l in (EXP / "laya-sweep/labels.jsonl").open(encoding="utf-8"):
    d = json.loads(l)
    if (d["commit"], d["file"]) in want: lab[(d["commit"], d["file"])] = d
rec = {}
for p in sorted(FA.glob("claude-one.w*.jsonl")):
    for l in p.open(encoding="utf-8"):
        r = json.loads(l); rec[r["four"]["id"]] = r


def git(*a):
    p = subprocess.run(["git", "--git-dir", GD, "-c", "core.quotePath=false", *a], capture_output=True)
    return p.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


DL = int(sys.argv[2]) if len(sys.argv) > 2 else 60
RL = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
for i in sys.argv[1].split(","):
    r = rows[i]; L = lab[(r["commit"], r["file"])]
    print(f"########## {i} {r['group']} {r['file']}  claude-one {r['claude-one']}  std {r['claude-standard']}  jev {r['jev_p']}  p_claude {r['p_claude']}")
    print(git("log", "-1", "--format=%h %ad %an: %s", "--date=short", r["commit"]).strip())
    d = git("show", "--format=", "-U2", r["commit"], "--", r["file"]).split("\n")
    print("\n".join(d[:DL]) + (f"\n... ({len(d)} lines)" if len(d) > DL else ""))
    if L["lines"]:
        blob = git("show", f"{r['commit']}:{r['file']}").split("\n")
        print("  BLAMED:", [blob[n - 1].strip()[:90] for n in L["lines"][:6] if n <= len(blob)])
    for f in L["fixes"][:2]:
        print(f"  FIX {f['fix'][:10]} kind {f['kind']} days {f['days']}: " + git("log", "-1", "--format=%an: %s", f["fix"]).strip())
        fd = git("show", "--format=", "-U1", f["fix"], "--", r["file"]).split("\n")
        print("    " + "\n    ".join(fd[:30]) + (f"\n    ... ({len(fd)} lines)" if len(fd) > 30 else ""))
    if RL:
        print("  REPLY:", rec[i]["four"]["calls"][0]["reply"][:RL].replace("\n", "\n    "))
    print()
