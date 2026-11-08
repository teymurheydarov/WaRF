src = open(r"C:/workdir/warf/WaRF/.warf-experiments/logodds-review/verify-spec/mut.py", encoding="utf-8").read()
head, rest = src.split("M = [", 1)
tail = rest.split("\n]\n", 1)[1]
M = [("logodds acts as no_early_stop", "warf/orchestrator.py",
      "            skipped = len(profiles) - i - 1\n",
      "            if calibrator is not None:\n                early_decision = early_decision or boundary\n                continue\n            skipped = len(profiles) - i - 1\n")]
exec(head + "\n" + tail, {"M": M, "__name__": "__main__"})
