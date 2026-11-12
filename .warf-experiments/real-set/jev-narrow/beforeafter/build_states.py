"""Lever "beforeafter": old and new code instead of a diff (../../DEV.md 2026-11-09).

For each dev item, read the changed file before (<commit>^:<path>) and after (<commit>:<path>) the change from
the gismo6 repo (git plumbing only, read only), and cut both to the region of each hunk: the hunk's changed
lines plus 40 lines on each side, located through the diff's hunk headers. Regions that overlap (in the old or
the new file) are merged so no line appears twice; regions are joined with a "..." line. Every hunk's
context, '-' and '+' lines are checked against the file text; a mismatch is reported and stops the build. Only the diff part
of the item's code is used: the "# Full function context" appendix after it is not part of the diff.

    python build_states.py      # writes states.jsonl {id, state}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = HERE.parent.parent / "items.jsonl"
OUT = HERE / "states.jsonl"
GISMO = r"C:\Users\Teymur Heydarov\source\repos\gismo6"
PAD = 40
TASK = "Compare code_before and code_after; questions are about what the change introduces."
NOFILE = "(the file does not exist before the change)"


def git_file(rev, path):
    r = subprocess.run(["git", "-C", GISMO, "show", f"{rev}:{path}"], capture_output=True)
    if r.returncode:
        return None
    return [l.rstrip("\r") for l in r.stdout.decode("utf-8", "replace").split("\n")]


def parse(code):
    lines = code.splitlines()
    old_path = new_path = None
    hunks, cur = [], None
    for ln in lines:
        if ln.startswith("--- ") and cur is None:
            old_path = None if ln[4:].strip() == "/dev/null" else ln[4:].strip()[2:]
        elif ln.startswith("+++ ") and cur is None:
            new_path = None if ln[4:].strip() == "/dev/null" else ln[4:].strip()[2:]
        elif ln.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", ln)
            cur = {"o": int(m.group(1)), "n": int(m.group(3)), "lines": [],
                   "ro": int(m.group(2) or 1), "rn": int(m.group(4) or 1)}
            hunks.append(cur)
        elif cur is not None and (cur["ro"] > 0 or cur["rn"] > 0 or ln.startswith("\\")):
            # the header's line counts bound the hunk; the item's appended function context is not diff
            t = ln[:1] if ln else " "
            if t == " ":
                cur["ro"] -= 1; cur["rn"] -= 1
            elif t == "-":
                cur["ro"] -= 1
            elif t == "+":
                cur["rn"] -= 1
            cur["lines"].append(ln)
    return old_path, new_path, hunks


def spans(h, old, new):
    """(olo, ohi, nlo, nhi), 1-based inclusive changed span in each file, after checking the hunk's text."""
    o = h["o"] if h["o"] > 0 else 1
    n = h["n"] if h["n"] > 0 else 1
    if h["o"] == 0:
        o = 1
    od, nd, oins, nins = [], [], None, None
    for ln in h["lines"]:
        if ln.startswith("\\"):
            continue
        t, body = (ln[:1], ln[1:].rstrip("\r")) if ln else (" ", "")
        if t == " ":
            if old[o - 1] != body or new[n - 1] != body:
                raise ValueError(f"context mismatch at old {o} / new {n}")
            o += 1; n += 1
        elif t == "-":
            if old[o - 1] != body:
                raise ValueError(f"'-' mismatch at old {o}")
            od.append(o); nins = nins or n; o += 1
        elif t == "+":
            if new[n - 1] != body:
                raise ValueError(f"'+' mismatch at new {n}")
            nd.append(n); oins = oins or o; n += 1
    olo, ohi = (min(od), max(od)) if od else (oins, oins)
    nlo, nhi = (min(nd), max(nd)) if nd else (nins, nins)
    return olo, ohi, nlo, nhi


def cut(text, ranges):
    return "\n...\n".join("\n".join(text[a - 1:b]) for a, b in ranges)


def main():
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    out, bad = [], 0
    for it in items:
        op, np_, hs = parse(it["code"])
        hs = [h for h in hs if any(l[:1] in "+-" for l in h["lines"])]
        old = git_file(it["commit"] + "^", op) if op else []
        new = git_file(it["commit"], np_)
        if new is None or (op and old is None):
            print(f"  {it['id']}: file not found in git", flush=True); bad += 1; continue
        try:
            sp = [spans(h, old, new) for h in hs]
        except (ValueError, IndexError) as e:
            print(f"  {it['id']}: {e}", flush=True); bad += 1; continue
        no, nn = max(len(old), 1), len(new)
        groups = []
        for olo, ohi, nlo, nhi in sp:
            r = [max(1, olo - PAD), min(no, ohi + PAD), max(1, nlo - PAD), min(nn, nhi + PAD)]
            if groups and (r[0] <= groups[-1][1] + 1 or r[2] <= groups[-1][3] + 1):
                g = groups[-1]; g[1] = max(g[1], r[1]); g[3] = max(g[3], r[3])
            else:
                groups.append(r)
        before = cut(old, [(g[0], g[1]) for g in groups]) if op else NOFILE
        after = cut(new, [(g[2], g[3]) for g in groups])
        state = {"task": TASK, "domain": it["domain"], "file": it["file"], "code_before": before, "code_after": after}
        out.append({"id": it["id"], "hunks": len(hs), "regions": len(groups), "state": state})
    if bad:
        sys.exit(f"{bad} items failed; nothing written")
    with OUT.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    ch = [len(json.dumps(r["state"])) for r in out]
    print(f"{len(out)} states; hunks {sum(r['hunks'] for r in out)}, regions {sum(r['regions'] for r in out)}; "
          f"state chars median {sorted(ch)[len(ch) // 2]}, max {max(ch)}, total {sum(ch)}")


if __name__ == "__main__":
    main()
