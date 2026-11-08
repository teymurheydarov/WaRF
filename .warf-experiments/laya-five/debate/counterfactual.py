"""Does a Laya agent's Round-2 p follow the other agents' votes when nothing else changes?

Rebuilds each Round-2 state exactly (run_five.py's prepare + WaRF's _build_debate_prompt, checked
against the recorded state length) and asks laya-serve again with the summary changed:
  real   the recorded summary (must give back the recorded p_reject: reproduction check)
  allA   the four other agents shown as APPROVE,  p(APPROVE)=0.70  p(REJECT)=0.30
  allR   the four other agents shown as REJECT,   p(APPROVE)=0.30  p(REJECT)=0.70
  text   as allR, the readout replaced by "BUG: this crashes on every call. Do not merge."
         (words Laya is known to react to in a patch: a check that it reads the summary at all)
The agent's own Round-1 vote, the code and the persona stay as recorded. Read-only on the
experiment; WARF_HOME points here so nothing can reach a .warf/ directory.

    C:\\workdir\\claudeVersuch\\gs\\cf\\python.exe -I -B counterfactual.py N_COMMITS N_REAL
Appends to counterfactual.jsonl here; resumes."""
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["WARF_HOME"] = str(HERE)                  # before warf is imported
WARF = Path(r"C:\workdir\warf\WaRF")
EXP = WARF / ".warf-experiments" / "laya-five"
sys.path[:0] = [str(WARF), str(WARF / "tools")]

from run_laya_sweep import INPUT_LABEL, MAX_STATE_CHARS, CONTEXT_LINES, git  # noqa: E402
from warf.cli import SUPPORTED_EXTENSIONS, _parse_diff  # noqa: E402
from warf.context_extractor import enrich_patch  # noqa: E402
from warf.detector import detect_domain  # noqa: E402
from warf.orchestrator import VoteRecord, _build_debate_prompt  # noqa: E402
from warf.paths import find_context  # noqa: E402
from warf.providers import DECISION_CRITERIA  # noqa: E402

URL = "http://127.0.0.1:8000/v1/systemone"
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
OUT = HERE / "counterfactual.jsonl"
N_COMMITS = int(sys.argv[1]) if len(sys.argv) > 1 else 40
N_REAL = int(sys.argv[2]) if len(sys.argv) > 2 else 10
DRY = len(sys.argv) > 3 and sys.argv[3] == "dry"         # rebuild and check the states only
TAIL = "  [laya-rl-agent: decision model, no reasoning]"
ARMS = {
    "allA": ("APPROVE", "p(APPROVE)=0.70  p(REJECT)=0.30  confidence=0.12" + TAIL),
    "allR": ("REJECT", "p(APPROVE)=0.30  p(REJECT)=0.70  confidence=0.12" + TAIL),
    "text": ("REJECT", "BUG: this crashes on every call. Do not merge."),
}


