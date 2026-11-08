# Development log (the 132-item real set)

Nothing here is evidence. Every variant looked at is listed, so the number of looks is on record. A panel chosen here must be frozen and confirmed once on a fresh set.

## dev_explore.py, 2026-11-06 07:22: 414 variants looked at
best single call: claude-commit-strict 0.864; top 15:
  0.879  caught 56/66  false alarms 6/66  1-of-2 claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  2-of-3 claude+claude-strict+claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  2-of-3 claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  2-of-3 claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude+claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude-commit+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 56/66  false alarms 6/66  log-odds claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  log-odds claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict+claude-advocate
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 56/66  false alarms 6/66  log-odds claude-commit+claude-strict+claude-commit-strict+claude-standard

## finder + checker, 2026-11-06 07:32 (claude-verify on the 92 items claude-commit rejected; missing 0)
  0.773  caught 64/66  false alarms 28/66  finder alone (claude-commit)
  0.864  caught 56/66  false alarms 8/66  checker alone where asked
  0.864  caught 56/66  false alarms 8/66  finder AND checker
  0.864  caught 52/66  false alarms 4/66  best single: claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  OR(strict, commit-strict) = W3
  0.886  caught 59/66  false alarms 8/66  OR(finder-checker, commit-strict)

## search checker: first 2 smoke answers discarded (the snapshot path used the 8.3 short name and the CLI refused it; fixed)
## finder + search checker, 2026-11-06 07:52
  0.894  caught 57/66  false alarms 5/66  finder AND search checker
  0.864  caught 56/66  false alarms 8/66  finder AND checker (no search)
  0.864  caught 52/66  false alarms 4/66  best single: claude-commit-strict
  0.902  caught 60/66  false alarms 7/66  OR(finder-search-checker, commit-strict)
  0.879  caught 59/66  false alarms 9/66  OR(finder-search-checker, strict)
  0.894  caught 61/66  false alarms 9/66  finder AND (checker OR search checker)
  0.864  caught 52/66  false alarms 4/66  finder AND checker AND search checker

## single strict reviewer with search, 2026-11-06 08:12
  0.894  caught 54/66  false alarms 2/66  one Claude, strict, whole commit + search
  0.894  caught 57/66  false alarms 5/66  finder AND search checker
  0.864  caught 52/66  false alarms 4/66  best single so far: commit-strict
  0.894  caught 58/66  false alarms 6/66  OR(finder-search-checker, strict+search)
  finder+search checker vs strict+search: only panel 5, only single 5, McNemar p 1.000

## effort levels (Opus, whole commit + search, strict), 2026-11-06 18:09
  0.939  caught 62/66  FA 4/66  1-of-3 low+default+max   vs best single (low): 6/3 p 0.508
  0.939  caught 62/66  FA 4/66  1-of-4 low+default+high+max   vs best single (low): 6/3 p 0.508
  0.932  caught 61/66  FA 4/66  1-of-2 low+max   vs best single (low): 5/3 p 0.727
  0.932  caught 61/66  FA 4/66  1-of-3 low+high+max   vs best single (low): 5/3 p 0.727
  0.924  caught 60/66  FA 4/66  1-of-3 default+high+max   vs best single (low): 6/5 p 1.000
  0.917  caught 56/66  FA 1/66  low   vs best single (low): 0/0 p 1.000
  0.917  caught 57/66  FA 2/66  1-of-2 low+default   vs best single (low): 1/1 p 1.000
  0.917  caught 59/66  FA 4/66  1-of-2 default+max   vs best single (low): 6/6 p 1.000
  0.917  caught 59/66  FA 4/66  1-of-2 high+max   vs best single (low): 5/5 p 1.000
  0.917  caught 58/66  FA 3/66  1-of-3 low+default+high   vs best single (low): 2/2 p 1.000
  0.909  caught 57/66  FA 3/66  1-of-2 low+high   vs best single (low): 1/2 p 1.000
  0.902  caught 54/66  FA 1/66  2-of-2 low+high   vs best single (low): 0/2 p 0.500
  single low: 0.917  caught 56/66 FA 1/66
  single default: 0.894  caught 54/66 FA 2/66
  single high: 0.894  caught 55/66 FA 3/66
  single max: 0.894  caught 56/66 FA 4/66
  pairwise disagreement (items): low-default 5, low-high 5, low-max 13, default-high 4, default-max 10, high-max 8
  (32 effort variants looked at)


## 2026-11-08: reviewer weights conditioned on the type of change (`dev_bytype.py`, no new calls)

The idea came from a lecture note: global weights can't say "reviewer A is good on module X and noise on module Y". Here the change type is the G+Smo module of the file (gsAssembler 28, gsCore 27, gsNurbs 12, the rest 9 or fewer). The pool is the 13 reviewers with all 132 answers. Everything is leave-one-out.

| Rule | BA |
|---|---|
| Best single reviewer, chosen globally (always picks Opus strict + commit + search at low) | 0.917 |
| Best single reviewer, chosen per module (falls back to global if fewer than 8 items) | 0.886 |
| Naive-Bayes pool of all 13, per-module rates shrunk to the global ones | 0.909 |

Conditioning makes things worse. The module winners in-sample differ (ADVOCATE on gsHSplines and gsIO, strict Opus on gsModeling), but those come from 7 to 9 items each and don't carry over to the held-out item.
