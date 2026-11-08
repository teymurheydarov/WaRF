"""
Generate slide06.html — interactive SPRT trace for the most recent session.
Called automatically by cli.py after every review (_refresh_html).
"""
import json
from pathlib import Path

if __package__ in (None, ""):  # run as `py warf/plot_slide06.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
# The engine's own constants, not copies: this page replays the session the
# audience has just watched in the terminal, and the two must agree to the digit.
from .engine import (  # noqa: E402
    A as SPRT_A, B as SPRT_B, ALPHA_ERR, BETA_ERR, LLR_APPROVE, LLR_REJECT, P0, P1,
)
from .paths import sessions_path, html_dir  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "slide06.html"

AGENT_COLOR = {
    "AUDITOR":      "#4E79A7",
    "ADVOCATE":     "#59A14F",
    "SKEPTIC":      "#E15759",
    "BOUNDARY":     "#F28E2B",
    "TEST-FOCUSED": "#B07AA1",
}
ALL_AGENTS = ["AUDITOR", "ADVOCATE", "SKEPTIC", "BOUNDARY", "TEST-FOCUSED"]


def load_last_session(path: Path) -> dict | None:
    if not path.exists():
        return None
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    pass
    return last


def build_trace(votes: list[dict]) -> list[dict]:
    """Recompute delta and running Λ from stored omega+vote, as engine.sprt_update does.

    The step is asymmetric: an APPROVE adds ω·log(P1/P0) ≈ +0.981ω, a REJECT adds
    ω·log((1−P1)/(1−P0)) ≈ −1.253ω.
    """
    trace = []
    running = 0.0
    crossed = False
    for v in votes:
        omega = max(0.001, min(0.999, v["omega"]))
        delta = omega * (LLR_APPROVE if v["label"] == "APPROVE" else LLR_REJECT)
        running += delta
        just_crossed = (not crossed) and (running <= SPRT_B or running >= SPRT_A)
        if just_crossed:
            crossed = True
        trace.append({**v, "delta": delta, "running": running, "crossed": just_crossed})
    return trace


def _fmt(f: float) -> str:
    s = f"{f:+.3f}"
    return s


