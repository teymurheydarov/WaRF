# WaRF's default panel on Claude Haiku 4.5 (stopped)

2026-11-02. WaRF's default profile with WaRF's default provider (the Claude CLI,
`claude-haiku-4-5-20251001`), debate on, early stopping off, on the 100 commits of
`../laya-five/selection.jsonl`. Stopped at the user's request after 59 of 100 reviews; the
AUDITOR-five-times arm never ran. The Jev version of the default panel is in `../jev-five/`
(`--arm standard`).

- `check_cli.py`: the real `warf review-commit --debate` sends the runner's messages, both rounds,
  2 of 2 commits (`check_cli.log`).
- `score_standard.py` on the 56 reviews done at 19:23 (partial, unverified): panel AUC 0.54
  Round 1, 0.52 after the debate; Claude Opus 0.78 on the same commits.
- Found on the way:
  - WaRF's `find_claude_exe()` does not find the desktop app's CLI
    (`AppData\Local\Claude-Data\...\claude-code\<version>\<hash>\claude.exe`), so WaRF falls back
    to `anthropic` and fails without `ANTHROPIC_API_KEY`. The runner put the CLI on PATH.
  - The CLI gives each agent its default tools (Bash, PowerShell, Read, Edit, Write, ...) and the
    account's connectors, in the home folder. Read-only shell commands run without asking: one
    SKEPTIC call ran `find` and `grep -r` over the home folder and timed out, so WaRF dropped its
    vote (`audit_transcripts.py`). Each call also leaves a ~250 KB transcript in
    `~/.claude/projects/C--Users-Teymur-Heydarov/`.
