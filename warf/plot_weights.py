"""
Generate weight_trajectories.html — ω learning curves per agent per domain.
Run:  py warf/plot_weights.py
Opens warf/weight_trajectories.html in your browser.
"""
import json
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):  # run as `py warf/plot_weights.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
from .paths import sessions_path, html_dir, open_in_browser  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "weight_trajectories.html"

AGENTS = ["AUDITOR", "ADVOCATE", "SKEPTIC", "BOUNDARY", "TEST-FOCUSED"]
COLORS = {
    "AUDITOR":      "#4E79A7",
    "ADVOCATE":     "#59A14F",
    "SKEPTIC":      "#E15759",
    "BOUNDARY":     "#F28E2B",
    "TEST-FOCUSED": "#B07AA1",
}
DOMAIN_ORDER = ["LOGIC", "SECURITY", "PERFORMANCE"]


def extract(path: Path) -> dict:
    """
    Return dict: domain -> agent -> {"init": float, "points": [{"idx", "omega", "correct"}]}
    init  = ω at the very first appearance of (domain, agent) in any vote
    points = one entry per oracle update, in chronological order
    """
    sessions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                sessions.append(json.loads(line))
    sessions.sort(key=lambda s: s.get("created_at", ""))

    init_omega: dict[tuple, float] = {}          # (domain, agent) -> first seen omega
    traj: dict[tuple, list]        = defaultdict(list)
    counts: dict[tuple, int]       = defaultdict(int)

    for s in sessions:
        domain = s.get("domain", "?")
        # Record first-seen omega from every vote (not just oracle sessions)
        for v in s.get("votes", []):
            key = (domain, v["agent"])
            if key not in init_omega:
                init_omega[key] = v.get("omega", 0.5)
        # Record oracle updates
        oracle = s.get("oracle")
        if oracle and oracle.get("weight_updates"):
            for u in oracle["weight_updates"]:
                key = (domain, u["agent"])
                counts[key] += 1
                traj[key].append({
                    "idx":     counts[key],
                    "omega":   round(u["omega_after"], 6),
                    "correct": u["correct"],
                })

    # Build per-domain structure
    domains = sorted({k[0] for k in traj}, key=lambda d: DOMAIN_ORDER.index(d) if d in DOMAIN_ORDER else 99)
    result = {}
    for domain in domains:
        result[domain] = {}
        for agent in AGENTS:
            key = (domain, agent)
            if key in traj:
                result[domain][agent] = {
                    "init":   round(init_omega.get(key, 0.5), 6),
                    "points": traj[key],
                }
    return result


# ── HTML template ─────────────────────────────────────────────────────────────
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF — Weight Trajectories</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #e2e8f0;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding: 28px 32px 40px;
}
h1 {
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #c8d8f4;
  margin-bottom: 6px;
}
.subtitle {
  font-size: 0.82rem;
  color: #64748b;
  margin-bottom: 28px;
  line-height: 1.6;
}
.domain-grid {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.domain-card {
  background: #1e293b;
  border-radius: 10px;
  padding: 16px 18px 14px;
  flex: 1 1 320px;
  min-width: 280px;
}
.domain-title {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #7ea8d4;
  margin-bottom: 10px;
}
canvas { display: block; width: 100%; }
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 10px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.73rem;
  color: #94a3b8;
  cursor: pointer;
  padding: 2px 6px 2px 4px;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: background 0.1s, border-color 0.1s;
}
.legend-item:hover { background: #1e293b; }
.legend-item.front {
  color: #e2e8f0;
  font-weight: 700;
  background: #1e293b;
  border-color: #334155;
}
.legend-swatch {
  width: 22px;
  height: 3px;
  border-radius: 2px;
  flex-shrink: 0;
}
.legend-hint {
  font-size: 0.68rem;
  color: #475569;
  margin-top: 6px;
}
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
  color: #e2e8f0;
  line-height: 1.6;
  max-width: 220px;
}
</style>
</head>
<body>
<h1>WaRF — Agent Reliability Learning Curves</h1>
<div class="subtitle">
  Each point = one oracle update (ground-truth label applied).<br>
  Dashed line: ω = 0.5, the weight of an agent nobody has tested yet. Above it the agent has been right more often than wrong.<br>
  Below it the vote still counts in its own direction &#x2014; only with less weight (Δλ = ω × LLR; ω never flips the sign).
</div>
<div class="domain-grid" id="grid"></div>
<div id="tooltip"></div>

<script>
const DATA   = __DATA__;
const COLORS = __COLORS__;
const AGENTS = __AGENTS__;

const PAD  = { l: 46, r: 96, t: 14, b: 32 };
const CH   = 230;  // canvas height px

