"""Where Laya's window cut each Round-2 state. Read-only on the experiment.

Run with the laya-venv interpreter (same base python, has `tokenizers`):
    C:\\workdir\\warf\\laya-venv\\Scripts\\python.exe -I tokens.py

The Round-2 state is WaRF's _build_debate_prompt: the Round-1 frame with the label
"Code under review" instead of "Patch under review (unified diff)", then after the closing
fence the Round-1 summary (own vote, the four other agents' lines, the "Your Turn"
instructions). Laya keeps the first `room` tokens of the state, so the
state_tokens_dropped tokens are the summary's last ones (Round 1 was never cut here).

The summary text is rebuilt from the session record's Round-1 votes (label + reasoning,
which is the probability readout) with the template copied from warf/orchestrator.py;
the rebuild is checked by requiring label delta + summary tokens == S_R2 - S_R1 for
every call. Writes cut.json: per (id, agent) which parts of the summary Laya saw."""
import json
from pathlib import Path

from tokenizers import Tokenizer

EXP = Path(r"C:\workdir\warf\WaRF\.warf-experiments\laya-five")
TOK = Path(r"C:\Users\Teymur Heydarov\.cache\huggingface\hub\models--convaiinnovations--laya\snapshots"
           r"\7b928d828b7b0e022f929d9bd2e44165aa270148\multilingual\tokenizer\tokenizer.json")
OUT = Path(__file__).resolve().parent / "cut.json"
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
tok = Tokenizer.from_file(str(TOK))


def n_tokens(text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False).ids)


def tail_parts(record: dict, agent: str) -> list[tuple[str, str]]:
    """The text after the closing fence of the Round-2 state, as (part name, text) pieces,
    copied from _build_debate_prompt (warf/orchestrator.py)."""
    votes = record["votes"]
    own = next(v for v in votes if v["agent"] == agent)
    parts = [("header", "\n\n=== Round 1 Summary ===\n"),
             ("own", f"Your Round 1 vote: {own['label']}\n\n"),
             ("others_head", "Other agents voted:\n")]
    others = [v for v in votes if v["agent"] != agent]
    for i, v in enumerate(others):
        excerpt = v["reasoning"][:300].replace("\n", " ") if v["reasoning"] else "(no reasoning)"
        # one line of _build_debate_prompt, split where the vote label ends and the readout starts
        parts.append((f"label:{v['agent']}", f"- {v['agent']}: {v['label']}\n"))
        parts.append((f"other:{v['agent']}", f"  Reasoning: {excerpt}" + ("\n" if i < len(others) - 1 else "")))
    parts.append(("turn", "\n\n=== Your Turn ===\n"
                  "Critically evaluate the other agents' reasoning:\n"
                  "- If their reasoning reveals a genuine technical error in your own analysis, "
                  "revise your vote and explain what convinced you.\n"
                  "- If their reasoning contains misconceptions or factual errors, "
                  "maintain your position and explain specifically what they got wrong.\n"
                  "- Do NOT change your vote simply because others disagree with you."))
    return parts


def token_ends(prefix: str, parts: list[tuple[str, str]]) -> tuple[int, list[tuple[str, int]]]:
    """Tokenize prefix + all parts once; for each part, the index (counted from the start of the
    tail) of the first tail token after that part. A token counts toward a part when it ends
    inside it, so a token straddling two parts belongs to the later one (seeing it needs both)."""
    text = prefix + "".join(t for _, t in parts)
    enc = tok.encode(text, add_special_tokens=False)
    base = n_tokens(prefix)
    # tokens of the prefix must be unchanged by what follows
    if enc.ids[:base] != tok.encode(prefix, add_special_tokens=False).ids:
        raise SystemExit("prefix tokens change when the summary follows")
    ends, pos = [], len(prefix)
    for name, t in parts:
        pos += len(t)
        k = sum(1 for (s, e) in enc.offsets[base:] if e <= pos)
        ends.append((name, k))
    return len(enc.ids) - base, ends


R = [json.loads(l) for l in (EXP / "sessions.jsonl").open(encoding="utf-8")]
FENCE_PREFIX = "    return x;\n}\n```"     # any code line + the closing fence: the tail follows the fence
lab1 = n_tokens("Domain: LOGIC\n\nPatch under review (unified diff):\n```\n")
lab2 = n_tokens("Domain: LOGIC\n\nCode under review:\n```\n")
label_delta = lab2 - lab1
print(f"frame label tokens: R1 {lab1}, R2 {lab2}, delta {label_delta}")

out, bad = {}, 0
for r in R:
    f = r["five"]
    if not f["round2"]:
        continue
    for a in AG:
        parts = tail_parts(r, a)
        T, ends = token_ends(FENCE_PREFIX, parts)
        u1, u2 = f["round1"][a]["usage"], f["round2"][a]["usage"]
        delta = u2["state_tokens"] - u1["state_tokens"]
        if label_delta + T != delta:
            bad += 1
            if bad <= 5:
                print("  mismatch", f["id"], a, "label", label_delta, "tail", T, "observed", delta)
        D = u2["state_tokens_dropped"]
        seen = T - D                     # tail tokens inside the window
        out[f"{f['id']}|{a}"] = {
            "tail_tokens": T, "dropped": D, "seen_tail_tokens": seen,
            "parts": {name: end <= seen for name, end in ends},
            "part_end": dict(ends),
        }
print(f"rebuild check: {bad} of {sum(1 for r in R if r['five']['round2']) * 5} calls disagree with S_R2 - S_R1")
OUT.write_text(json.dumps({"label_delta": label_delta, "cuts": out}, indent=0), encoding="utf-8")

# report
print("\ntail token layout (first commit, each agent): part -> tail tokens up to its end")
r0 = next(r for r in R if r["five"]["round2"])
for a in AG:
    k = f"{r0['five']['id']}|{a}"
    print(f"  {a:<13} total {out[k]['tail_tokens']}: " + ", ".join(f"{n}={e}" for n, e in out[k]["part_end"].items()))
print("\nRound 2, per agent: summary cut | what was still seen")
for a in AG:
    rows = [v for k, v in out.items() if k.endswith("|" + a)]
    n = len(rows)
    cut = sum(v["dropped"] > 0 for v in rows)
    only_turn = sum(v["dropped"] > 0 and all(ok for name, ok in v["parts"].items() if name != "turn") for v in rows)
    k_seen = {}
    for v in rows:
        m = sum(ok for name, ok in v["parts"].items() if name.startswith("other:"))
        k_seen[m] = k_seen.get(m, 0) + 1
    own = sum(v["parts"]["own"] for v in rows)
    l_seen = {}
    for v in rows:
        m = sum(ok for name, ok in v["parts"].items() if name.startswith("label:"))
        l_seen[m] = l_seen.get(m, 0) + 1
    lost = {}
    for v in rows:
        for name, ok in v["parts"].items():
            if name.startswith("label:") and not ok:
                lost[name[6:]] = lost.get(name[6:], 0) + 1
    print(f"  {a:<13} n={n} cut {cut} ({100 * cut / n:.0f} %); instructions only {only_turn}; "
          f"other agents' lines fully seen: {dict(sorted(k_seen.items()))}; their vote labels seen: "
          f"{dict(sorted(l_seen.items()))}; labels lost: {lost}; own vote seen {own}")
    drops = sorted(v["dropped"] for v in rows if v["dropped"])
    if drops:
        print(f"  {'':<13} dropped tokens when cut: min {drops[0]}, median {drops[len(drops) // 2]}, max {drops[-1]}")
