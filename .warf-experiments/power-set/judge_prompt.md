# Judge instructions (power set, fixed 2026-11-11)

You judge, for each candidate, whether **this change introduced a defect that the later fix repairs**.
You see the change (its diff with context and function bodies) and the later fix's diff on the same
file. You may read the gismo6 repository at C:\Users\Teymur Heydarov\source\repos\gismo6 with
read-only git plumbing (`git -C <repo> show <sha>:<path>`, `git log`, `git grep <sha>`). Never check
out, reset, stash or touch its working tree. Do not use any other source.

For each candidate decide:
- **introduced**:
  - `yes`: the fix repairs a real defect (wrong result, crash, undefined behaviour, leak, compile or
    link failure on a supported configuration, broken interface) and that defect lies in lines this
    change added or changed;
  - `no`: the fix is a refactor, feature, API redesign, style, documentation, configuration or test
    change, or it repairs something that was already wrong before this change;
  - `unsure`: you cannot tell from the change, the fix and the repository.
- **visible**: `diff` if a careful reviewer could see the defect from the change's diff alone,
  `needs_other_file` if it needs another file or a caller, `not_visible` if it is not visible from
  code (or there is no defect).
- **defect**: one sentence naming the defect in this change (or what the fix does, if `no`).
- **reason**: one sentence for your verdict.

Judge each candidate on its own. Write one JSON line per candidate, exactly:
`{"judge": "<A|B>", "base": "<base>", "introduced": "...", "visible": "...", "defect": "...", "reason": "..."}`
