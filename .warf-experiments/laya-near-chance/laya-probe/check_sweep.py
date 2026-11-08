"""Integrity check of the finished Laya sweep: plan vs sessions vs commits."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

home = Path(sys.argv[1])
def rows(name):
    out = []
    with (home / name).open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  {name}: line {i + 1} does not parse")
    return out

plan = rows("plan.jsonl")
sess = [s for s in rows("sessions.jsonl") if s.get("profile") == "laya_sweep" and "sweep" in s]
commits = rows("commits.jsonl")
runs = rows("runs.jsonl")

planned = {(e["repo"], e["sha"]): e for e in plan}
print(f"plan: {len(plan)} commits, {sum(e['files'] for e in plan)} file reviews, "
      f"phases {dict(Counter(e['phase'] for e in plan))}")
print(f"sessions: {len(sess)}")

keys = Counter((s["sweep"]["repo"], s["sweep"]["commit"], s["sweep"]["file"]) for s in sess)
dups = {k: n for k, n in keys.items() if n > 1}
print(f"unique (repo, commit, file): {len(keys)}   duplicated keys: {len(dups)}")
idx = Counter((s["sweep"]["repo"], s["sweep"]["commit"], s["sweep"]["file_index"]) for s in sess)
print(f"unique (repo, commit, file_index): {len(idx)}")

per_commit = Counter((s["sweep"]["repo"], s["sweep"]["commit"]) for s in sess)
missing = [(k, e["files"], per_commit.get(k, 0)) for k, e in planned.items() if per_commit.get(k, 0) != e["files"]]
print(f"commits whose review count differs from the plan: {len(missing)}")
for k, want, got in missing[:10]:
    print(f"   {k[0]} {k[1][:10]} planned {want} reviewed {got}")
extra = [k for k in per_commit if k not in planned]
print(f"reviewed commits not in the plan: {len(extra)}")

last = {}
for c in commits:
    last[(c["repo"], c["sha"])] = c
print(f"commits.jsonl: {len(commits)} records, {len(last)} commits; final status {dict(Counter(c['status'] for c in last.values()))}")
bad = [c for c in last.values() if c["status"] != "done" or c["errors"] or c["error"] or c["reviewed"] != c["supported"]]
print(f"   final records with errors or reviewed != supported: {len(bad)}")
not_logged = [k for k in planned if k not in last]
print(f"   planned commits without a commits.jsonl record: {len(not_logged)}")

sw = [s["sweep"] for s in sess]
print(f"phase of reviews: {dict(Counter(x['phase'] for x in sw))}")
print(f"enrich fell back to the plain patch: {sum(1 for x in sw if x.get('enrich_error'))}")
print(f"state cut to laya-serve's char limit: {sum(1 for x in sw if x.get('cut'))}")
dec = Counter(s["decision"] for s in sess)
print(f"decisions: {dict(dec)}   sprt fired: {sum(1 for s in sess if s.get('sprt_fired'))}")
dom = Counter(s["domain"] for s in sess)
print(f"domains: {dict(dom)}")
nolaya = [s for s in sess if not isinstance(s["sweep"].get("laya"), dict)]
print(f"sessions without a laya block: {len(nolaya)}")
ex = sw[0]["laya"]
print(f"laya block keys: {sorted(ex)}")
usage_keys = sorted(ex.get("usage", {}))
print(f"laya usage keys: {usage_keys}")
trunc = sum(1 for x in sw if x["laya"].get("usage", {}).get("truncated"))
print(f"states Laya truncated: {trunc} of {len(sw)} ({trunc / len(sw):.1%})")
secs = [x["seconds"] for x in sw]
print(f"seconds per review: mean {sum(secs) / len(secs):.2f}  by phase " + ", ".join(
    f"{p} {sum(x['seconds'] for x in sw if x['phase'] == p) / max(1, sum(1 for x in sw if x['phase'] == p)):.2f}" for p in "ABC"))
print(f"runs.jsonl: {len(runs)} runs")
for r in runs:
    print("   ", {k: r[k] for k in list(r)[:8]})
