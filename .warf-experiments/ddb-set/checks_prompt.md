# Prompt for the checks agent (DuckDB set, fixed 2026-11-14 before judging)

You are given `defect_profile.md`, the kinds of defect that DuckDB's past changes introduced.

Write exactly seven YES/NO questions that a reviewer asks about the changed lines of a new DuckDB change,
so that a YES means the change has one of these defects. Rules:

- Each question covers one kind of defect from the profile, or one frequent pattern within a kind; the
  most frequent kinds get the questions first, and every kind gets at least one question if seven allow.
- Each question begins with "Do the changed lines", "Does the change", "Would the changed lines" or
  "Does a changed", is one sentence of at most 45 words, and names concrete patterns from the profile in
  brackets or after "for example".
- A YES must mean a defect, not a style point; do not ask about tests, comments or documentation unless the
  profile names them as defects.
- Use only the profile; do not add patterns from general knowledge.

Write the seven questions to `checks.md`, one per line, nothing else (no numbering, no blank lines).
