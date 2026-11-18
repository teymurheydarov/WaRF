"""
The rest of a commit, shown to every seat that reviews one of its files (docs/spec/commit-context.md).

review-commit reviews each changed file on its own. A defect that only shows with another file of the same
change (a declaration changed in a header, a caller adapted in another file) is then invisible to every seat.
With --commit-context each file's review also gets the other files' diff, compact (3 lines of context), in at
most COMMIT_CONTEXT_CHARS characters in all.
"""
# About the median reviewed input of the fresh test sets (DuckDB 7,614, PPSSPP 6,944 characters), so that the
# other files do not outweigh the file under review. Not the model's limit: Jev took contexts of up to 76,381
# characters in the commit-context test (before the closing line was budgeted).
COMMIT_CONTEXT_CHARS = 8000
MIN_CUT = 500       # about six diff lines: less shows a patch's header and little of its change, so it is named
NAMES_MAX = 400     # room kept for the closing line of named files when not every patch fits (about 20 paths)
_CUT_MARK = "[... rest of this file's diff cut ...]\n"
_NAMED = "Also changed (diff not shown): "


def _names_line(names: list[str], room: int) -> str:
    """'Also changed (diff not shown): a, b, and N more' in at most `room` characters (names in diff order)."""
    line = _NAMED + ", ".join(names) + "\n"
    if len(line) <= room:
        return line
    kept = []
    for f in names:
        more = len(names) - len(kept) - 1
        candidate = _NAMED + ", ".join(kept + [f]) + (f", and {more} more" if more else "") + "\n"
        if len(candidate) > room:
            break
        kept.append(f)
    return _NAMED + ", ".join(kept) + f"{', and' if kept else ''} {len(names) - len(kept)} more\n"


def commit_context(patches: list[tuple[str, str]], path: str, budget: int = COMMIT_CONTEXT_CHARS) -> str | None:
    """
    The patches of the commit's files other than `path`, in diff order, in at most `budget` characters.

    If they all fit, all of them. Else NAMES_MAX characters are kept for a closing line that names the files
    not shown, and in the rest the patches come whole while they fit; the first that does not fit is cut after
    its last whole line (if at least MIN_CUT characters are left), every later one is only named. None when
    the commit changes no other file.

    patches: (path, patch) per file, as cli._parse_diff gives them.
    """
    others = [(f, p.rstrip("\n") + "\n") for f, p in patches if f != path]
    if not others:
        return None
    if sum(len(p) for _, p in others) <= budget:
        return "".join(p for _, p in others).rstrip("\n")
    names_room = min(NAMES_MAX, budget)
    room = budget - names_room
    shown, named, budget_spent = [], [], False
    for f, p in others:
        if budget_spent:
            named.append(f)
        elif len(p) <= room:
            shown.append(p)
            room -= len(p)
        else:
            budget_spent = True
            if room >= MIN_CUT:                  # cut after the last whole line that fits with the mark
                head = p[:room - len(_CUT_MARK)]
                k = head.rfind("\n")
                shown.append((head[:k + 1] if k >= 0 else head[:-1] + "\n") + _CUT_MARK)
            else:
                named.append(f)
    text = "".join(shown)
    if named:
        text += _names_line(named, names_room)
    return text.rstrip("\n")
