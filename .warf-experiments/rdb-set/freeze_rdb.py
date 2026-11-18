"""Freeze the arms of README.md from the 844 labelled G+Smo, MFEM and KeePassXC changes, before any RocksDB
change is judged or reviewed.

    python freeze_rdb.py      # writes calib_sessions.jsonl (the persona seats), calib_size.jsonl, calib_V1.jsonl"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent)); sys.path.insert(0, str(EXP / "kpx-set"))
from freeze import SIZE_TEXT, size_p  # noqa: E402
from warf.calibration import p_reject_from_text  # noqa: E402
from warf.state import persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import DEFAULT_PERSONA  # noqa: E402


def main():
    items = {}
    for f in ("real-set/items.jsonl", "confirm-set/items.jsonl", "mfem-set/items.jsonl", "kpx-set/items.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l); items[r["id"]] = r
    keep = ("agent", "persona", "provider", "model", "vote")
    sessions = {}
    for f in ("confirm-set/jev-learned/dev_sessions.jsonl", "confirm-set/jev-learned/sessions_LO.jsonl",
              "mfem-set/sessions_LO.jsonl", "kpx-set/sessions_LO.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l)
            votes = []
            for v in r["votes"]:
                p = p_reject_from_text(v["reasoning"])        # the dev log has no p_reject field: WaRF reads it so
                if v.get("p_reject", p) != p:
                    raise SystemExit(f"{r['artifact']} {v['agent']}: logged p differs from its readout")
                votes.append({k: v[k] for k in keep} | {"p_reject": p, "evidence_source": ""})
            sessions[r["artifact"]] = votes
    if set(sessions) != set(items):
        raise SystemExit("persona votes missing for some items")
    x = {i: (-1 if it["kind"] == "defective" else 1) for i, it in items.items()}
    with (HERE / "calib_sessions.jsonl").open("w", encoding="utf-8") as f:
        for i in items:
            f.write(json.dumps({"artifact": i, "oracle": {"type": "DEVELOPER", "x_star": x[i]}, "votes": sessions[i]}) + "\n")
    v1 = {}
    for f in ("real-set/jev-narrow/answers.jsonl", "confirm-set/jev-narrow/answers.jsonl",
              "mfem-set/answers_narrow.jsonl", "kpx-set/answers_V1.jsonl"):
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l)
            if r["state"] == "whole" and "jev-1.14" in r["model"]:
                v1[r["id"]] = min(0.99, max(0.01, round((r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0), 2)))
    if set(v1) != set(items):
        raise SystemExit("one-Jev answers missing for some items")
    for name, agent, text, provider, model, p in (
            ("calib_V1.jsonl", "JEV", DEFAULT_PERSONA, "jev", "jev-1.14", v1),
            ("calib_size.jsonl", "SIZE", SIZE_TEXT, "size", "", {i: size_p(it["code"]) for i, it in items.items()})):
        with (HERE / name).open("w", encoding="utf-8") as f:
            for i in items:
                vote = {"agent": agent, "persona": persona_hash(text), "provider": provider, "model": model,
                        "evidence_source": "", "vote": -1 if p[i] >= 0.5 else 1, "p_reject": p[i]}
                f.write(json.dumps({"artifact": i, "oracle": {"type": "DEVELOPER", "x_star": x[i]}, "votes": [vote]}) + "\n")
    print(f"{len(items)} training changes ({sum(t == 1 for t in x.values())} clean) written to calib_sessions, calib_size, calib_V1")


if __name__ == "__main__":
    main()
