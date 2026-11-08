"""Pick the 100 gismo6 commits for the five-Laya panel test.

Drawn from the size-matched sample of the blinded Claude review
(../laya-near-chance/claude-review/key.json): one changed file per commit, labelled
by git history (REJECT = a later fix blamed its lines, APPROVE = never blamed in at
least 180 days). On top of that sample's rules:
  * gismo6 only, 100 distinct commits;
  * the patch has an added or removed line of a regular file: binary diffs, mode
    changes, pure renames, symbolic links and submodules show Laya no code;
  * every one of the five personas reads the whole change: the state is at most
    795 tokens, the room left beside TEST-FOCUSED, the longest persona;
  * the 50 smallest later-fixed changes whose commit is not taken yet, so that as
    much of the debate round as possible fits too (it adds about 290 tokens after
    the code);
  * each paired with the never-fixed change nearest in state tokens.
Writes selection.jsonl, with the single-Laya and Claude scores of the earlier runs."""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
from run_five import PLAN, file_patch, has_code  # noqa: E402
ROOM = 795          # Laya's window minus the TEST-FOCUSED question (measured on laya-serve)
PER_CLASS = 50

key = json.loads((EXP / "laya-near-chance" / "claude-review" / "key.json").read_text(encoding="utf-8"))
res = json.loads((EXP / "laya-near-chance" / "laya-probe" / "claude_review_result.json").read_text(encoding="utf-8"))
claude = {it["id"]: it["p_defect"] for b in res["reviews"] for it in b["items"]}
debate = {r["id"]: r for r in map(json.loads, (EXP / "laya-near-chance" / "laya-probe" / "debate.jsonl").open(encoding="utf-8"))}
tokens = {}
with (EXP / "laya-sweep" / "sessions.jsonl").open(encoding="utf-8") as f:
    for line in f:
        w = json.loads(line)["sweep"]
        if "gismo6" in w["repo"]:
            tokens[(w["commit"], w["file"])] = w["laya"]["usage"]["state_tokens"]

plan = {e["sha"]: e for e in map(json.loads, PLAN.open(encoding="utf-8"))}
no_code = [k for k in key if not has_code(file_patch(plan[k["commit"]], k["file"]))]
skip = {k["id"] for k in no_code}
pool = [dict(k, state_tokens=tokens[(k["commit"], k["file"])]) for k in key
        if "gismo6" in k["repo"] and tokens[(k["commit"], k["file"])] <= ROOM and k["id"] not in skip]
rejects = sorted((k for k in pool if k["label"] == "REJECT"), key=lambda k: (k["state_tokens"], k["id"]))
approves = [k for k in pool if k["label"] == "APPROVE"]

chosen, used = [], set()
for r in rejects:
    if len(chosen) == 2 * PER_CLASS:
        break
    if r["commit"] in used:
        continue
    free = [a for a in approves if a["commit"] not in used and a["commit"] != r["commit"]]
    a = min(free, key=lambda a: (abs(a["state_tokens"] - r["state_tokens"]),
                                 abs(math.log(a["patch_chars"]) - math.log(r["patch_chars"])), a["id"]))
    used |= {r["commit"], a["commit"]}
    chosen += [r, a]

with (HERE / "selection.jsonl").open("w", encoding="utf-8") as out:
    for k in chosen:
        d = debate.get(k["id"], {})
        out.write(json.dumps({
            "id": k["id"], "commit": k["commit"], "file": k["file"], "domain": k["domain"],
            "label": k["label"], "patch_chars": k["patch_chars"], "state_tokens": k["state_tokens"],
            "p_single_laya": k["p_laya"], "p_claude": claude[k["id"]],
            "p_single_debate": {arm: d.get(arm) for arm in ("alone", "real", "shuffled")},
        }) + "\n")


def auc(score, pos):
    P = [s for s, y in zip(score, pos) if y]
    N = [s for s, y in zip(score, pos) if not y]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


y = [k["label"] == "REJECT" for k in chosen]
print(f"matched sample: {len(no_code)} of {len(key)} patches show no code "
      f"({sum(k['label'] == 'REJECT' for k in no_code)} later fixed): {', '.join(k['id'] for k in no_code)}")
print(f"{len(chosen)} commits ({sum(y)} later fixed), {len({k['commit'] for k in chosen})} distinct; "
      f"pool {len(rejects)} REJECT / {len(approves)} APPROVE at <= {ROOM} tokens")
for name in ("state_tokens", "patch_chars"):
    v = sorted(k[name] for k in chosen)
    print(f"  {name:<13} AUC {auc([k[name] for k in chosen], y):.3f}  range {v[0]} to {v[-1]}, median {v[len(v) // 2]}")
print(f"  later-fixed state tokens up to {max(k['state_tokens'] for k in chosen if k['label'] == 'REJECT')}")
