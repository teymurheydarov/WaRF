# Paraphrase ensemble of the generic narrow checks (2026-11-09, dev set, $0.048)

**Asked:** each of the 7 generic checks of `../run_narrow.py` was rewritten twice: the same question in different words, in generic C++ terms. The dev defect descriptions were not used. Jev was then asked the 14 paraphrases plus the verdict in one call per state: the whole change and each hunk, with run_narrow's request, framing and hunk split (`run_narrow.CHECKS` is replaced, as in `run_gismo.py`). That made 321 calls with no errors, 4 workers, and a total cost of $0.0481 (summed from `usage.cost`, including the 2-item smoke test).

**Files:**
- `run_paraphrase.py`: the 14 paraphrases; it calls `run_narrow.main()`.
- `answers_paraphrase.jsonl`: the answers.
- `run.log`
- `score_paraphrase.py`: imports `../jevscore.py`; writes `score.log` and `scores.json`.

**Scores, fixed before any result was seen.** The primary is P21.
- **P21:** for each check, average the logit of the hunk max over three answers: the original one (`../answers.jsonl`) and the two paraphrases. Then take the mean over the 7 checks.
- **P14:** the 14 paraphrases alone, mean logit of the hunk max.
- **Pa and Pb:** each paraphrase set alone.

| Score (132 items) | AUC | AUC within thirds | LOO size + score | AUC − ref N, 95% bootstrap |
|---|---|---|---|---|
| ref N (generic 7, frozen) | 0.892 | 0.830 | 0.910 | |
| **P21: original + 2 paraphrases** | **0.897** | **0.838** | **0.912** | +0.005 [−0.004, +0.016] |
| P14: 14 paraphrases alone | 0.901 | 0.846 | 0.896 | +0.009 [−0.004, +0.025] |
| Pa: paraphrase set a | 0.896 | 0.844 | 0.908 | +0.004 [−0.012, +0.020] |
| Pb: paraphrase set b | 0.903 | 0.848 | 0.899 | +0.011 [−0.004, +0.028] |

**Findings:**
- **The ensemble does not beat the reference.** Every interval contains 0, and the primary gains +0.005 AUC.
- **Jev barely reacts to wording.** For each check, the item logits of the original and a paraphrase correlate 0.89–0.97 (Pearson). The 7-check means correlate 0.99 between N and P14, and 0.99 between Pa and Pb.
- **Averaging three wordings therefore averages near-copies.** There is little independent noise to cancel.
- **Single checks move by up to ±0.04 AUC between wordings**, for example off-by-one 0.823 / 0.859 / 0.819 and interface 0.644 / 0.631 / 0.691. The mean over 7 checks moves by about ±0.01.
- **The verdict re-asked gives AUC 0.852**, against 0.856 originally.
- This agrees with `../DEV.md`: every variant tried lands within about ±0.015 of N.
