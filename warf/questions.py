"""
Questions a decision seat can be asked besides WaRF's verdict (docs/spec/learned-aggregation.md §2).

  check   the persona is a YES/NO question about the changed lines; YES is the defect
  locate  the persona asks WHICH added line has a problem; every added line of the diff is tagged
          [L1], [L2], ... in the input and offered as an option, with NONE
A persona of several lines is several such questions, asked in one call (persona_questions).
"""
import re

from .context_extractor import _SEPARATOR

QUESTIONS = ("check", "locate")
_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")

CHECK_CRITERIA = {
    "YES": "Yes, the changed lines have this problem.",
    "NO":  "No, the changed lines do not have this problem.",
}

LOCATE_NONE = "NONE"
LOCATE_NONE_TEXT = "None of these added lines has this problem."
LOCATE_WINDOW = 60          # options per request; longer diffs are asked in windows
LOCATE_OPTION_CHARS = 50    # how much of a line its option repeats


def persona_questions(persona: str) -> list[str]:
    """
    A question seat's questions: the persona's non-empty lines, stripped. One line is one question; several
    are asked together in one call and pooled as "any of them finds a problem" (learned-aggregation.md §2).
    """
    return [line.strip() for line in persona.splitlines() if line.strip()]


def mark_added_lines(code: str) -> tuple[str, list[str]]:
    """
    The input with each added diff line tagged `+[Lk] `, and the added lines' text (stripped).

    An added line is a `+` line inside a hunk, as long as the line counts of its `@@ -a,b +c,d @@` header
    say: so a file header `+++ b/...` is never one, and an added line whose own text starts with `++` is.
    Only the diff is marked: the function context WaRF appends after its separator is left as it is. An
    input without hunks (not a diff) has no added lines.
    """
    diff, sep, rest = code.partition(_SEPARATOR)
    out, added = [], []
    old_left = new_left = 0
    for line in diff.split("\n"):
        header = _HUNK.match(line)
        if header:
            old_left, new_left = int(header.group(1) or 1), int(header.group(2) or 1)
        elif old_left > 0 or new_left > 0:
            if line.startswith("+"):
                new_left -= 1
                added.append(line[1:].strip())
                out.append(f"+[L{len(added)}] {line[1:]}")
                continue
            if line.startswith("-"):
                old_left -= 1
            elif not line.startswith("\\"):          # "\ No newline at end of file" counts for neither side
                old_left -= 1
                new_left -= 1
        out.append(line)
    return "\n".join(out) + sep + rest, added


def locate_criteria(lines: list[str], start: int) -> dict[str, str]:
    """Options for the window of `lines` that begins at added line start + 1, then NONE."""
    opts = {f"L{start + k + 1}": f"the added line marked [L{start + k + 1}]: {text[:LOCATE_OPTION_CHARS]}"
            for k, text in enumerate(lines)}
    opts[LOCATE_NONE] = LOCATE_NONE_TEXT
    return opts