def main() -> None:
    session = load_last_session(SESSIONS)

    if session is None:
        OUTPUT.write_text(
            "<!doctype html><title>slide06</title><body style='background:#0f172a;color:#94a3b8;"
            "font-family:monospace;padding:2rem'>No sessions recorded yet.</body>",
            encoding="utf-8",
        )
        return

    votes        = session.get("votes", [])
    artifact     = session.get("artifact", "?")
    domain       = session.get("domain", "?")
    decision     = session.get("decision", "?")
    confidence   = session.get("confidence", "?")
    created_at   = (session.get("created_at") or "")[:16].replace("T", " ")
    sprt_fired   = session.get("sprt_fired", False)

    trace        = build_trace(votes)
    queried      = {v["agent"] for v in votes}
    skipped      = [a for a in ALL_AGENTS if a not in queried]

    # ── SVG chart ────────────────────────────────────────────────────────────
    W, H      = 560, 220
    PAD_L     = 68
    PAD_R     = 20
    PAD_T     = 20
    PAD_B     = 36
    plot_w    = W - PAD_L - PAD_R
    plot_h    = H - PAD_T - PAD_B

    n_steps   = len(trace) + 1          # include step 0
    y_min     = min(-2.8, SPRT_B - 0.15, min((t["running"] for t in trace), default=0) - 0.15)
    y_max     = max( 3.2, SPRT_A + 0.15, max((t["running"] for t in trace), default=0) + 0.15)

    def sx(i):   # step index 0..n_steps-1 → SVG x
        return PAD_L + i * plot_w / max(n_steps - 1, 1)

    def sy(v):   # Λ value → SVG y (y increases downward)
        return PAD_T + (y_max - v) / (y_max - y_min) * plot_h

    # grid lines
    grid_lines = ""
    for yv in [SPRT_A, 0.0, SPRT_B]:
        y  = sy(yv)
        col = "#22c55e" if yv == SPRT_A else ("#ef4444" if yv == SPRT_B else "#475569")
        lbl = f"A={SPRT_A:+.2f}" if yv == SPRT_A else (f"B={SPRT_B:+.2f}" if yv == SPRT_B else "0")
        grid_lines += (
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="{col}" stroke-width="1" stroke-dasharray="4 3" opacity="0.7"/>\n'
            f'<text x="{PAD_L - 4}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="9" fill="{col}" font-family="monospace">{lbl}</text>\n'
        )

    # polyline points: start at (0, 0), then each step
    pts = [(sx(0), sy(0.0))]
    for i, t in enumerate(trace):
        pts.append((sx(i + 1), sy(t["running"])))
    pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    # crossing point annotations
    cross_vline = ""
    cross_circle = ""
    cross_label = ""
    for i, t in enumerate(trace):
        if t["crossed"]:
            cx, cy   = sx(i + 1), sy(t["running"])
            b_y      = sy(SPRT_B) if t["running"] <= SPRT_B else sy(SPRT_A)
            # vertical dashed drop from boundary line to the crossing dot
            cross_vline = (
                f'<line x1="{cx:.1f}" y1="{min(cy, b_y):.1f}" '
                f'x2="{cx:.1f}" y2="{max(cy, b_y):.1f}" '
                f'stroke="#ef4444" stroke-width="1" stroke-dasharray="3 2" opacity="0.6"/>\n'
            )
            # large filled circle — unmissable
            cross_circle = (
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" '
                f'fill="#ef4444" stroke="#0f172a" stroke-width="2"/>\n'
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#fff"/>\n'
            )
            # "STOP" label above the dot
            label_y = cy - 11
            cross_label = (
                f'<text x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                f'font-size="8.5" font-weight="700" fill="#ef4444" '
                f'font-family="monospace">STOP</text>\n'
            )
            break

    # x-axis agent labels
    x_labels = f'<text x="{sx(0):.1f}" y="{H - 6}" text-anchor="middle" ' \
               f'font-size="8.5" fill="#475569" font-family="monospace">start</text>\n'
    for i, t in enumerate(trace):
        col = AGENT_COLOR.get(t["agent"], "#94a3b8")
        x_labels += (
            f'<text x="{sx(i+1):.1f}" y="{H - 6}" text-anchor="middle" '
            f'font-size="8.5" fill="{col}" font-family="monospace">'
            f'{t["agent"][:3]}</text>\n'
        )

    svg = f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;max-width:{W}px;display:block;margin:0 auto">
  <rect width="{W}" height="{H}" fill="#0f172a" rx="6"/>
  {grid_lines}
  {cross_vline}
  <polyline points="{pts_str}" fill="none" stroke="#60a5fa" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
  {cross_circle}
  {cross_label}
  {x_labels}
