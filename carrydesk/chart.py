"""The carry-spread chart — server-rendered inline SVG, no JS, no dependencies.

The archive is the product's only real moat, and as a table of numbers it is
accurate but unpersuasive. This turns it into a line anyone can read in a second,
and it improves on its own every hour.

Two series on purpose. The mean is what an equal-weighted book earns; the median
is what survives when one illiquid coin funding at +200%/yr is removed. The *gap
between them* is the honest part, and plotting only the flattering line would
undo the reason anyone should trust the rest.

Design constraints, in priority order:
  1. No JavaScript and no external requests — the page must render when
     everything else is broken. Hover uses SVG's native <title>, which every
     browser shows as a tooltip with zero script.
  2. Colors are the validated categorical slots 1 and 2 (blue / orange), checked
     with the palette validator against both the light and dark page surfaces:
     lightness band, chroma floor, CVD separation, normal-vision floor and
     contrast all pass. Do not substitute by eye.
  3. Thin marks, solid hairline grid one shade off the surface, and labels only
     at the endpoints — a number on every point is unreadable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

# Categorical slots 1 and 2 from the validated reference palette.
# light/dark are separately stepped for their own surface, not an auto-flip.
SERIES = {
    "mean": {"light": "#2a78d6", "dark": "#3987e5", "label": "mean"},
    "median": {"light": "#eb6834", "dark": "#d95926", "label": "median"},
}

W, H = 760, 210          # plot box
PAD_L, PAD_R = 46, 62    # right pad holds the endpoint labels
PAD_T, PAD_B = 14, 26    # bottom pad is the x-axis band, inside the viewBox


def _nice_step(span: float) -> float:
    """A round gridline interval — 1/2/5 × 10^n covering ~4 lines."""
    if span <= 0:
        return 0.05
    raw = span / 4
    import math

    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def render_chart(series: list[dict], mode_css_var: str = "--chart-ink") -> str:
    """Inline SVG for the spread history. Returns '' when there is nothing to plot."""
    pts = [r for r in series if r.get("mean") is not None]
    if len(pts) < 2:
        return (
            '<p class="dim">The chart appears once at least two snapshots have '
            "been published. It fills in hourly.</p>"
        )

    xs = [r["ts"] for r in pts]
    vals = [r["mean"] for r in pts] + [r["median"] for r in pts if r.get("median") is not None]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi, lo = hi + 0.01, lo - 0.01
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad
    # Always show zero: a carry spread crossing into negative is the single most
    # important thing this chart can show, and hiding the axis would mask it.
    lo, hi = min(lo, 0.0), max(hi, 0.0)

    x0, x1 = min(xs), max(xs)
    span = (x1 - x0) or 1

    def px(ts):
        return PAD_L + (ts - x0) / span * (W - PAD_L - PAD_R)

    def py(v):
        return PAD_T + (hi - v) / (hi - lo) * (H - PAD_T - PAD_B)

    # --- grid + y ticks ---
    step = _nice_step(hi - lo)
    import math

    grid, first = [], math.ceil(lo / step) * step
    t = first
    while t <= hi + 1e-9:
        y = py(t)
        is_zero = abs(t) < 1e-9
        grid.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'class="{"zero" if is_zero else "grid"}"/>'
            f'<text x="{PAD_L - 8}" y="{y + 3.5:.1f}" class="tick" text-anchor="end">'
            f"{100 * t:.0f}%</text>"
        )
        t += step

    # --- x labels: first and last only, plus a midpoint when the span is wide ---
    # Format follows the span. Early on the archive covers hours, and two
    # identical "Aug 02" labels tell the reader nothing; past a couple of days
    # the clock time is the noise instead.
    def daylabel(ts):
        d = datetime.fromtimestamp(ts, tz=timezone.utc)
        if span < 2 * 86400:
            return d.strftime("%b %d %H:%M")
        return d.strftime("%b %d")

    xlab = [(x0, "start"), (x1, "end")]
    if (x1 - x0) > 3 * 86400:
        xlab.insert(1, ((x0 + x1) // 2, "middle"))
    xaxis = "".join(
        f'<text x="{px(ts):.1f}" y="{H - 6}" class="tick" text-anchor="{anchor}">'
        f"{daylabel(ts)}</text>"
        for ts, anchor in xlab
    )

    # --- series paths ---
    body = []
    for key in ("mean", "median"):
        got = [(r["ts"], r[key]) for r in pts if r.get(key) is not None]
        if len(got) < 2:
            continue
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{px(ts):.1f},{py(v):.1f}"
            for i, (ts, v) in enumerate(got)
        )
        body.append(f'<path d="{d}" class="s-{key}"/>')
        # Endpoint marker + direct label. Labelling only the endpoint keeps the
        # identity attached to the line without a number on every point.
        lts, lv = got[-1]
        body.append(
            f'<circle cx="{px(lts):.1f}" cy="{py(lv):.1f}" r="4" class="dot d-{key}"/>'
            f'<text x="{px(lts) + 10:.1f}" y="{py(lv) + 4:.1f}" class="lab l-{key}">'
            f"{100 * lv:+.1f}%</text>"
        )

    # --- hover targets: native SVG <title>, no script ---
    hover = []
    bw = max(4.0, (W - PAD_L - PAD_R) / max(len(pts), 1))
    for r in pts:
        med = f"{100 * r['median']:+.1f}%" if r.get("median") is not None else "n/a"
        tip = f"{escape(str(r['as_of'])[:16])} · mean {100 * r['mean']:+.1f}% · median {med}"
        hover.append(
            f'<rect x="{px(r["ts"]) - bw / 2:.1f}" y="{PAD_T}" width="{bw:.1f}" '
            f'height="{H - PAD_T - PAD_B}" class="hit"><title>{tip}</title></rect>'
        )

    legend = (
        '<div class="legend">'
        + "".join(
            f'<span class="key"><i class="sw sw-{k}"></i>{v["label"]}</span>'
            for k, v in SERIES.items()
        )
        + "</div>"
    )

    return f"""{legend}
