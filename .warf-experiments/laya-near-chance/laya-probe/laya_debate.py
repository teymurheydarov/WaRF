"""Would WaRF's debate round help Laya? On the 352 size-matched changes of the blinded review,
build the Round-2 prompt WaRF builds (_build_debate_prompt) and ask Laya three times:
  alone     - Laya is the only agent: it sees only its own Round-1 vote
  real      - a CLAUDE agent's verdict and reason for this change
  shuffled  - the CLAUDE verdicts and reasons dealt to the wrong changes
If Laya judged the arguments against the code, `real` would help and `shuffled` would not;
if it follows the words, both move it the same way."""
import json, math, random, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from rebuild_state import ask, frame, load_plan, rebuild  # noqa: E402

sys.path.insert(0, r"C:\workdir\warf\WaRF")
from warf.orchestrator import VoteRecord, _build_debate_prompt  # noqa: E402

key = json.loads((HERE.parent / "claude-review" / "key.json").read_text(encoding="utf-8"))
res = json.loads((HERE / "claude_review_result.json").read_text(encoding="utf-8"))
claude = {it["id"]: it for b in res["reviews"] for it in b["items"]}
ps = sorted(c["p_defect"] for c in claude.values())
cut = ps[int(0.75 * len(ps))]                 # CLAUDE votes REJECT on its top quarter
verdicts = [(("REJECT" if claude[k["id"]]["p_defect"] >= cut else "APPROVE"), claude[k["id"]]["reason"]) for k in key]
shuffled = verdicts[:]
random.Random(17).shuffle(shuffled)
plan = load_plan()
OUT = HERE / "debate.jsonl"


def vote(agent, label, reasoning):
    return VoteRecord(agent_name=agent, vote=1 if label == "APPROVE" else -1, reasoning=reasoning,
                      omega=0.5, provider="x", model="x")


with OUT.open("w", encoding="utf-8") as out:
    for n, (k, real, wrong) in enumerate(zip(key, verdicts, shuffled), 1):
        state = rebuild(plan[k["commit"]], k["file"], k["domain"])
        head, tail = frame(k["domain"])
        code = state[len(head):len(state) - len(tail)]
        own = "REJECT" if k["p_laya"] > 0.5 else "APPROVE"
        rec = {"id": k["id"], "label": k["label"], "p_round1": k["p_laya"], "claude_vote": real[0],
               "shuffled_vote": wrong[0]}
        for arm, others in (("alone", []), ("real", [real]), ("shuffled", [wrong])):
            votes = [vote("LAYA", own, "")] + [vote("CLAUDE", lab, why) for lab, why in others]
            p, u = ask(_build_debate_prompt(code, k["domain"], votes, agent_name="LAYA"))
            rec[arm] = p
            rec[arm + "_dropped"] = u.get("state_tokens_dropped")
        out.write(json.dumps(rec) + "\n")
        out.flush()
        if n % 50 == 0:
            print(f"  {n}/{len(key)}", flush=True)


def auc(score, pos):
    P = [s for s, y in zip(score, pos) if y]
    N = [s for s, y in zip(score, pos) if not y]
    a = sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return a, math.sqrt((a * (1 - a) + (len(P) - 1) * (q1 - a * a) + (len(N) - 1) * (q2 - a * a)) / (len(P) * len(N)))


R = [json.loads(line) for line in OUT.open(encoding="utf-8")]
y = [r["label"] == "REJECT" for r in R]
print(f"\n  {len(R)} changes, {sum(y)} later fixed; CLAUDE votes REJECT at p(defect) >= {cut:.2f}")
print(f"  {'':<34} {'AUC vs history':>15} {'p if CLAUDE says REJECT':>24} {'... APPROVE':>12} {'argument cut':>13}")
a, se = auc([r["p_round1"] for r in R], y)
print(f"  {'Round 1 (no debate)':<34} {a:>9.3f} ±{se:.3f}")
for arm, attached in (("alone", "claude_vote"), ("real", "claude_vote"), ("shuffled", "shuffled_vote")):
    a, se = auc([r[arm] for r in R], y)
    rej = [r[arm] for r in R if r[attached] == "REJECT"]
    app = [r[arm] for r in R if r[attached] == "APPROVE"]
    dropped = sum(1 for r in R if r[arm + "_dropped"])
    print(f"  {'debate, ' + arm:<34} {a:>9.3f} ±{se:.3f} {sum(rej) / len(rej):>24.3f} {sum(app) / len(app):>12.3f} "
          f"{dropped:>9}/{len(R)}")
a, se = auc([1.0 if v == "REJECT" else 0.0 for v in (r["claude_vote"] for r in R)], y)
print(f"  {'CLAUDE vote itself':<34} {a:>9.3f} ±{se:.3f}")
for arm in ("real", "shuffled"):
    att = "claude_vote" if arm == "real" else "shuffled_vote"
    a, _ = auc([r[arm] for r in R], [r[att] == "REJECT" for r in R])
    print(f"  how well Laya's p tracks the attached vote ({arm}): AUC {a:.3f}")
print(f"  Laya votes REJECT: round 1 {sum(r['p_round1'] > 0.5 for r in R)}, alone {sum(r['alone'] > 0.5 for r in R)}, "
      f"real {sum(r['real'] > 0.5 for r in R)}, shuffled {sum(r['shuffled'] > 0.5 for r in R)}")
