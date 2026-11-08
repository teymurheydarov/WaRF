"""What did each Haiku agent do besides answering? The Claude CLI keeps a transcript of every call
WaRF makes (~/.claude/projects/<home folder>/<session>.jsonl, since WaRF runs it in the home
folder). Each transcript is matched to its call in the run records by the message sent and the
persona, and its tool calls are listed with their permission decisions and a snippet of each result.
A call whose tools touched a source repository could have seen code from after the reviewed commit.

    python .warf-experiments/standard-five/audit_transcripts.py   # -> transcripts.jsonl, audit.log
Writes only short excerpts: the transcripts also hold the CLI's environment and account context."""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from warf.state import _DEFAULT_AGENTS  # noqa: E402

FOLDER = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path.home()))
PERSONA = {text: name for name, text in _DEFAULT_AGENTS}
REPO = re.compile(r"source[/\\]+repos|gismo|[/\\]\.git[/\\]|\.warf|workdir", re.I)   # in what a tool returned


def transcript(path: Path) -> dict | None:
    out = {"session": path.stem, "tools": []}
    pending = {}
    for line in path.open(encoding="utf-8"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get("type")
        if t == "queue-operation" and e.get("operation") == "enqueue" and "sent_sha" not in out:
            sent = (e.get("content") or "").replace("\r\n", "\n")
            out.update(start=e["timestamp"], sent_sha=hashlib.sha256(sent.encode("utf-8")).hexdigest()[:16])
        elif t == "attachment" and (e.get("attachment") or {}).get("type") == "prompt_snapshot" and "agent" not in out:
            out["agent"] = PERSONA.get((e["attachment"].get("systemPrompt") or [""])[0], "?")
        elif t == "attachment" and (e.get("attachment") or {}).get("type") == "model" and "model" not in out:
            out["model"] = (e["attachment"].get("identity") or {}).get("modelId")
        elif t == "assistant":
            for b in e["message"].get("content") or []:
                if b.get("type") == "tool_use":
                    item = {"name": b.get("name"), "input": json.dumps(b.get("input"), ensure_ascii=False)[:400]}
                    pending[b.get("id")] = item
                    out["tools"].append(item)
                elif b.get("type") == "text" and b.get("text", "").strip():
                    out["last_text"] = b["text"].strip().split("\n", 1)[0][:120]
        elif t == "user" and isinstance(e["message"].get("content"), list):
            for b in e["message"]["content"]:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    c = b.get("content")
                    text = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                    pending[b["tool_use_id"]].update(result=text[:300], is_error=bool(b.get("is_error")),
                                                     permission=(e.get("permissionDecision") or {}).get("decision"),
                                                     repo=bool(REPO.search(text)))
    if "sent_sha" not in out:
        return None
    for item in out["tools"]:
        item.setdefault("repo", False)
    return out


def seconds(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


calls = []                     # every recorded call, with its estimated start time
for path in sorted(HERE.glob("*.w*.jsonl")):
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        s = r["std"]
        t = seconds(r["created_at"]) - s["seconds"]
        for c in s["calls"]:
            calls.append({"arm": s["arm"], "id": s["id"], "label": s["label"], "sample": s["sample"],
                          "round": c["round"], "agent": c["agent"], "sent_sha": c["sent_sha"], "vote": c.get("vote"),
                          "error": c.get("error"), "start": t})
            t += c["seconds"]
T = [x for x in map(transcript, FOLDER.glob("*.jsonl")) if x]
T.sort(key=lambda x: x["start"])
by_key = {}
for c in calls:
    by_key.setdefault((c["sent_sha"], c["agent"]), []).append(c)
matched, unmatched = 0, []
for x in T:
    cands = by_key.get((x["sent_sha"], x.get("agent")))
    if cands:                   # the same message and persona: take the call that started closest in time
        best = min(cands, key=lambda c: abs(c["start"] - seconds(x["start"])))
        if abs(best["start"] - seconds(x["start"])) < 120:
            cands.remove(best)
            x["call"] = {k: v for k, v in best.items() if k != "start"}
            matched += 1
            continue
    unmatched.append(x)
with (HERE / "transcripts.jsonl").open("w", encoding="utf-8") as f:
    for x in T:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")

used = [x for x in T if x["tools"] and "call" in x]
print(f"  {len(T)} transcripts in {FOLDER}; {matched} matched to the {len(calls)} recorded calls; "
      f"{len(unmatched)} unmatched (smoke tests and CLI checks); {sum(len(v) for v in by_key.values())} calls without a transcript")
print(f"  models: {sorted({x.get('model') for x in T if 'call' in x})}")
names = {}
for x in used:
    for t in x["tools"]:
        names[t["name"]] = names.get(t["name"], 0) + 1
print(f"  calls that used tools: {len(used)} of {matched} ({100 * len(used) / max(1, matched):.1f} %); tool calls by name {names}")
perm = {}
for x in used:
    for t in x["tools"]:
        perm[t.get("permission")] = perm.get(t.get("permission"), 0) + 1
print(f"  permission decisions: {perm}")
touched = [x for x in used if any(t["repo"] for t in x["tools"])]
print(f"  calls where a tool returned something from a repository (source/repos, gismo, .git, .warf, workdir): {len(touched)}")
print(f"  of the calls that used tools, {sum(bool(x['call']['error']) for x in used)} failed (WaRF drops the vote of an agent that times out)")
for x in used:
    c = x["call"]
    flag = "REPO " if x in touched else ""
    print(f"    {flag}{c['arm']} {c['id']} ({c['label']}) sample {c['sample']} {c['round']} {c['agent']} vote {c['vote']}"
          + (f", {c['error'][:40]}" if c["error"] else "") + ":")
    for t in x["tools"]:
        print(f"      {t['name']} {t['input'][:160]} -> {t.get('permission')}, {(t.get('result') or '')[:100]!r}")
