# Lever "context": retrieved declarations (2026-11-09)

**Question.** 17 of the 66 dev defects are labelled `visible=needs_other_file`: you can only see them with a second file. Does Jev rank changes better when the state also carries the declarations of the names the change uses, taken from the same revision?

**What was asked.** For every one of the 132 dev items, clean and defective alike, `build_context.py` builds a "Related code" block. It uses no labels and no defect text.
1. It collects the identifiers on the changed (+/-) lines. Comments and string literals are removed first. It drops C++ keywords, a fixed stoplist of very common names, and names shorter than 3 characters. Option keys from `get*/add*/ask*/set*("key")` calls are kept.
2. It runs one `git grep -n -w` over `src/` of gismo6 at the item's own commit. Option keys get a `-F '"key"'` grep. A name hit in more than 60 files is dropped.
3. It resolves each name in the nearest scope: first the reviewed file outside the lines the diff shows, then its sibling `.h/.hpp/.cpp`, then the rest of `src/`. It keeps up to two declaration-like hits per name (type, macro, function, member or variable, option registration), headers preferred.
   - A function or type declared on the shown lines gets up to two caller hits from other files, if it is used in at most 10 files.
   - A name with no declaration anywhere gets one plain use, under the same limit.
4. Each hit is shown with 3 lines above and 6 below. Snippets are added, most specific name first (fewest files), until the block would pass 6000 characters.

The state is `run_narrow.frame(domain, code) + "\n\nRelated code from the same revision:\n" + block`. The questions are the frozen `run_narrow.questions()`: the verdict plus the 7 generic checks, on the whole change only, with no hunks. There were 132 calls and no errors.

**Block sizes.**
- Mean length: 3678 chars on defects, 1279 on clean items, 3689 on the 17 needs_other_file defects.
- 12 items have no block at all.
- Block length alone gives AUC 0.792, but only 0.586 within thirds of added lines. Most of it is the size of the change again.

**Cost.** $0.022411 for 132 calls, including the 2-item smoke test.

## Results (`score_context.log`)

Four scores were fixed before the run. **C is the primary.** The references are:
- N = `jevscore.ref_N()`;
- W0 = the same 7 checks on the whole state without the block (answers.jsonl);
- V0 = the verdict without the block.

| Score | AUC | Within thirds | LOO size+score | d vs N [95%] | d vs W0 [95%] | AUC, 17 nof vs clean | AUC, 49 other vs clean |
|---|---|---|---|---|---|---|---|
| N (ref) | 0.892 | 0.830 | 0.910 | — | +0.008 [−0.009, +0.028] | 0.824 | 0.916 |
| W0 (ref, whole, no ctx) | 0.884 | 0.831 | 0.904 | −0.008 [−0.028, +0.009] | — | 0.835 | 0.901 |
| V0 (ref, verdict, no ctx) | 0.855 | 0.775 | 0.848 | −0.037 [−0.074, −0.003] | −0.029 [−0.061, +0.000] | 0.797 | 0.876 |
| **C: 7 checks, whole + ctx** | 0.881 | 0.832 | 0.904 | −0.011 [−0.040, +0.015] | −0.004 [−0.027, +0.018] | 0.862 | 0.887 |
| CV: verdict, whole + ctx | 0.841 | 0.764 | 0.852 | −0.051 [−0.094, −0.011] | −0.044 [−0.084, −0.007] | 0.798 | 0.856 |
| CA: mean of C and W0 | 0.885 | 0.836 | 0.905 | −0.007 [−0.027, +0.013] | +0.001 [−0.011, +0.014] | 0.849 | 0.898 |
| CN: max(whole + ctx, hunks) | 0.885 | 0.828 | 0.904 | −0.007 [−0.027, +0.012] | +0.001 [−0.018, +0.018] | 0.850 | 0.897 |

Subset bootstraps, with the 66 clean items as negatives (d = AUC(score) − AUC(ref)):

| Defects | Comparison | d [95%] |
|---|---|---|
| 17 needs_other_file | C − W0 | +0.027 [−0.013, +0.070] |
| 17 needs_other_file | C − N | +0.037 [−0.012, +0.091] |
| 17 needs_other_file | CV − V0 | +0.000 [−0.040, +0.044] |
| 49 other | C − W0 | −0.014 [−0.038, +0.005] |
| 49 other | CV − V0 | −0.020 [−0.046, +0.002] |

The ranking barely changes: Spearman(C, W0) = 0.972.

**Reading.**
- **Overall, the related code gives no gain.** The primary C ties W0 (−0.004) and N (−0.011), and so does every other measure: within thirds 0.832 vs 0.831, LOO 0.904 vs 0.904.
- **The verdict gets slightly worse with the block** (−0.044 vs V0, CI excludes 0). One possible reason: the longer state makes Jev say REJECT more often.
- **On the 17 needs_other_file defects the checks move up and the others move down,** each by about 0.02 to 0.03. Both CIs include 0, and the two shifts cancel overall. This subset was named in the task, so it is a pre-stated comparison. With 17 positives, though, a +0.027 lead is a direction only.
- **Was the retrieval able to help at all?** A diagnostic, with no calls, compared the identifiers named in each defect description with the block; the descriptions were used only for this check, never in a state.
  - In 16 of the 17 needs_other_file items, the block contains at least one identifier the defect description names.
  - In 5 of the 17, it brings in a defect-named identifier that is absent from the diff.

  So the retrieval often reaches relevant code, and Jev does not turn it into a better ranking.

## Files
- `build_context.py`: builds the blocks and writes `context_items.jsonl` (id, names, used names, block). Its output is in `build.log`.
- `run_context.py`: asks Jev; resumable; appends to `answers_context.jsonl`. Its output is in `run.log`.
- `score_context.py`: scores with `jevscore` and writes `score_context.log` and `score_context.json`.

To rescore, run this from this folder:

```
C:\workdir\claudeVersuch\gs\cf\python.exe -B score_context.py
```