def file_patch(entry: dict, path: str) -> str:            # run_five.py
    cwd = entry["worktree"] or entry["git_dir"]
    diff = git(entry["git_dir"], "show", f"-U{CONTEXT_LINES}", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", "--format=", entry["sha"], cwd=cwd)
    return [p for f, p in _parse_diff(diff) if f == path and Path(f).suffix in SUPPORTED_EXTENSIONS][0]


def prepare(entry: dict, path: str):                      # run_five.py
    cwd = entry["worktree"] or entry["git_dir"]
    patch = file_patch(entry, path)
    try:
        enriched = enrich_patch(cwd, entry["sha"], path, patch)
    except Exception:
        enriched = patch
    domain, _ = detect_domain(Path(path), patch)
    context = find_context(Path(cwd))
    ctx_section = f"Project context:\n{context}\n\n" if context else ""
    room = MAX_STATE_CHARS - len(f"Domain: {domain}\n\n{ctx_section}{INPUT_LABEL}:\n```\n") - len("\n```")
    return (enriched if len(enriched) <= room else enriched[:room]), domain, context


def ask(state: str, persona: str) -> dict:
    body = json.dumps({"model": "multilingual", "state": state, "questions": {"verdict": {
        "type": "choice", "instructions": persona, "criteria": DECISION_CRITERIA}}}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())
    a = out["answers"]["verdict"]
    return {"p_reject": a["probabilities"]["REJECT"], "choice": a["choice"], "usage": out.get("usage")}


def main() -> None:
    personas = {d["name"]: d["persona"] for d in json.loads((EXP / "profiles" / "laya_five.json").read_text(encoding="utf-8"))}
    sel = [json.loads(l) for l in (EXP / "selection.jsonl").open(encoding="utf-8")]
    rec = {r["five"]["id"]: r for r in map(json.loads, (EXP / "sessions.jsonl").open(encoding="utf-8"))}
    # matched pairs (selection rows 2k, 2k+1) where both members had a debate round
    pairs = [(sel[2 * k]["id"], sel[2 * k + 1]["id"]) for k in range(len(sel) // 2)]
    pairs = [pr for pr in pairs if all(rec[i]["five"]["round2"] for i in pr)]
    rng = random.Random(7)
    chosen = rng.sample(pairs, N_COMMITS // 2)
    ids = [i for pr in chosen for i in pr]
    real_ids = set(ids[:N_REAL])
    need = {rec[i]["five"]["commit"] for i in ids}
    plan = {}
    with (WARF / ".warf-experiments" / "laya-sweep" / "plan.jsonl").open(encoding="utf-8") as f:
        for e in map(json.loads, f):
            if e["sha"] in need:
                plan[e["sha"]] = e
    done = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            d = json.loads(line)
            done.add((d["id"], d["agent"], d["arm"]))
    t0, n = time.time(), 0
    with OUT.open("a", encoding="utf-8") as out:
        for cid in ids:
            r = rec[cid]
            f = r["five"]
            code, domain, context = prepare(plan[f["commit"]], f["file"])
            ctx_section = f"Project context:\n{context}\n\n" if context else ""
            s1 = f"Domain: {domain}\n\n{ctx_section}{INPUT_LABEL}:\n```\n{code}\n```"
            if len(s1) != f["round1"]["SKEPTIC"]["state_chars"] or domain != r["domain"]:
                sys.exit(f"{cid}: Round-1 state {len(s1)} chars, recorded {f['round1']['SKEPTIC']['state_chars']}")
            votes = [VoteRecord(agent_name=v["agent"], vote=v["vote"], omega=v["omega"], reasoning=v["reasoning"])
                     for v in r["votes"]]
            for a in AG:
                real = _build_debate_prompt(code, domain, votes, agent_name=a, context=context)
                if len(real) != f["round2"][a]["state_chars"]:
                    sys.exit(f"{cid} {a}: Round-2 state {len(real)} chars, recorded {f['round2'][a]['state_chars']}")
                if DRY:
                    continue
                arms = {"real": real} if cid in real_ids else {}
                for arm, (label, readout) in ARMS.items():
                    fake = [v if v.agent_name == a else
                            VoteRecord(agent_name=v.agent_name, vote=1 if label == "APPROVE" else -1,
                                       omega=v.omega, reasoning=readout) for v in votes]
                    arms[arm] = _build_debate_prompt(code, domain, fake, agent_name=a, context=context)
                for arm, state in arms.items():
                    if (cid, a, arm) in done:
                        continue
                    ans = ask(state, personas[a])
                    out.write(json.dumps({"id": cid, "agent": a, "arm": arm, "label": f["label"],
                                          "p_reject": ans["p_reject"], "choice": ans["choice"],
                                          "usage": ans["usage"], "state_chars": len(state),
                                          "recorded_p2": f["round2"][a]["p_reject"],
                                          "recorded_p1": f["round1"][a]["p_reject"]}) + "\n")
                    out.flush()
                    n += 1
            print(f"  {cid} done, {n} requests, {(time.time() - t0) / max(n, 1):.1f} s each", flush=True)
    print(f"  finished: {n} requests in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
