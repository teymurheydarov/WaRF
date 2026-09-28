"""
Generate token_cost_chart.html — SPRT efficiency: token cost vs agents used.
Run:  py warf/plot_tokens.py
"""
import json
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):  # run as `py warf/plot_tokens.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
from .paths import sessions_path, html_dir, open_in_browser  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "token_cost_chart.html"

_MIN_TOKENS = 200  # sessions below this have missing token data; skip them


def extract(path: Path) -> list[dict]:
    sessions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            tok_in  = s.get("total_tokens_in",  0) or 0
            tok_out = s.get("total_tokens_out", 0) or 0
            total   = tok_in + tok_out
            agents  = len(s.get("votes", []))
            if agents == 0 or total < _MIN_TOKENS:
                continue  # skip sessions without token tracking
            sessions.append({
                "agents":     agents,
                "tokens":     total,
                "tokens_in":  tok_in,
                "tokens_out": tok_out,
                "confidence": s.get("confidence", "LOW") or "LOW",
                "decision":   s.get("decision",   "?"),
                "sprt_fired": bool(s.get("sprt_fired", False)),
                "domain":     s.get("domain", "?"),
                "artifact":   Path(s.get("artifact", "?")).name,
            })
    return sessions


def build_summary(rows: list[dict]) -> list[dict]:
    """Two bars: SPRT early-stop vs full run (all agents used)."""
    groups = {True: [], False: []}
    for r in rows:
        groups[r["sprt_fired"]].append(r["tokens"])
    summary = []
    for fired, label in [(True, "SPRT early stop"), (False, "All agents ran")]:
        vals = groups[fired]
        if not vals:
            continue
        summary.append({
            "label": label,
            "fired": fired,
            "mean":  round(sum(vals) / len(vals)),
            "min":   min(vals),
            "max":   max(vals),
            "count": len(vals),
        })
    return summary


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF — Tokens vs Agents Consulted</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #e2e8f0;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding: 28px 32px 48px;
}
h1 {
  font-size: 1.35rem;
  font-weight: 600;
  color: #c8d8f4;
  margin-bottom: 6px;
}
.subtitle {
  font-size: 0.82rem;
  color: #64748b;
  margin-bottom: 28px;
  line-height: 1.6;
}
.charts {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.chart-card {
  background: #1e293b;
  border-radius: 10px;
  padding: 16px 18px 14px;
  flex: 1 1 380px;
}
.chart-title {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #7ea8d4;
  margin-bottom: 10px;
}
canvas { display: block; width: 100%; }

.legend {
  display: flex;
  gap: 8px 16px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 0.74rem;
  color: #94a3b8;
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-dot  { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }

.stats-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 20px;
}
.stat-chip {
  background: #1e293b;
  border-radius: 8px;
  padding: 10px 16px;
  min-width: 130px;
}
.stat-label  { font-size: 0.7rem; color: #64748b; letter-spacing: 0.08em; text-transform: uppercase; }
.stat-value  { font-size: 1.5rem; font-weight: 700; color: #c8d8f4; line-height: 1.3; }
.stat-sub    { font-size: 0.72rem; color: #475569; margin-top: 1px; }

#tooltip {
  position: fixed;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 7px 11px;
  font-size: 0.76rem;
  pointer-events: none;
  display: none;
  z-index: 999;
  line-height: 1.6;
  max-width: 230px;
  color: #e2e8f0;
}
</style>
</head>
<body>
<h1>WaRF — SPRT Efficiency: Tokens vs Agents Consulted</h1>
<div class="subtitle">
  SPRT fires early when agents agree — fewer opinions needed, fewer tokens spent.
</div>

<div id="stats-row" class="stats-row"></div>

<div class="charts" style="margin-top:20px">

  <!-- Chart 1: how many opinions were needed? -->
  <div class="chart-card">
    <div class="chart-title">How many opinions were needed?</div>
    <div id="proportion-chart"></div>
  </div>

  <!-- Chart 2: SPRT early-stop vs full run -->
  <div class="chart-card">
    <div class="chart-title">SPRT early stop vs full run</div>
    <canvas id="bar" height="280"></canvas>
  </div>

</div>
<div id="tooltip"></div>

<script>
const ROWS    = __ROWS__;
const SUMMARY = __SUMMARY__;

// ── Stat chips ────────────────────────────────────────────────────────────────
(function buildStats() {
  const total     = ROWS.length;
  const earlyStop = ROWS.filter(r => r.sprt_fired).length;
  const pctEarly  = Math.round(earlyStop / total * 100);
  const avgAll    = Math.round(ROWS.reduce((s, r) => s + r.tokens, 0) / total);
  const earlyRows = ROWS.filter(r => r.sprt_fired);
  const avgEarly  = earlyRows.length ? Math.round(earlyRows.reduce((s,r)=>s+r.tokens,0)/earlyRows.length) : 0;
  const fullRows  = ROWS.filter(r => !r.sprt_fired);
  const avgFull   = fullRows.length  ? Math.round(fullRows.reduce((s,r)=>s+r.tokens,0)/fullRows.length)   : 0;
  const avgAgents = (ROWS.reduce((s, r) => s + r.agents, 0) / total).toFixed(2);
  const maxAgents = Math.max(...ROWS.map(r => r.agents));

  const row = document.getElementById("stats-row");
  const chips = [
    { label: "Reviews",           value: total,              sub: "total sessions" },
    { label: "SPRT early stop",   value: `${pctEarly}%`,    sub: `${earlyStop} of ${total} sessions` },
    { label: "Avg agents consulted", value: `${avgAgents} / ${maxAgents}`, sub: "avg reviewers consulted" },
    { label: "Avg tokens (all)",  value: avgAll.toLocaleString(), sub: "input + output" },
    { label: "Avg (early stop)",  value: avgEarly.toLocaleString(), sub: "vs " + avgFull.toLocaleString() + " (full run)" },
  ];
  chips.forEach(c => {
    const el = document.createElement("div");
    el.className = "stat-chip";
    el.innerHTML = `<div class="stat-label">${c.label}</div><div class="stat-value">${c.value}</div><div class="stat-sub">${c.sub}</div>`;
    row.appendChild(el);
  });
})();

const PAD = { l: 56, r: 20, t: 14, b: 38 };
const tooltip = document.getElementById("tooltip");

// ── Proportion chart: stopped early vs full run ───────────────────────────────
(function drawProportion() {
  const total     = ROWS.length;
  const earlyN    = ROWS.filter(r => r.sprt_fired).length;
  const fullN     = total - earlyN;
  const earlyPct  = Math.round(earlyN / total * 100);
  const fullPct   = 100 - earlyPct;

  const container = document.getElementById("proportion-chart");
  container.style.padding = "24px 8px 8px";

  const rows = [
    { label: "Stopped early",  n: earlyN, pct: earlyPct, color: "#16a34a", sub: "SPRT fired — agents agreed" },
    { label: "Full review",    n: fullN,  pct: fullPct,  color: "#4E79A7", sub: "all agents consulted" },
  ];

  rows.forEach(row => {
    const wrap = document.createElement("div");
    wrap.style.cssText = "margin-bottom:28px";

    // Label row
    const labelRow = document.createElement("div");
    labelRow.style.cssText = "display:flex;justify-content:space-between;align-items:baseline;margin-bottom:7px";
    labelRow.innerHTML =
      `<span style="font-size:0.88rem;font-weight:600;color:#c8d8f4">${row.label}</span>` +
      `<span style="font-size:1.45rem;font-weight:700;color:${row.color}">${row.pct}%` +
      `<span style="font-size:0.72rem;font-weight:400;color:#64748b;margin-left:6px">n=${row.n}</span></span>`;

    // Bar track
    const track = document.createElement("div");
    track.style.cssText = "background:#0f172a;border-radius:4px;height:28px;overflow:hidden";
    const fill = document.createElement("div");
    fill.style.cssText = `width:0%;height:100%;border-radius:4px;background:${row.color};transition:width 0.8s ease`;
    track.appendChild(fill);

    // Sub-label
    const sub = document.createElement("div");
    sub.style.cssText = "font-size:0.72rem;color:#475569;margin-top:5px";
    sub.textContent = row.sub;

    wrap.appendChild(labelRow);
    wrap.appendChild(track);
    wrap.appendChild(sub);
    container.appendChild(wrap);

    // Animate bar after paint
    requestAnimationFrame(() => requestAnimationFrame(() => {
      fill.style.width = `${row.pct}%`;
    }));
  });
})();

// ── Bar chart: mean tokens per agent count ────────────────────────────────────
(function drawBar() {
  const canvas = document.getElementById("bar");
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 380;
  const H   = 280;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;

  const maxMean = Math.max(...SUMMARY.map(s => s.mean)) * 1.15;
  const n       = SUMMARY.length;
  const barW    = Math.min(60, (pw / n) * 0.6);
  const gap     = pw / n;

  const xCenter = i => PAD.l + gap * i + gap / 2;
  const yS = v => PAD.t + (1 - v / maxMean) * ph;

  // Background
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, H);

  // Y grid
  ctx.strokeStyle = "#1e3a5f"; ctx.lineWidth = 0.8;
  [0, 0.25, 0.5, 0.75, 1].forEach(f => {
    const v = f * maxMean;
    const py = yS(v);
    ctx.beginPath(); ctx.moveTo(PAD.l, py); ctx.lineTo(PAD.l + pw, py); ctx.stroke();
    ctx.fillStyle  = "#475569"; ctx.font = "10px monospace"; ctx.textAlign = "right";
    ctx.fillText((v / 1000).toFixed(1) + "k", PAD.l - 5, py + 3.5);
  });

  // Axes
  ctx.strokeStyle = "#334155"; ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t); ctx.lineTo(PAD.l, PAD.t + ph); ctx.lineTo(PAD.l + pw, PAD.t + ph);
  ctx.stroke();

  // Bar colors: green for early stop, blue for full run
  const BAR_COLORS = { true: ["#16a34a", "#052e16"], false: ["#4E79A7", "#2a4a6e"] };

  // Bars
  const hits = [];
  SUMMARY.forEach((s, i) => {
    const cx   = xCenter(i);
    const yTop = yS(s.mean);
    const yBot = yS(0);
    const hh   = yBot - yTop;
    const [c0, c1] = BAR_COLORS[s.fired];

    const grad = ctx.createLinearGradient(0, yTop, 0, yBot);
    grad.addColorStop(0, c0);
    grad.addColorStop(1, c1);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(cx - barW / 2, yTop, barW, hh, [4, 4, 0, 0]);
    ctx.fill();

    // Min/max range line
    const yMin = yS(s.min), yMax = yS(s.max);
    ctx.strokeStyle = "#7ea8d4"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(cx, yMin); ctx.lineTo(cx, yMax); ctx.stroke();
    ctx.strokeStyle = "#7ea8d4"; ctx.lineWidth = 1;
    [yMin, yMax].forEach(py => {
      ctx.beginPath(); ctx.moveTo(cx - 4, py); ctx.lineTo(cx + 4, py); ctx.stroke();
    });

    // Value label
    ctx.fillStyle  = "#c8d8f4"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
    ctx.fillText((s.mean / 1000).toFixed(1) + "k", cx, yTop - 5);

    // X labels
    ctx.fillStyle = "#94a3b8"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(s.label, cx, PAD.t + ph + 14);
    ctx.fillStyle = "#475569"; ctx.font = "9px sans-serif";
    ctx.fillText(`n=${s.count}`, cx, PAD.t + ph + 26);

    hits.push({ cx, yTop, yBot, barW, ...s });
  });

  // Y label
  ctx.save();
  ctx.translate(12, PAD.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle  = "#475569"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("mean total tokens", 0, 0);
  ctx.restore();

  canvas.addEventListener("mousemove", e => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let best = null;
    hits.forEach(h => {
      if (mx >= h.cx - h.barW / 2 - 4 && mx <= h.cx + h.barW / 2 + 4 && my >= h.yTop - 4 && my <= h.yBot + 4)
        best = h;
    });
    if (best) {
      tooltip.style.display = "block";
      tooltip.style.left    = (e.clientX + 14) + "px";
      tooltip.style.top     = (e.clientY - 40) + "px";
      tooltip.innerHTML =
        `<b>${best.label}</b>&ensp;(${best.count} sessions)<br>` +
        `Mean: ${best.mean.toLocaleString()} tokens<br>` +
        `Range: ${best.min.toLocaleString()} – ${best.max.toLocaleString()}`;
    } else {
      tooltip.style.display = "none";
    }
  });
  canvas.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
})();
</script>
</body>
</html>
"""


def main() -> None:
    rows = extract(SESSIONS)
    if not rows:
        print("No sessions found in", SESSIONS)
        return

    summary = build_summary(rows)

    html = (_TEMPLATE
            .replace("__ROWS__",    json.dumps(rows))
            .replace("__SUMMARY__", json.dumps(summary)))

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    print(f"Sessions: {len(rows)}  |  SPRT early-stop: {sum(1 for r in rows if r['sprt_fired'])}")

    open_in_browser(OUTPUT)


if __name__ == "__main__":
    main()
