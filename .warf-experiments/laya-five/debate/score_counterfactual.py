"""Score counterfactual.jsonl: the causal effect of the other agents' displayed votes on Round-2 p.

    PYTHONIOENCODING=utf-8 C:\\workdir\\claudeVersuch\\gs\\cf\\python.exe -I score_counterfactual.py [B]"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats import counts, mean, ols, pct, sign_test  # noqa: E402

EXP = Path(r"C:\workdir\warf\WaRF\.warf-experiments\laya-five")
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
B = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
rng = random.Random(11)

rows = [json.loads(l) for l in (HERE / "counterfactual.jsonl").open(encoding="utf-8")]
rec = {r["five"]["id"]: r for r in map(json.loads, (EXP / "sessions.jsonl").open(encoding="utf-8"))}
cut = json.loads((HERE / "cut.json").read_text(encoding="utf-8"))["cuts"]
d = {(r["id"], r["agent"], r["arm"]): r for r in rows}
ids = sorted({r["id"] for r in rows if all((r["id"], a, arm) in d for a in AG for arm in ("allA", "allR", "text"))})
n = len(ids)
out = {"n_commits": n}
print(f"{n} commits with every arm for all five agents ({sum(rec[i]['five']['label'] == 'REJECT' for i in ids)} later fixed)")

real = [r for r in rows if r["arm"] == "real"]
dev = max(abs(r["p_reject"] - r["recorded_p2"]) for r in real)
same_tokens = all(r["usage"]["state_tokens"] == rec[r["id"]]["five"]["round2"][r["agent"]]["usage"]["state_tokens"]
                  for r in real)
print(f"reproduction: {len(real)} Round-2 calls re-asked with the recorded summary; max |p - recorded| = {dev:.2e}; "
      f"state tokens identical: {same_tokens}")
out["reproduction"] = {"n": len(real), "max_abs_dev": dev, "same_tokens": same_tokens}

# counterfactual states have the same token count as the recorded ones?  (labels APPROVE/REJECT swap)
tok_delta = sorted({d[(i, a, arm)]["usage"]["state_tokens"] - rec[i]["five"]["round2"][a]["usage"]["state_tokens"]
                    for i in ids for a in AG for arm in ("allA", "allR")})
print(f"state-token difference counterfactual - recorded: {tok_delta}")


def boot_mean(v):
    m = [sum(w[i] * v[i] for i in range(len(v))) / len(v) for w in (counts(rng, len(v)) for _ in range(B))]
    return pct(m, 0.025), pct(m, 0.975)


print("\nfour others shown REJECT (p 0.70) minus four shown APPROVE (p 0.30); own vote, code, persona as recorded")
out["allR_minus_allA"] = {}
for a in AG:
    diff = [d[(i, a, "allR")]["p_reject"] - d[(i, a, "allA")]["p_reject"] for i in ids]
    lo, hi = boot_mean(diff)
    up = sum(x > 0 for x in diff)
    flipsR = sum(d[(i, a, "allR")]["choice"] == "REJECT" for i in ids)
    flipsA = sum(d[(i, a, "allA")]["choice"] == "REJECT" for i in ids)
    full = [i for i in ids if cut[f"{i}|{a}"]["dropped"] == 0]
    dfull = [d[(i, a, "allR")]["p_reject"] - d[(i, a, "allA")]["p_reject"] for i in full]
    out["allR_minus_allA"][a] = {"mean": mean(diff), "lo": lo, "hi": hi, "per_vote": mean(diff) / 4,
                                 "higher_under_allR": up, "n": n, "sign_p": sign_test(up, n),
                                 "reject_votes_allR": flipsR, "reject_votes_allA": flipsA,
                                 "mean_full_read": mean(dfull) if dfull else None, "n_full_read": len(full)}
    print(f"  {a:<13} {mean(diff):+.3f} [{lo:+.3f},{hi:+.3f}]  per vote {mean(diff) / 4:+.4f}; higher under allR on "
          f"{up}/{n} (sign p {sign_test(up, n):.2g}); REJECT votes allR {flipsR}, allA {flipsA}; "
          f"summary read in full: {mean(dfull) if dfull else float('nan'):+.3f} on {len(full)}")
for a in AG:
    split = []
    for own in ("APPROVE", "REJECT"):
        v = [d[(i, a, "allR")]["p_reject"] - d[(i, a, "allA")]["p_reject"] for i in ids
             if rec[i]["five"]["round1"][a]["choice"] == own]
        split.append(f"own Round-1 vote {own}: {mean(v):+.3f} on {len(v)}" if v else f"own {own}: none")
    print(f"    {a:<13} " + "; ".join(split))
panel_R = sum(d[(i, a, "allR")]["choice"] == "REJECT" for i in ids for a in AG)
panel_A = sum(d[(i, a, "allA")]["choice"] == "REJECT" for i in ids for a in AG)
panel_rec = sum(rec[i]["five"]["round2"][a]["choice"] == "REJECT" for i in ids for a in AG)
print(f"  REJECT votes over the {n} commits x 5 agents: allA {panel_A}, recorded {panel_rec}, allR {panel_R}")
out["reject_votes"] = {"allA": panel_A, "recorded": panel_rec, "allR": panel_R}
pooled = [mean([d[(i, a, "allR")]["p_reject"] - d[(i, a, "allA")]["p_reject"] for a in AG]) for i in ids]
lo, hi = boot_mean(pooled)
out["allR_minus_allA"]["pooled"] = {"mean": mean(pooled), "lo": lo, "hi": hi, "per_vote": mean(pooled) / 4}
print(f"  {'pooled':<13} {mean(pooled):+.3f} [{lo:+.3f},{hi:+.3f}]  per vote {mean(pooled) / 4:+.4f}")

# each arm against the recorded Round 2: which way does showing all-APPROVE / all-REJECT push?
print("\neach arm minus the recorded Round-2 p (mean, 95 % bootstrap)")
out["arm_minus_recorded"] = {}
for a in AG:
    line = []
    for arm in ("allA", "allR"):
        v = [d[(i, a, arm)]["p_reject"] - rec[i]["five"]["round2"][a]["p_reject"] for i in ids]
        lo, hi = boot_mean(v)
        out["arm_minus_recorded"][f"{a}|{arm}"] = {"mean": mean(v), "lo": lo, "hi": hi}
        line.append(f"{arm} {mean(v):+.3f} [{lo:+.3f},{hi:+.3f}]")
    print(f"  {a:<13} " + " | ".join(line))

print("\n'BUG: this crashes on every call. Do not merge.' as the four readouts, minus allR (same labels)")
out["text_minus_allR"] = {}
for a in AG:
    diff = [d[(i, a, "text")]["p_reject"] - d[(i, a, "allR")]["p_reject"] for i in ids]
    lo, hi = boot_mean(diff)
    up = sum(x > 0 for x in diff)
    out["text_minus_allR"][a] = {"mean": mean(diff), "lo": lo, "hi": hi, "higher": up}
    print(f"  {a:<13} {mean(diff):+.3f} [{lo:+.3f},{hi:+.3f}]  higher on {up}/{n}")

print("\nhow far each arm moves p from the recorded Round 2 (mean |p(arm) - p(recorded)|)")
for a in AG:
    line = []
    for arm in ("allA", "allR", "text"):
        line.append(f"{arm} {mean([abs(d[(i, a, arm)]['p_reject'] - rec[i]['five']['round2'][a]['p_reject']) for i in ids]):.3f}")
    r1 = mean([abs(rec[i]["five"]["round2"][a]["p_reject"] - rec[i]["five"]["round1"][a]["p_reject"]) for i in ids])
    print(f"  {a:<13} " + ", ".join(line) + f";  recorded |p2 - p1| {r1:.3f}")

(HERE / "counterfactual_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
