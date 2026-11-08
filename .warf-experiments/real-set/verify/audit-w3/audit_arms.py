"""Audit the claude-commit and claude-commit-strict records and commit_inputs.jsonl (read-only git)."""
import hashlib, json, random, subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
HERE = Path(__file__).resolve().parent; SET = HERE.parents[1]
GD = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"
def git(*a): return subprocess.run(["git", "--git-dir", GD, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}; ids = [it["id"] for it in items]
ci = {}
for l in (SET / "commit_inputs.jsonl").open(encoding="utf-8"):
    r = json.loads(l); assert r["id"] not in ci; ci[r["id"]] = r
print("commit_inputs:", len(ci), "ids equal items:", set(ci) == set(ids))
errs = [json.loads(l) for l in (SET / "errors.jsonl").open(encoding="utf-8")]
print("errors.jsonl:", len(errs), Counter(e["arm"] for e in errs))
ph = lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]
def load(a):
    out = {}
    for p in sorted(SET.glob(f"{a}.w*.jsonl")):
        for n, l in enumerate(p.open(encoding="utf-8")):
            r = json.loads(l); out.setdefault(r["planted"]["id"], []).append((p.name, n, r))
    return out
base = {a: load(a) for a in ("claude", "claude-strict")}
for arm, ref in (("claude-commit", "claude"), ("claude-commit-strict", "claude-strict")):
    R = load(arm)
    multi = [i for i, v in R.items() if len(v) != 1]
    print(f"\n[{arm}] ids {len(R)}, missing {len(set(ids) - set(R))}, extra {len(set(R) - set(ids))}, >1 record {len(multi)}")
    recs = {i: v[0][2] for i, v in R.items()}
    bad = Counter()
    for i, r in recs.items():
        pl, c, v = r["planted"], r["planted"]["call"], r["votes"]
        if not (pl["model"] == c["model"] == "claude-opus-5-5" and pl["provider"] == "claude_cli"): bad["planted model"] += 1
        if len(v) != 1 or v[0]["model"] != "claude-opus-5-5" or v[0]["provider"] != "claude_cli": bad["vote model"] += 1
        if v[0]["agent"] != "CLAUDE-COMMIT" or c["agent"] != "CLAUDE-COMMIT": bad["agent"] += 1
        if not c["exact"]: bad["not exact first word"] += 1
        if pl["kind"] != by_id[i]["kind"]: bad["kind"] += 1
        if r["artifact"] != f"{by_id[i]['commit']}:{by_id[i]['file']}": bad["artifact"] += 1
        if r["domain"] != by_id[i]["domain"]: bad["domain"] += 1
        if v[0]["vote"] not in (1, -1) or r["decision"] not in ("APPROVE", "REJECT"): bad["vote"] += 1
        ov_c = c["sent_chars"] - len(ci[i]["code"]); rb = base[ref][i][0][2]
        ov_b = rb["planted"]["call"]["sent_chars"] - len(by_id[i]["code"])
        bad[f"overhead commit-minus-single {ov_c - ov_b}"] += 0
        r.setdefault("_ov", (ov_c, ov_b))
        if v[0]["persona"] != rb["votes"][0]["persona"]: bad["persona differs from " + ref] += 1
    ovs = Counter(r["_ov"][0] - r["_ov"][1] for r in recs.values())
    print("  problems:", {k: n for k, n in bad.items() if n} or "none")
    print("  persona hashes:", Counter(r["votes"][0]["persona"] for r in recs.values()), "ref", Counter(base[ref][i][0][2]["votes"][0]["persona"] for i in ids))
    print("  (sent_chars - len(input)) commit minus single-file arm:", ovs)
    print("  answers: exact", sum(r["planted"]["call"]["exact"] for r in recs.values()), "REJECT", sum(r["decision"] == "REJECT" for r in recs.values()))
    E = [e for e in errs if e["arm"] == arm]
    print(f"  errors {len(E)}:", Counter(e["error"][:60] for e in E))
    for e in E:
        later = [x for x in R.get(e["id"], []) if datetime.fromisoformat(x[2]["created_at"]) > datetime.fromisoformat(e["at"])]
        if len(R.get(e["id"], [])) != 1 or len(later) != 1:
            print("   ! errored item", e["id"], "records", len(R.get(e["id"], [])), "later", len(later))
    print("  every errored item has exactly one record, written after the error:",
          all(len(R.get(e["id"], [])) == 1 and datetime.fromisoformat(R[e["id"]][0][2]["created_at"]) > datetime.fromisoformat(e["at"]) for e in E))
    ts = sorted(r["created_at"] for r in recs.values()); print("  created_at range", ts[0], ts[-1])
    early = [r["planted"]["id"] for r in recs.values() if r["created_at"] < "2026-11-05T20:40"]
    print("  records before the main run (2026-11-05T20:40):", early)

# commit_inputs structure
nok = Counter()
for i in ids:
    it, c = by_id[i], ci[i]["code"]
    if it["code"] not in c: nok["item code not verbatim"] += 1
    head = f"=== The reviewed file ({it['file']}) ===\n{it['code']}\n\n=== The commit's other files ({ci[i]['other_files']}) ===\n"
    if head not in c: nok["layout"] += 1
    if not c.startswith("Commit message:\n"): nok["no message"] += 1
print("\ncommit_inputs structure problems:", dict(nok) or "none",
      "; cut:", sum("[... the remaining diff of the other files is cut ...]" in ci[i]["code"] for i in ids),
      "; no other files:", sum(ci[i]["other_files"] == 0 for i in ids))
merges = [i for i in ids if len(git("show", "-s", "--format=%P", by_id[i]["commit"]).split()) > 1]
print("merge commits among items:", merges)
# spot-check 10 against git
pick = random.Random(11).sample(ids, 10)
for i in pick:
    it = by_id[i]; c = ci[i]["code"]; sha = it["commit"]
    msg = git("show", "-s", "--format=%s%n%n%b", sha).strip()
    files = [f for f in git("show", "--format=", "--name-only", sha).split() if f != it["file"]]
    other = git("show", "-U10", "--no-color", "--format=", sha, "--", ".", f":(exclude){it['file']}") if files else ""
    full = other
    if len(other) > 60000: other = other[:60000] + "\n[... the remaining diff of the other files is cut ...]"
    want = (f"Commit message:\n{msg}\n\n=== The reviewed file ({it['file']}) ===\n{it['code']}\n\n"
            f"=== The commit's other files ({len(files)}) ===\n{other or '(none)'}")
    # files named in the other-files part, each must be touched by this commit
    named = {l[len('diff --git a/'):].split(' b/')[0] for l in (other.splitlines()) if l.startswith("diff --git a/")}
    touched = set(git("show", "--format=", "--name-only", sha).split())
    # the reviewed file's own diff at the commit (U30 is used for the item; check its '+' lines appear in git's diff)
    own = git("show", "-U0", "--no-color", "--format=", sha, "--", it["file"])
    plus = [l[1:] for l in own.splitlines() if l.startswith("+") and not l.startswith("+++")]
    later = git("log", "--format=%h", f"{sha}..origin/dev", "--", it["file"]).split()[:1]
    print(f"  {i}: equal to git {c == want}; other files {len(files)} named {len(named)} all touched {named <= touched};"
          f" item + lines in git diff {sum(('+' + p) in it['code'] for p in plus)}/{len(plus)}; date {git('show','-s','--format=%cI',sha).strip()[:10]} item {it['date']}")
