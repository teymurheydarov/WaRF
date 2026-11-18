# Prompt for the defect-profile agent (PPSSPP set, fixed 2026-11-16 before judging)

You are given `history_defects.md`: confirmed defects from PPSSPP's past changes. Each line is the file, the
date of the change that introduced the defect, and two independent one-sentence descriptions of it. They
are labelled history, not the changes WaRF will review.

Write a defect profile that a code reviewer reads before reviewing a new PPSSPP change: the kinds of defect
this project's changes introduce, so that the reviewer knows what to check a diff for.

- Group the defects into at most six kinds. For each kind, say about how many of the defects it covers,
  then name the concrete patterns behind it (types, functions, configurations, idioms, as specific as the
  descriptions allow).
- Most frequent kind first.
- Write only what the descriptions support; do not add kinds from general knowledge.
- At most 1,300 characters in all; start with the line "PPSSPP defect profile (N past defects). Check a diff
  for:" and use one bullet per kind.

Write the profile to `defect_profile.md` and nothing else.
