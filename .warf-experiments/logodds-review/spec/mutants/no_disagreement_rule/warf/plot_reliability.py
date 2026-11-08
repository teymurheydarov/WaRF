"""
Generate reliability_diagram.html — accuracy by confidence band.
Run:  py warf/plot_reliability.py
"""
import json
from pathlib import Path

if __package__ in (None, ""):  # run as `py warf/plot_reliability.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
from .paths import sessions_path, html_dir, open_in_browser  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "confidence_calibration.html"

BAND_ORDER  = ["LOW", "MEDIUM", "HIGH"]
BAND_COLOR  = {"LOW": "#ef4444", "MEDIUM": "#f59e0b", "HIGH": "#22c55e"}
BAND_DARK   = {"LOW": "#7f1d1d", "MEDIUM": "#78350f", "HIGH": "#14532d"}


def extract(path: Path) -> dict:
    """Return {band: {correct: int, total: int}} from oracle-labelled sessions."""
    bands = {b: {"correct": 0, "total": 0} for b in BAND_ORDER}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            if not s.get("oracle"):
                continue
            conf   = s.get("confidence", "?")
            if conf not in bands:
                continue
            dec    = s.get("decision", "?")
            x_star = s["oracle"].get("x_star", 0)
            vote   = 1 if dec == "APPROVE" else -1
            correct = vote == x_star
            bands[conf]["total"]   += 1
            bands[conf]["correct"] += int(correct)
    return bands


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF — Confidence Calibration</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #e2e8f0;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding: 28px 32px 48px;
}
h1 { font-size: 1.35rem; font-weight: 600; color: #c8d8f4; margin-bottom: 6px; }
.subtitle { font-size: 0.82rem; color: #64748b; margin-bottom: 8px; line-height: 1.6; }
.provenance {
  font-size: 0.72rem; color: #334155; background: #1e293b;
  border-left: 3px solid #334155; padding: 6px 12px;
  margin-bottom: 24px; border-radius: 0 4px 4px 0;
  font-family: "Consolas", monospace; letter-spacing: 0.01em;
}
.charts { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
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
  color: #e2e8f0;
}
</style>
</head>
<body>
<h1>Does WaRF Know When It's Right?</h1>
<div class="subtitle">
  Confidence calibration by band — accuracy against developer ground truth.<br>
  Dashed line = random baseline (50%). n = oracle-labelled sessions per band.
</div>
<div class="provenance">
  Historical oracle-labelled sessions only &nbsp;·&nbsp; live demo excluded
  &nbsp;·&nbsp; <span id="n-total"></span> sessions total
  &nbsp;·&nbsp; preliminary calibration evidence, not definitive generalisation
</div>

<div class="charts">
  <div class="chart-card">
    <div class="chart-title">Confidence calibration</div>
    <canvas id="acc" height="300"></canvas>
  </div>
  <div class="chart-card">
    <div class="chart-title">Session coverage</div>
    <canvas id="cov" height="300"></canvas>
  </div>
</div>
<div id="tooltip"></div>

<script>
const BANDS  = __BANDS__;
const COLORS = __COLORS__;
const DARKS  = __DARKS__;
const ORDER  = __ORDER__;

const nTotal = ORDER.reduce((s, b) => s + BANDS[b].total, 0);
document.getElementById("n-total").textContent = `n = ${nTotal}`;

const PAD  = { l: 52, r: 20, t: 20, b: 48 };
const tooltip = document.getElementById("tooltip");

// ── Accuracy chart ────────────────────────────────────────────────────────────
(function drawAcc() {
  const canvas = document.getElementById("acc");
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 380;
  const H   = 300;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;
  const n  = ORDER.length;
  const bw = Math.min(70, (pw / n) * 0.55);
  const gap = pw / n;

  const yS = v => PAD.t + (1 - v) * ph;
  const cx = i => PAD.l + gap * i + gap / 2;

  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, H);

  // Y grid
  [0, 0.25, 0.5, 0.75, 1].forEach(f => {
    const py = yS(f);
    ctx.strokeStyle = f === 0.5 ? "#334155" : "#1e3a5f";
    ctx.lineWidth   = f === 0.5 ? 1.2 : 0.8;
    ctx.beginPath(); ctx.moveTo(PAD.l, py); ctx.lineTo(PAD.l + pw, py); ctx.stroke();
    ctx.fillStyle = "#475569"; ctx.font = "10px monospace"; ctx.textAlign = "right";
    ctx.fillText((f * 100).toFixed(0) + "%", PAD.l - 5, py + 3.5);
  });

  // Random baseline label
  ctx.fillStyle = "#475569"; ctx.font = "9px sans-serif"; ctx.textAlign = "left";
  ctx.fillText("random", PAD.l + pw + 2, yS(0.5) + 3.5);

  // 50% dashed line
  ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 1.2;
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(PAD.l, yS(0.5)); ctx.lineTo(PAD.l + pw, yS(0.5)); ctx.stroke();
  ctx.setLineDash([]);

  // Axes
  ctx.strokeStyle = "#334155"; ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t); ctx.lineTo(PAD.l, PAD.t + ph); ctx.lineTo(PAD.l + pw, PAD.t + ph);
  ctx.stroke();

  const hits = [];
  ORDER.forEach((band, i) => {
    const { correct, total } = BANDS[band];
    const acc  = total > 0 ? correct / total : 0;
    const yTop = yS(acc);
    const yBot = yS(0);
    const hh   = yBot - yTop;
    const x    = cx(i);
    const color = COLORS[band];
    const dark  = DARKS[band];

    const grad = ctx.createLinearGradient(0, yTop, 0, yBot);
    grad.addColorStop(0, color);
    grad.addColorStop(1, dark);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x - bw / 2, yTop, bw, hh, [4, 4, 0, 0]);
    ctx.fill();

    // Accuracy label
    ctx.fillStyle = "#e2e8f0"; ctx.font = "bold 12px sans-serif"; ctx.textAlign = "center";
    ctx.fillText((acc * 100).toFixed(0) + "%", x, yTop - 6);

    // X label
    ctx.fillStyle = "#94a3b8"; ctx.font = "11px sans-serif";
    ctx.fillText(band, x, PAD.t + ph + 16);
    ctx.fillStyle = "#475569"; ctx.font = "9px sans-serif";
    ctx.fillText(`n=${total}`, x, PAD.t + ph + 30);

    hits.push({ x, yTop, yBot, bw, band, acc, correct, total });
  });

  // Y label
  ctx.save();
  ctx.translate(12, PAD.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#475569"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("accuracy against developer ground truth", 0, 0);
  ctx.restore();

  canvas.addEventListener("mousemove", e => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let best = null;
    hits.forEach(h => {
      if (mx >= h.x - h.bw/2 - 4 && mx <= h.x + h.bw/2 + 4 && my >= h.yTop - 4 && my <= h.yBot + 4)
        best = h;
    });
    if (best) {
      tooltip.style.display = "block";
      tooltip.style.left    = (e.clientX + 14) + "px";
      tooltip.style.top     = (e.clientY - 40) + "px";
      tooltip.innerHTML =
        `<b style="color:${COLORS[best.band]}">${best.band}</b><br>` +
        `Correct: ${best.correct} / ${best.total}<br>` +
        `Accuracy: ${(best.acc * 100).toFixed(1)}%`;
    } else {
      tooltip.style.display = "none";
    }
  });
  canvas.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
})();

