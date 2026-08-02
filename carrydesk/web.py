"""The public page — the funnel.

Server-rendered from the same snapshot the API serves. No JS, no build step, no
external requests: it must keep working when everything else is having a bad day,
because it is the thing people see first.

Deliberately shows the numbers that make us look worse (trimmed and median
spread, the outlier flag) next to the headline. That contrast IS the pitch:
anyone can compute a funding mean, publishing the caveat is what earns trust.
"""
from __future__ import annotations

from html import escape

from . import config as C


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:+.1f}%"


def _vol(x: float) -> str:
    return f"${x / 1e6:.1f}m" if x >= 1e6 else f"${x / 1e3:.0f}k"


CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--dim:#6b6b66;--line:#e4e4e0;--card:#fff;
--pos:#0a7c4a;--neg:#b4341f;--accent:#1a1a19}
@media (prefers-color-scheme:dark){:root{--bg:#111110;--fg:#e8e8e4;--dim:#8a8a83;
--line:#2a2a27;--card:#1a1a18;--pos:#4ade80;--neg:#f87171;--accent:#e8e8e4}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:48px 20px 80px}
h1{font-size:26px;letter-spacing:-.02em;margin:0 0 6px;font-weight:650}
.sub{color:var(--dim);margin:0 0 36px;font-size:14px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);
margin:40px 0 14px;font-weight:600}
.head{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.stat .v{font-size:22px;font-weight:640;letter-spacing:-.02em;margin-top:3px;
font-variant-numeric:tabular-nums}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--neg);
border-radius:8px;padding:12px 15px;margin:14px 0;font-size:13.5px;color:var(--dim)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:28px}
@media(max-width:620px){.cols{grid-template-columns:1fr;gap:8px}}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
color:var(--dim);font-weight:600;padding:0 0 8px;border-bottom:1px solid var(--line)}
td{padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.coin{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13.5px}
.pos{color:var(--pos)}.neg{color:var(--neg)}.dim{color:var(--dim);font-size:13px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;
background:var(--card);border:1px solid var(--line);border-radius:5px;padding:1.5px 5px}
pre{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:14px 16px;overflow-x:auto;font-size:13px;line-height:1.5}
pre code{background:none;border:none;padding:0}
a{color:var(--accent);text-underline-offset:2px}
.foot{margin-top:52px;padding-top:22px;border-top:1px solid var(--line);
color:var(--dim);font-size:13px}
.foot p{margin:0 0 8px}
"""


def _rows(items: list[dict], side: str) -> str:
    out = []
    for r in items:
        cls = "neg" if r["mean_funding_annualized"] < 0 else "pos"
        out.append(
            f'<tr><td class="coin">{escape(r["coin"])}</td>'
            f'<td class="n {cls}">{_pct(r["mean_funding_annualized"])}</td>'
            f'<td class="n dim">{_vol(r["day_notional_volume"])}</td></tr>'
        )
    return (
        f'<div><h2>{side}</h2><table><tr><th>coin</th>'
        f'<th style="text-align:right">14d funding</th>'
        f'<th style="text-align:right">volume/day</th></tr>'
        + "".join(out)
        + "</table></div>"
    )


def render_archive(index: list[dict], totals: dict) -> str:
    """Every snapshot day ever published. The proof, made browsable.

    A JSONL file in a repo is evidence; a page anyone can open is persuasion.
    Same data either way.
    """
    rows = []
    for d in index:
        flag = (
            ' <span class="dim">(outlier-dominated)</span>'
            if d.get("outlier_dominated")
            else ""
        )
        rows.append(
            f'<tr><td class="coin">{escape(d["day"])}</td>'
            f'<td class="n">{d["snapshots"]}</td>'
            f'<td class="n">{d.get("universe_size") or "—"}</td>'
            f'<td class="n">{_pct(d.get("carry_spread_annualized"))}</td>'
            f'<td class="n">{_pct(d.get("carry_spread_annualized_median"))}{flag}</td></tr>'
        )
    body = "".join(rows) or '<tr><td colspan="5" class="dim">No snapshots yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>carrydesk — published archive</title>
<meta name="description" content="Every funding-carry snapshot carrydesk has published, timestamped and never edited.">
<style>{CSS}</style></head><body><div class="wrap">
<h1>Published archive</h1>
<p class="sub"><strong>{totals.get("snapshots", 0)}</strong> snapshots across
<strong>{totals.get("days", 0)}</strong> day(s), appended hourly and never edited.
Each row shows that day's final reading.</p>

<table><tr><th>day</th>
<th style="text-align:right">snapshots</th>
<th style="text-align:right">universe</th>
<th style="text-align:right">spread (mean)</th>
<th style="text-align:right">spread (median)</th></tr>
{body}</table>

<h2>Why this page exists</h2>
<p>Anyone can publish a number today and claim it was right yesterday. The only
thing that distinguishes a real signal from a backfitted one is a record written
<em>in advance</em> and never touched afterwards. That is what this is: every
snapshot, appended as it was computed, mirrored to a
<a href="https://github.com/pelazas/carrydesk">public git repository</a> where the
commit history is independently checkable.</p>

<p>It is also why the median column sits next to the mean. When they diverge, one
or two illiquid names are carrying the headline — and hiding that would make
every other number here worth less.</p>

<div class="foot">
<p><a href="{C.PUBLIC_URL}/">← today's ranking</a> &middot;
<a href="{C.PUBLIC_URL}/v1/method">method</a> &middot;
<a href="https://github.com/pelazas/carrydesk">source</a></p>
<p><strong>Informational only. Not investment advice.</strong></p>
</div>
</div></body></html>"""


def render(snap: dict, delayed: bool, archived_days: int, json_ld: str = "") -> str:
    """Render the public page from a free-tier snapshot."""
    as_of = escape(str(snap.get("as_of", "unknown")))
    n = snap.get("universe_size", 0)
    lookback = snap.get("method", {}).get("lookback_hours", 336) // 24

    outlier = ""
    if snap.get("outlier_dominated"):
        outlier = (
            '<div class="note"><strong>Outlier-dominated today.</strong> One or two '
            "illiquid names carry most of the headline spread. The median is the "
            "number to trust.</div>"
        )

    freshness = (
        f"Delayed {C.FREE_TIER_DELAY_HOURS}h." if delayed else "Live (no delayed snapshot yet)."
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>carrydesk — Hyperliquid funding carry</title>
<meta name="description" content="Cross-sectional funding-carry rankings for Hyperliquid perpetuals, published daily and sold per call in USDC.">
<link rel="alternate" type="text/plain" href="/llms.txt" title="LLM-readable summary">
<script type="application/ld+json">{json_ld}</script>
<style>{CSS}</style></head><body><div class="wrap">

<h1>Hyperliquid funding carry</h1>
<p class="sub">Cross-sectional ranking of {n} liquid perps by trailing {lookback}-day mean
funding &middot; {as_of} &middot; {freshness}</p>

<div class="head">
  <div class="stat"><div class="k">spread (mean)</div>
    <div class="v">{_pct(snap.get("carry_spread_annualized"))}</div></div>
  <div class="stat"><div class="k">trimmed</div>
    <div class="v">{_pct(snap.get("carry_spread_annualized_trimmed"))}</div></div>
  <div class="stat"><div class="k">median</div>
    <div class="v">{_pct(snap.get("carry_spread_annualized_median"))}</div></div>
</div>
{outlier}

<div class="cols">
{_rows(snap.get("longs", []), "Long leg &middot; paid to hold")}
{_rows(snap.get("shorts", []), "Short leg &middot; paid to short")}
</div>

<h2>What this is</h2>
<p>Perps charge funding hourly between longs and shorts. Rank the liquid universe by
trailing mean funding, go long the most negative and short the most positive,
dollar-neutral, and you collect the spread between the legs. It is a
<strong>structural risk premium</strong> &mdash; compensation for absorbing crowded
leverage &mdash; not a prediction. It can and does go negative.</p>

<p>Three spread numbers, always. The mean is what an equal-weighted book earns; the
trimmed and median readings tell you whether one illiquid name is carrying it.
Published in advance, every hour, and never edited &mdash;
<a href="{C.PUBLIC_URL}/archive"><strong>{archived_days} day(s)</strong> archived so far</a>.</p>

<h2>API</h2>
<pre><code>curl {C.PUBLIC_URL}/v1/free/carry     # free, delayed, top 5 each leg
curl {C.PUBLIC_URL}/v1/carry/rankings # {C.PRICE_RANKINGS} USDC, full live ranking</code></pre>
<p class="dim">Paid endpoints are metered with <a href="https://x402.org">x402</a>: your
client gets a 402, pays USDC on Base, retries, gets data. No account, no API key.
Full docs at <a href="{C.PUBLIC_URL}/docs">/docs</a>, method at
<a href="{C.PUBLIC_URL}/v1/method">/v1/method</a>.</p>

<h2>Use it from an agent</h2>
<pre><code>claude mcp add carrydesk -- uvx --from git+https://github.com/pelazas/carrydesk carrydesk-mcp</code></pre>
<p class="dim">One command. No clone, no virtualenv &mdash; <code>uvx</code> fetches and runs it.
Six tools; the free ones work with no wallet configured.</p>

<div class="foot">
<p>Gross of fees, slippage and borrow. Taker fees alone can erase this edge.
Funding data is Hyperliquid's own, with no cross-venue reconciliation.</p>
<p><strong>Informational only. Not investment advice.</strong></p>
<p><a href="https://github.com/pelazas/carrydesk">source</a></p>
</div>
</div></body></html>"""
