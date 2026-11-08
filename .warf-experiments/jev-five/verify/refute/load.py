"""Load the 100 commits with every score and feature, in selection order (pairs 2k, 2k+1)."""
import json
import math
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
EXP = Path(r"C:\workdir\warf\WaRF\.warf-experiments")
JEV = EXP / "jev-five"
LAYA = EXP / "laya-five"
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def jl(path):
    return [json.loads(line) for line in Path(path).open(encoding="utf-8")]


sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
pair = [i // 2 for i in range(len(sel))]
assert all(y[2 * k] and not y[2 * k + 1] for k in range(50))

one = {r["jev"]["id"]: r for r in jl(JEV / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(JEV / "sessions_five.jsonl")}
rep = {r["jev"]["id"]: r for r in jl(JEV / "repeat_one.jsonl")}
runA = {r["jev"]["id"]: r for r in jl(OUT / "rerun_A.jsonl")}
runB = {r["jev"]["id"]: r for r in jl(OUT / "rerun_B.jsonl")}
lfive = {r["five"]["id"]: r for r in jl(LAYA / "sessions.jsonl")}
feat = {r["id"]: r for r in jl(OUT / "features.jsonl")}
states = {r["id"]: r for r in jl(OUT / "states.jsonl")}


def p1(rs, i):
    return rs[i]["jev"]["round1"]["JEV"]["p_reject"]


def final(block, a):
    b = block["round2"].get(a) or block["round1"][a]
    return b["p_reject"]


S = {}
S["jev0"] = [p1(one, i) for i in ids]
S["jevA"] = [p1(runA, i) for i in ids]
S["jevB"] = [p1(runB, i) for i in ids]
S["jev3"] = [(a + b + c) / 3 for a, b, c in zip(S["jev0"], S["jevA"], S["jevB"])]
for a in AGENTS:
    S[f"five_{a}"] = [five[i]["jev"]["round1"][a]["p_reject"] for i in ids]
S["five_r1"] = [sum(five[i]["jev"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids]
S["five_final"] = [sum(final(five[i]["jev"], a) for a in AGENTS) / 5 for i in ids]
S["laya1"] = [s["p_single_laya"] for s in sel]
S["laya5_r1"] = [sum(lfive[i]["five"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids]
S["laya5_final"] = [sum(final(lfive[i]["five"], a) for a in AGENTS) / 5 for i in ids]
S["claude"] = [s["p_claude"] for s in sel]
S["patch_chars"] = [s["patch_chars"] for s in sel]
S["state_tokens"] = [s["state_tokens"] for s in sel]

F = [feat[i] for i in ids]


def year(d):
    t = datetime.fromisoformat(d.replace("Z", "+00:00"))
    return t.year + (t.timetuple().tm_yday - 1) / 366


DATE = [year(f["commit_date"]) for f in F]