// ── Coverage chart ────────────────────────────────────────────────────────────
(function drawCov() {
  const canvas = document.getElementById("cov");
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 380;
  const H   = 300;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const total = ORDER.reduce((s, b) => s + BANDS[b].total, 0);
  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;
  const n  = ORDER.length;
  const bw = Math.min(70, (pw / n) * 0.55);
  const gap = pw / n;
  const maxN = Math.max(...ORDER.map(b => BANDS[b].total));

  const yS = v => PAD.t + (1 - v / (maxN * 1.15)) * ph;
  const cx = i => PAD.l + gap * i + gap / 2;

  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, H);

  [0, 0.25, 0.5, 0.75, 1].forEach(f => {
    const v  = f * maxN * 1.15;
    const py = yS(v);
    ctx.strokeStyle = "#1e3a5f"; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(PAD.l, py); ctx.lineTo(PAD.l + pw, py); ctx.stroke();
    ctx.fillStyle = "#475569"; ctx.font = "10px monospace"; ctx.textAlign = "right";
    ctx.fillText(Math.round(v), PAD.l - 5, py + 3.5);
  });

  ctx.strokeStyle = "#334155"; ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t); ctx.lineTo(PAD.l, PAD.t + ph); ctx.lineTo(PAD.l + pw, PAD.t + ph);
  ctx.stroke();

  ORDER.forEach((band, i) => {
    const { total: cnt } = BANDS[band];
    const pct   = total > 0 ? cnt / total : 0;
    const yTop  = yS(cnt);
    const yBot  = yS(0);
    const hh    = yBot - yTop;
    const x     = cx(i);
    const color = COLORS[band];
    const dark  = DARKS[band];

    const grad = ctx.createLinearGradient(0, yTop, 0, yBot);
    grad.addColorStop(0, color);
    grad.addColorStop(1, dark);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x - bw / 2, yTop, bw, hh, [4, 4, 0, 0]);
    ctx.fill();

    ctx.fillStyle = "#e2e8f0"; ctx.font = "bold 12px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(`${cnt}`, x, yTop - 6);
    ctx.fillStyle = "#64748b"; ctx.font = "9px sans-serif";
    ctx.fillText(`(${(pct * 100).toFixed(0)}%)`, x, yTop - 18);

    ctx.fillStyle = "#94a3b8"; ctx.font = "11px sans-serif";
    ctx.fillText(band, x, PAD.t + ph + 16);
  });

  ctx.save();
  ctx.translate(12, PAD.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#475569"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("oracle-labelled sessions", 0, 0);
  ctx.restore();
})();
</script>
</body>
</html>
"""


def main() -> None:
    bands = extract(SESSIONS)
    total = sum(b["total"] for b in bands.values())
    if total == 0:
        print("No oracle-labelled sessions found.")
        return

    for band, d in bands.items():
        acc = d["correct"] / d["total"] if d["total"] else 0
        print(f"  {band:<7} n={d['total']:>3}  accuracy={acc:.2f}")

    html = (_TEMPLATE
            .replace("__BANDS__",  json.dumps(bands))
            .replace("__COLORS__", json.dumps(BAND_COLOR))
            .replace("__DARKS__",  json.dumps(BAND_DARK))
            .replace("__ORDER__",  json.dumps(BAND_ORDER)))
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"\nWritten: {OUTPUT}")

    open_in_browser(OUTPUT)


if __name__ == "__main__":
    main()