<svg viewBox="0 0 {W} {H}" class="chart" role="img"
     aria-label="Annualized carry spread over time, mean and median, from {daylabel(x0)} to {daylabel(x1)}.">
  {''.join(grid)}
  {xaxis}
  {''.join(body)}
  {''.join(hover)}
</svg>"""


CHART_CSS = """
.legend{display:flex;gap:16px;margin:0 0 6px;font-size:12.5px;color:var(--dim)}
.legend .key{display:inline-flex;align-items:center;gap:6px}
.sw{width:11px;height:2.5px;border-radius:2px;display:inline-block}
.sw-mean{background:#2a78d6}.sw-median{background:#eb6834}
.chart{width:100%;height:auto;display:block;overflow:visible}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .zero{stroke:var(--dim);stroke-width:1;opacity:.55}
.chart .tick{fill:var(--dim);font-size:10.5px;font-variant-numeric:tabular-nums}
.chart path{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .s-mean{stroke:#2a78d6}.chart .s-median{stroke:#eb6834}
.chart .dot{stroke:var(--bg);stroke-width:2}
.chart .d-mean{fill:#2a78d6}.chart .d-median{fill:#eb6834}
.chart .lab{font-size:11.5px;font-weight:600;font-variant-numeric:tabular-nums}
.chart .l-mean{fill:#2a78d6}.chart .l-median{fill:#eb6834}
.chart .hit{fill:transparent}
.chart .hit:hover{fill:var(--dim);opacity:.07}
@media (prefers-color-scheme:dark){
  .sw-mean{background:#3987e5}.sw-median{background:#d95926}
  .chart .s-mean{stroke:#3987e5}.chart .s-median{stroke:#d95926}
  .chart .d-mean{fill:#3987e5}.chart .d-median{fill:#d95926}
  .chart .l-mean{fill:#3987e5}.chart .l-median{fill:#d95926}
}
"""