function drawChart(canvas, domainData, frontAgent = null) {
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 340;
  canvas.width  = W * dpr;
  canvas.height = CH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const pw = W   - PAD.l - PAD.r;
  const ph = CH  - PAD.t - PAD.b;

  // Compute x range
  let maxIdx = 1;
  for (const a of Object.keys(domainData)) {
    const pts = domainData[a].points;
    if (pts.length > 0) maxIdx = Math.max(maxIdx, pts[pts.length - 1].idx);
  }

  const xScale = i => PAD.l + (i / maxIdx) * pw;
  const yScale = w => PAD.t + (1.0 - w) * ph;

  // Background
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, CH);

  // Horizontal grid + y-axis labels
  [0, 0.25, 0.5, 0.75, 1.0].forEach(y => {
    const py = yScale(y);
    ctx.strokeStyle = y === 0.5 ? "#334155" : "#1e3a5f";
    ctx.lineWidth   = y === 0.5 ? 1 : 0.8;
    ctx.beginPath(); ctx.moveTo(PAD.l, py); ctx.lineTo(PAD.l + pw, py); ctx.stroke();
    ctx.fillStyle   = "#475569";
    ctx.font        = "10px monospace";
    ctx.textAlign   = "right";
    ctx.fillText(y.toFixed(2), PAD.l - 6, py + 3.5);
  });

  // ω = 0.5: the untested-agent prior (dashed red). Not an inversion threshold —
  // engine.sprt_update adds ω × LLR, so a low ω shrinks a vote, never flips it.
  const y05 = yScale(0.5);
  ctx.strokeStyle = "#ef4444";
  ctx.lineWidth   = 1.2;
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(PAD.l, y05); ctx.lineTo(PAD.l + pw, y05); ctx.stroke();
  ctx.setLineDash([]);

  // Axes
  ctx.strokeStyle = "#334155";
  ctx.lineWidth   = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t);
  ctx.lineTo(PAD.l, PAD.t + ph);
  ctx.lineTo(PAD.l + pw, PAD.t + ph);
  ctx.stroke();

  // X-axis ticks
  const step = maxIdx <= 8 ? 1 : maxIdx <= 20 ? 2 : 5;
  for (let i = 0; i <= maxIdx; i += step) {
    const px = xScale(i);
    ctx.fillStyle   = "#475569";
    ctx.font        = "10px monospace";
    ctx.textAlign   = "center";
    ctx.fillText(i, px, PAD.t + ph + 16);
  }
  ctx.fillStyle   = "#475569";
  ctx.font        = "10px sans-serif";
  ctx.textAlign   = "center";
  ctx.fillText("oracle updates →", PAD.l + pw / 2, CH - 2);

  // Collect hit targets for tooltip
  const hits = [];

  // Sort agents by final omega descending for label placement
  // Draw order is z-order on a canvas: last drawn wins where lines overlap.
  // Two agents with an identical run of correct/wrong calls sit on the exact
  // same pixels — bringing one "to front" is the only way to see it then.
  let agentList = AGENTS.filter(a => a in domainData);
  if (frontAgent && agentList.includes(frontAgent)) {
    agentList = [...agentList.filter(a => a !== frontAgent), frontAgent];
  }

  agentList.forEach(agent => {
    const series = domainData[agent];
    const color  = COLORS[agent] || "#94a3b8";
    const isFront = agent === frontAgent;
    // Build full point list: [init point] + oracle updates
    const allPts = [{ idx: 0, omega: series.init, correct: null }, ...series.points];

    // Draw line. The front agent also gets a dark halo stroked underneath, so
    // it reads as "brought forward" even on a stretch where no line hides it.
    const tracePath = () => {
      ctx.beginPath();
      allPts.forEach((p, i) => {
        const px = xScale(p.idx), py = yScale(p.omega);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
    };
    if (isFront) {
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth   = 6;
      ctx.lineJoin    = "round";
      tracePath();
      ctx.stroke();
    }
    ctx.strokeStyle = color;
    ctx.lineWidth   = isFront ? 3.5 : 2.5;
    ctx.lineJoin    = "round";
    tracePath();
    ctx.stroke();

    // Draw dots
    allPts.forEach(p => {
      const px = xScale(p.idx), py = yScale(p.omega);
      const r  = p.correct === false ? 5 : 4;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      if (p.correct === null) {
        // hollow: initial weight marker
        ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        ctx.fillStyle   = "#1e293b";
        ctx.fill(); ctx.stroke();
      } else if (p.correct) {
        ctx.fillStyle = color;
        ctx.fill();
      } else {
        // wrong prediction: hollow with red ring
        ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 2;
        ctx.fillStyle   = "#1e293b";
        ctx.fill(); ctx.stroke();
      }
      hits.push({ px, py, agent, omega: p.omega, correct: p.correct, idx: p.idx });
    });

    // Direct label at end of line — a dark halo behind the front agent's
    // label too, so it wins legibility even where another label sits right
    // on top of it (that overlap is what made AUDITOR disappear in the
    // first place: identical end points, later-drawn label wins outright).
    const last  = allPts[allPts.length - 1];
    const label = agent === "TEST-FOCUSED" ? "T-FOCUSED" : agent;
    const lx    = PAD.l + pw + 6, ly = yScale(last.omega) + 3.5;
    ctx.font      = isFront ? "bold 11.5px sans-serif" : "bold 10.5px sans-serif";
    ctx.textAlign = "left";
    if (isFront) {
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth   = 3;
      ctx.lineJoin    = "round";
      ctx.strokeText(label, lx, ly);
    }
    ctx.fillStyle = color;
    ctx.fillText(label, lx, ly);
  });

  return hits;
}

const grid    = document.getElementById("grid");
const tooltip = document.getElementById("tooltip");

Object.entries(DATA).forEach(([domain, domainData]) => {
  const card = document.createElement("div");
  card.className = "domain-card";

  const title = document.createElement("div");
  title.className = "domain-title";
  title.textContent = domain;
  card.appendChild(title);

  const canvas = document.createElement("canvas");
  canvas.height = CH;
  card.appendChild(canvas);

  // Legend — click an agent to bring its line and label to the front. Two
  // agents with the same correct/wrong history at every point sit on
  // identical pixels (that's how AUDITOR went missing under ADVOCATE in
  // PERFORMANCE); the later-drawn one always wins, so this is the only way
  // to see the hidden one. Click the same agent again to go back to normal.
  const legend    = document.createElement("div");
  legend.className = "legend";
  const domainAgents = AGENTS.filter(a => a in domainData);
  const legendItems  = {};
  domainAgents.forEach(agent => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML  = `<div class="legend-swatch" style="background:${COLORS[agent] || '#aaa'}"></div>${agent}`;
    item.title      = "Click to bring this agent's line to the front";
    legend.appendChild(item);
    legendItems[agent] = item;
  });
  card.appendChild(legend);

  if (domainAgents.length > 1) {
    const hint = document.createElement("div");
    hint.className   = "legend-hint";
    hint.textContent = "Lines can overlap exactly — click a name above to bring it to the front.";
    card.appendChild(hint);
  }

  grid.appendChild(card);

  requestAnimationFrame(() => {
    let hits = [];
    let front = null;

    function redraw() {
      hits = drawChart(canvas, domainData, front);
      domainAgents.forEach(a => legendItems[a].classList.toggle("front", a === front));
    }
    redraw();

    domainAgents.forEach(agent => {
      legendItems[agent].addEventListener("click", () => {
        front = (front === agent) ? null : agent;
        redraw();
      });
    });

    canvas.addEventListener("mousemove", e => {
      const rect = canvas.getBoundingClientRect();
      const mx   = (e.clientX - rect.left) * (canvas.offsetWidth  / rect.width);
      const my   = (e.clientY - rect.top)  * (canvas.offsetHeight / rect.height);
      let best = null, bestD = 22;
      hits.forEach(h => {
        const d = Math.hypot(h.px - mx, h.py - my);
        if (d < bestD) { bestD = d; best = h; }
      });
      if (best) {
        const status = best.correct === null ? "initial weight"
                     : best.correct ? "✓ correct" : "✗ wrong";
        tooltip.style.display = "block";
        tooltip.style.left    = (e.clientX + 14) + "px";
        tooltip.style.top     = (e.clientY - 36) + "px";
        tooltip.innerHTML     =
          `<b style="color:${COLORS[best.agent]}">${best.agent}</b><br>` +
          `ω = ${best.omega.toFixed(4)}&ensp;·&ensp;update #${best.idx}<br>` +
          `${status}`;
      } else {
        tooltip.style.display = "none";
      }
    });
    canvas.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
  });
});
</script>
</body>
</html>
"""


def main() -> None:
    data = extract(SESSIONS)
    if not data:
        print("No oracle sessions found in", SESSIONS)
        return

    html = (_TEMPLATE
            .replace("__DATA__",   json.dumps(data))
            .replace("__COLORS__", json.dumps(COLORS))
            .replace("__AGENTS__", json.dumps(AGENTS)))
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")

    open_in_browser(OUTPUT)


if __name__ == "__main__":
    main()
