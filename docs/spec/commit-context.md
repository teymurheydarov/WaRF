# Spec: commit context (`warf review-commit --commit-context`)

Status: implemented 2026-11-17, opt-in, **not shown to help** Jev's three-seat panel
(`.warf-experiments/pooled-dev/commit-context/`: 95 vs 94 changes over DuckDB and PPSSPP; it helps the locate
seat and hurts the verdict seats). Kept as an opt-in option, off by default (Teymur, 2026-11-17).
Code: `warf/commit_context.py`, `warf/orchestrator.py` (`_commit_section`), `warf/cli.py`.
Test: `tools/test_commit_context.py`.

## 1. What

`review-commit` reviews each changed file on its own. With `--commit-context`, every seat that reviews a file
is also shown the commit's other files, so that a defect that only shows with another file of the same change
(a declaration changed in a header, a caller adapted elsewhere) is visible to it.

## 2. What the seat is shown

- **Source:** one extra diff of the commit with 3 lines of context (`get_diff(repo, commit, 3)`), split into
  files by `_parse_diff`; every changed file counts, also those WaRF does not review (build files, resources).
  The file under review is left out.
- **Budget:** at most `COMMIT_CONTEXT_CHARS = 8000` characters in all, about the median reviewed input of the
  fresh test sets (DuckDB 7,614, PPSSPP 6,944 characters), so that the other files do not outweigh the file
  under review. It is not the model's limit: Jev took contexts of up to 76,381 characters in the test.
  - If every other patch fits, all of them, in diff order.
  - Else `NAMES_MAX = 400` characters (about 20 paths) are kept for a closing line
    `Also changed (diff not shown): a, b, and N more`; in the rest the patches come whole while they fit, the
    first that does not fit is cut after its last whole line and marked `[... rest of this file's diff
    cut ...]` if at least `MIN_CUT = 500` characters (about six diff lines) are left, else only named; every
    later file is only named.
  - Changed 2026-11-17 after a cold review: before, the closing line was not budgeted (a 1,384-file DuckDB
    commit gave 76,381 characters). The test of `.warf-experiments/pooled-dev/commit-context/` ran with that
    earlier rule, as preregistered.
- **None** when the commit changes no other file: the message is then exactly as without the option.
- **Placement:** its own block between the project context and the input:

  ```
  Domain: LOGIC

  Project context:
  ...

  Other files changed in this commit (unified diff):
  ```<the other files' diff>```

  Patch under review (unified diff):
  ```<the file's enriched patch>```
  ```

  The debate round (`--debate`) shows it in the same place.
- **Locate seats** keep their options: only the reviewed file's added lines are tagged `[Lk]`; the lines of
  the commit context are not options.

## 3. Unchanged

- `warf review` (one file) and the MCP server have no commit; they take no commit context.
- Calibration keys are unchanged: the same seat with and without commit context is the same reviewer, and
  the session log does not record whether the option was on. A project that switches it on should start a
  new labelled log (another `WARF_HOME`); its old labelled sessions were answered without it.
- Files already reviewed (in `sessions.jsonl`) are skipped as before; `--force` reviews them again with the
  option.
