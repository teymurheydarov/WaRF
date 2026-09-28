"""
Ground truth for experiments: one answer per FILE, taken from the labelled corpus.

The corpus log identifies an artifact by the path string it was reviewed under, and
the same file has been reviewed under more than one spelling (the CLI used to run
from warf/, so `..\\..\\test-subjects\\x.py` and `..\\test-subjects\\x.py` are one
file). Labels were also corrected over time by labelling a later session rather
than by editing the earlier one. Keyed by path string, a lookup can therefore
return a label that the corpus itself has since overruled — which is how
requests/help.py entered the persona reference set as APPROVE although it had been
corrected to REJECT on 2026-07-25.

So: bring every spelling to one key per file, and let the most recent label win.
Files whose labels disagree are reported, never silently resolved.

The key is computed from the path string alone (see file_key), not by finding the
file on disk. Reviewed files such as test-subjects/ live outside the repository, so
in a fresh clone nothing resolves on disk; a lookup that depended on the disk would
find no label there and quietly fall back to whatever label an experiment session
happened to store — which reproduces results the corpus has since corrected.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_LOG = ROOT / ".warf" / "sessions.jsonl"

# Working directories the corpus was logged from: the repo root today, warf/ before
# the package was restructured.
_BASES = (ROOT, ROOT / "warf")


@dataclass
class Truth:
    key: str                         # file_key(): one per file, independent of the disk
    file: Path | None                # the file on disk if it resolves here, else None
    x_star: int                      # +1 APPROVE, -1 REJECT — the most recent label
    domain: str
    spelling: str                    # a logged spelling of the file
    labelled_at: str
    history: list[tuple[str, str, str]] = field(default_factory=list)   # (date, label, session id)

    @property
    def label(self) -> str:
        return "APPROVE" if self.x_star == 1 else "REJECT"

    @property
    def conflicted(self) -> bool:
        return len({lab for _, lab, _ in self.history}) > 1


def file_key(artifact: str) -> str | None:
    """One key per reviewed file, computed from the path string alone.

    The corpus was logged from the repo root and, earlier, from warf/, so a leading
    "..\\" or "..\\..\\" does not tell two files apart: leading ".." components are
    dropped ("..\\..\\test-subjects\\x.py" and "..\\test-subjects\\x.py" are one
    file). An absolute path is first made relative to the repo root, which gives it
    the same form as the relative spellings of the same file. Case and separators
    are normalised. Commit artifacts ("<rev>:<path>") name no working-tree file:
    None.
    """
    if not artifact or ":" in artifact[2:]:
        return None
    s = artifact.replace("\\", "/")
    if s.startswith("/") or (len(s) > 1 and s[1] == ":"):
        try:
            s = os.path.relpath(s, ROOT).replace("\\", "/")
        except ValueError:                       # another drive than the repo: drop the drive
            s = s.split(":", 1)[-1]
    parts = [p for p in s.split("/") if p not in ("", ".")]
    while parts and parts[0] == "..":
        parts.pop(0)
    return "/".join(parts).lower() or None


def canonical(artifact: str) -> Path | None:
    """The file an artifact string names ON THIS DISK, or None (commit artifacts,
    files not present here). Only needed by code that opens the file, such as the
    experiment runner; ground-truth lookups use file_key()."""
    if ":" in artifact[2:]:                      # "<commit>:<path>" — not a working-tree file
        return None
    p = Path(artifact)
    for candidate in ([p] if p.is_absolute() else [base / p for base in _BASES]):
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            pass
    return None


def corpus_truth(log: Path = CORPUS_LOG) -> dict[str, Truth]:
    """{file_key: Truth} for every labelled working-tree artifact in the corpus log,
    whether or not the file is present on this disk."""
    out: dict[str, Truth] = {}
    if not log.exists():
        return out
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            s = json.loads(line)
        except json.JSONDecodeError:
            continue
        oracle = s.get("oracle") or {}
        if oracle.get("x_star") is None:
            continue
        artifact = s.get("artifact", "")
        key = file_key(artifact)
        if key is None:
            continue
        t = out.get(key)
        if t is None:
            t = out[key] = Truth(key, canonical(artifact), oracle["x_star"], s.get("domain", "AUTO"),
                                 artifact, s.get("created_at", ""))
        else:                                    # log order is time order: the later label wins
            t.x_star, t.domain, t.labelled_at = oracle["x_star"], s.get("domain", t.domain), s.get("created_at", "")
            t.spelling = artifact
            if t.file is None:
                t.file = canonical(artifact)
        t.history.append((s.get("created_at", "")[:10], oracle.get("x_star_label", "?"), s.get("session_id", "")[:8]))
    return out


def truth_for(artifact: str, truths: dict[str, Truth]) -> Truth | None:
    key = file_key(artifact)
    return truths.get(key) if key is not None else None


def describe_conflicts(truths: dict[str, Truth]) -> list[str]:
    lines = []
    for t in truths.values():
        if t.conflicted:
            trail = "  ->  ".join(f"{d} {lab} ({sid})" for d, lab, sid in t.history)
            lines.append(f"{Path(t.key).name}: {trail}   => using {t.label}")
    return lines