</svg>"""

    # ── table rows ────────────────────────────────────────────────────────────
    dec_cls = "approve" if decision == "APPROVE" else "reject"
    conf_cls = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(confidence, "")

    rows = ""
    for t in trace:
        col   = AGENT_COLOR.get(t["agent"], "#94a3b8")
        vbadge = (f'<span class="badge approve">APPROVE</span>'
                  if t["label"] == "APPROVE"
                  else f'<span class="badge reject">REJECT</span>')
        d_cls = "pos" if t["delta"] >= 0 else "neg"
        r_cls = "pos" if t["running"] >= 0 else "neg"
        row_cls = ' class="crossing-row"' if t["crossed"] else ""
        cross = ' <span class="cross-marker">← boundary crossed · WaRF stops</span>' if t["crossed"] else ""
        rows += f"""<tr{row_cls}>
      <td style="color:{col};font-weight:700">{t["agent"]}</td>
      <td>{vbadge}</td>
      <td class="mono muted">{t["omega"]:.4f}</td>
      <td class="mono {d_cls}">{_fmt(t["delta"])}</td>
      <td class="mono {r_cls}">{_fmt(t["running"])}{cross}</td>
    </tr>\n"""

    for a in skipped:
        col = AGENT_COLOR.get(a, "#94a3b8")
        rows += f"""<tr class="skipped-row">
      <td style="color:{col};opacity:.55;font-weight:700">{a}</td>
      <td><span class="skipped-label">skipped</span></td>
      <td class="mono muted">—</td>
      <td class="mono muted">—</td>
      <td class="mono muted">—</td>
    </tr>\n"""

    stop_reason = (
        "Accumulated evidence crossed the decision boundary. Fewer agent calls are a consequence — not the goal."
        if sprt_fired else
        "Pool exhausted without crossing a boundary."
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF — SPRT Trace</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0f172a;
  color: #e2e8f0;
  font-family: 'Segoe UI', system-ui, sans-serif;
  font-size: 15px;
  padding: 2rem 2.5rem 4rem;
  max-width: 680px;
  margin: 0 auto;
}}
h1 {{ font-size: 1.25rem; font-weight: 700; color: #e2e8f0; margin-bottom: .25rem; }}
.meta {{ font-size: .78rem; color: #475569; margin-bottom: 1.5rem; }}
.meta b {{ color: #94a3b8; }}
.flow-label {{
  font-size: .75rem; color: #475569; text-align: center;
  margin-bottom: .5rem; letter-spacing: .03em;
}}
.chart-wrap {{ margin-bottom: 1.5rem; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 1rem; }}
th {{
  font-size: .65rem; letter-spacing: .07em; text-transform: uppercase;
  color: #475569; padding: 5px 8px; text-align: left;
  border-bottom: 1px solid #1e3a5f;
}}
td {{ padding: 7px 8px; border-bottom: 1px solid #1e293b; vertical-align: middle; }}
.skipped-row td {{ opacity: .5; }}
.mono {{ font-family: 'Consolas', monospace; font-size: .82rem; }}
.muted {{ color: #475569; }}
.pos {{ color: #22c55e; }}
.neg {{ color: #ef4444; }}
.badge {{
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  font-size: .68rem; font-weight: 700;
}}
.badge.approve {{ background: #052e16; color: #22c55e; }}
.badge.reject  {{ background: #7f1d1d; color: #ef4444; }}
.skipped-label {{ font-style: italic; color: #475569; font-size: .82rem; }}
.cross-marker  {{ color: #ef4444; font-size: .75rem; font-style: italic; margin-left: .4rem; }}
.crossing-row  {{ background: #1c0a0a; border-left: 3px solid #ef4444; }}
.decision-row {{
  margin-top: .75rem; padding: .6rem 1rem; border-radius: 6px;
  background: #1e293b; border-left: 3px solid;
  font-size: .82rem; display: flex; gap: 1.5rem; align-items: center;
}}
.decision-row.reject  {{ border-color: #ef4444; }}
.decision-row.approve {{ border-color: #22c55e; }}
.decision-row .high   {{ color: #22c55e; font-weight: 700; }}
.decision-row .medium {{ color: #f59e0b; font-weight: 700; }}
.decision-row .low    {{ color: #ef4444; font-weight: 700; }}
.footer {{
  margin-top: 1.25rem; font-size: .72rem; color: #334155; line-height: 1.6;
}}
</style>
</head>
<body>
<h1>SPRT Trace — {domain} domain</h1>
<div class="meta">
  <b>{artifact}</b> &nbsp;·&nbsp; {created_at} UTC
</div>

<div class="flow-label">Λ = 0 &nbsp;→&nbsp; evidence accumulates &nbsp;→&nbsp; boundary crossed &nbsp;→&nbsp; <span style="color:#ef4444;font-weight:700">STOP</span></div>
<div class="chart-wrap">{svg}</div>

<table>
  <thead>
    <tr>
      <th>Agent</th><th>Vote</th><th>ω</th><th>Δλ</th><th>Running λ</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>

<div class="decision-row {dec_cls}">
  <span>Decision: <strong>{decision}</strong></span>
  <span>Confidence: <strong class="{conf_cls}">{confidence}</strong></span>
  <span class="muted" style="font-size:.72rem">{stop_reason}</span>
</div>

<div class="footer">
  Δλ = ω × LLR &nbsp;·&nbsp;
  REJECT: log((1−P₁)/(1−P₀)) ≈ {LLR_REJECT:+.3f} &nbsp;·&nbsp;
  APPROVE: log(P₁/P₀) ≈ {LLR_APPROVE:+.3f} &nbsp;(P₁={P1}, P₀={P0}) &nbsp;·&nbsp;
  Boundaries: B = {SPRT_B:+.3f}, A = {SPRT_A:+.3f} (α={ALPHA_ERR}, β={BETA_ERR})
</div>
</body>
</html>
"""
    OUTPUT.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
