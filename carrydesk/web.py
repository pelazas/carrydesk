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
from .chart import CHART_CSS, render_chart


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
/* The hero carries the whole page. Big, plain, no gradient, no motion --
   the product is credibility, and anything that looks like a crypto landing
   page makes the honest median number read as marketing too. */
h1.hero{font-size:40px;line-height:1.12;letter-spacing:-.03em;font-weight:680;
margin:0 0 18px;max-width:16em}
@media(max-width:620px){h1.hero{font-size:30px}}
.lede{font-size:18px;line-height:1.55;margin:0 0 14px;max-width:34em}
.lede .big{font-size:22px;font-weight:660;letter-spacing:-.02em;
font-variant-numeric:tabular-nums;white-space:nowrap}
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
table.bt td:first-child{width:52%}
table.bt td{font-size:14px}
ul{margin:0 0 14px;padding-left:20px}
li{margin:0 0 7px}
""" + CHART_CSS


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


def render_archive(index: list[dict], totals: dict, series: list[dict] | None = None) -> str:
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
    chartblock = render_chart(series or [])
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

<h2>Carry spread over time</h2>
{chartblock}

<h2>By day</h2>
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


# Every figure here comes from a real 6.89-year backtest of this signal
# (systematic-trading/10-live/RESULTS.md): 40 Binance USDⓈ-M perps,
# 2019-09-10 → 2026-07-31, 7,550 8h bars, maker fills, costs modelled.
# Config: lookback=21, rebal=9, k=12, equal weight, dollar-neutral.
#
# Nothing here is invented or extrapolated beyond what that document states.
# The out-of-sample column leads because the full-sample number flatters, and
# every return sits next to the drawdown that produced it. This is a backtest
# of the strategy, NOT carrydesk's performance and NOT a live track record --
# said plainly in the copy, because a reader who confuses the two has been
# misled whether or not the numbers are accurate.
BACKTEST = """
<h2>What this signal did over 6.9 years</h2>
<p>The ranking above is the input to a dollar-neutral book. Here is how that book
backtested &mdash; <strong>40 Binance perpetuals, September 2019 to July 2026</strong>,
7,550 eight-hour bars, maker fills, costs modelled, rebalanced every 9 bars across
12 coins a side.</p>
<p class="dim"><strong>These are simulated results for the strategy, not carrydesk's own
performance and not a live trading record.</strong> Nobody's money was at risk in
producing them.</p>

<table class="bt"><tr><th></th>
<th style="text-align:right">gross 1.0</th>
<th style="text-align:right">gross 2.0</th></tr>
<tr><td>Annual return <span class="dim">(out-of-sample)</span></td>
    <td class="n">+14.4%</td><td class="n">+28.8%</td></tr>
<tr><td>Annual return <span class="dim">(full sample)</span></td>
    <td class="n">+18.0%</td><td class="n">+36.0%</td></tr>
<tr><td>Sharpe</td><td class="n">1.11</td><td class="n">1.11</td></tr>
<tr><td>Max drawdown</td><td class="n neg">&minus;20.6%</td>
    <td class="n neg">&minus;37.7%</td></tr>
<tr><td>Volatility</td><td class="n">14.8%</td><td class="n">29.6%</td></tr>
</table>

<p class="dim">Leverage is the only lever available, and it improves nothing: Sharpe is
flat across every gross level because leverage scales return and drawdown identically.
Quarter-Kelly lands at 2.05&times;, which is why 2.0 is a ceiling rather than an
aggressive choice.</p>

<h2>Why you should discount it anyway</h2>
<p>A backtest is a hypothesis, not a track record. Four things are worth knowing before
you weigh this one:</p>
<ul>
<li><strong>It degraded out of sample.</strong> Train half Sharpe 1.48, test half 1.11.
A neighbouring configuration degraded far worse &mdash; 1.35 to 0.72 &mdash; which is a
fair estimate of how much of this is luck.</li>
<li><strong>Forty parameter combinations were tested.</strong> Under a zero-skill null the
expected <em>best</em> Sharpe from forty tries is about 1.20. The best observed was 1.91.
It clears the bar, but not by enough to trust any single configuration.</li>
<li><strong>2021 flattered it</strong> (+81% that year). Removing 2021 entirely moves
Sharpe 0.48 &rarr; 0.42 on the comparable config, so it is not purely a mania artifact
&mdash; but no single year should carry a thesis.</li>
<li><strong>It was validated on Binance; this page ranks Hyperliquid.</strong> Similar
universe, not identical. Live slippage beyond the modelled fee is untested.</li>
</ul>
<p class="dim">These are the numbers as computed, including the ones that argue against the
strategy. Past backtested performance says nothing reliable about future returns, and
none of this is a recommendation to trade.</p>
"""


def _honesty_block(snap: dict) -> str:
    """The section that undercuts our own headline.

    Written from the live snapshot rather than boilerplate, because naming the
    actual coin paying 199% is what makes the point land — and because when
    there is no outlier the honest thing is to say so, not to keep the warning
    up for effect.
    """
    mean = snap.get("carry_spread_annualized") or 0.0
    trimmed = snap.get("carry_spread_annualized_trimmed") or 0.0
    median = snap.get("carry_spread_annualized_median") or 0.0
    # Extreme payers on the short leg: high funding, and the reason it is high
    # is almost always that nobody can trade size in them.
    big = [r for r in snap.get("shorts", []) if (r.get("mean_funding_annualized") or 0) > 0.5]
    big.sort(key=lambda r: -(r["mean_funding_annualized"]))

    # Use the snapshot's own flag so the page and the API can never disagree
    # about whether the headline is misleading -- they did, on the same data.
    if not snap.get("outlier_dominated") or not big:
        return f"""<h2>About that number</h2>
<p>Today the three readings agree closely &mdash; mean {_pct(mean)}, trimmed
{_pct(trimmed)}, median {_pct(median)}. No single coin is carrying the headline,
which is the calmer state and not the usual one.</p>
<p>We publish all three on every response regardless, plus a flag when they
diverge. The day they disagree is the day the headline alone would mislead you.</p>"""

    clauses = [
        f'<strong>{escape(r["coin"])}</strong> is paying {_pct(r["mean_funding_annualized"])} '
        f'on {_vol(r["day_notional_volume"])} a day'
        for r in big[:2]
    ]
    names = " and ".join(clauses) if len(clauses) > 1 else clauses[0]
    return f"""<h2>Our own headline number is misleading. Here is why.</h2>
<p>That <strong>{_pct(mean)}</strong> is real arithmetic &mdash; and it is mostly one or two coins.
Right now {names}.</p>

<p>At that size you cannot put real money in without moving the price against
yourself, and the funding can flip while you are trying. Strip the extremes out
and the number is <strong>{_pct(trimmed)}</strong>. Take the middle coin instead of the
average and it is <strong>{_pct(median)}</strong>.</p>

<p>Most data vendors would print {_pct(mean)} and stop. We print all three on every
response, plus a flag when the gap gets this wide &mdash; because the first time you
size into a {_pct(big[0]["mean_funding_annualized"])} number and get hurt, nothing else
we publish would be worth reading.</p>"""


def render(snap: dict, delayed: bool, archived_days: int, json_ld: str = "",
           series: list[dict] | None = None) -> str:
    """Render the public page from a free-tier snapshot.

    Leads with the arresting true fact, not the method. "Cross-sectional ranking
    by trailing 14-day mean funding" is accurate and means nothing to anyone who
    does not already know what it means — which is everyone we need to reach.
    """
    chartblock = render_chart(series or [])
    as_of = escape(str(snap.get("as_of", "unknown")))
    n = snap.get("universe_size", 0)
    lookback = snap.get("method", {}).get("lookback_hours", 336) // 24
    median = snap.get("carry_spread_annualized_median") or 0.0

    freshness = (
        f"delayed {C.FREE_TIER_DELAY_HOURS}h" if delayed else "live"
    )

    # The headline MUST follow the sign. A carry spread goes negative -- this
    # page says so two paragraphs later -- and a fixed "somebody is paying you"
    # would be a plain falsehood on those days, while the lede beneath it said
    # the opposite. On a product whose only real asset is being trusted about
    # numbers, that is the most expensive bug available.
    if median >= 0:
        headline = "Somebody is paying you<br>to take the other side."
        lede_tail = (
            f"Right now the market is paying <span class=\"big\">{_pct(median)}</span> a year "
            "to hold a position that does not care where Bitcoin goes."
        )
    else:
        headline = "Today, taking the other side<br>costs you money."
        lede_tail = (
            f"Right now that flips: the typical coin is <span class=\"big\">{_pct(median)}</span> "
            "a year against you. This is the same risk premium seen from the other side, and it "
            "is why the carry is rent rather than a free lunch."
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>carrydesk — who is paying whom on Hyperliquid perps</title>
<meta name="description" content="On perpetual futures the crowded side pays the uncrowded side every hour. carrydesk ranks who is paying whom across Hyperliquid, updated hourly and published before the fact.">
<link rel="alternate" type="text/plain" href="/llms.txt" title="LLM-readable summary">
<script type="application/ld+json">{json_ld}</script>
<style>{CSS}</style></head><body><div class="wrap">

<h1 class="hero">{headline}</h1>
<p class="lede">On perpetual futures, whichever crowd is more crowded pays the other one
&mdash; <strong>every hour, automatically</strong>. {lede_tail}</p>
<p class="sub">{n} liquid Hyperliquid perps &middot; {lookback}-day trailing funding &middot;
{as_of} &middot; {freshness}</p>

<div class="head">
  <div class="stat"><div class="k">an equal-weight book earns</div>
    <div class="v">{_pct(snap.get("carry_spread_annualized"))}</div></div>
  <div class="stat"><div class="k">ignoring the extremes</div>
    <div class="v">{_pct(snap.get("carry_spread_annualized_trimmed"))}</div></div>
  <div class="stat"><div class="k">the typical coin</div>
    <div class="v">{_pct(median)}</div></div>
</div>

<h2>Wait — why would anyone pay me?</h2>
<p>A perpetual future never expires, so something has to keep its price tethered to the
real one. That something is the <strong>funding rate</strong>: every hour, one side pays
the other.</p>
<p>When everyone piles into longs, longs pay shorts. When everyone is short, shorts pay
longs. It is a <strong>crowding tax</strong>, and it lands in your account whether or not
the price moves.</p>
<p>So: go long the coins nobody wants to hold, short the coins everybody is crowding into,
in equal size. You are flat on direction &mdash; you do not need to be right about anything
&mdash; and you collect the difference. That is the carry. Not a prediction; rent for being
willing to take the unpopular side.</p>
<p class="dim">It is a risk premium, not free money. It can and does go negative, and it is
gross of fees, slippage and borrow.</p>

<div class="cols">
{_rows(snap.get("longs", []), "Nobody wants these &mdash; paid to hold")}
{_rows(snap.get("shorts", []), "Everybody piles in &mdash; paid to short")}
</div>

{_honesty_block(snap)}

<h2>Carry spread over time</h2>
{chartblock}

<h2>Why trust the numbers</h2>
<p>Anyone can publish a chart today and claim it was right yesterday.</p>
<p>Every snapshot here was written <em>before</em> the hour it describes, appended to a file
that is never edited, and mirrored to a
<a href="https://github.com/pelazas/carrydesk">public git repository</a> where the commit
timestamps are not ours to forge. The chart above is that file, drawn.
<a href="{C.PUBLIC_URL}/archive">{archived_days} day(s) archived so far</a> &mdash; it gets
more convincing every hour, and there is no way to speed that up.</p>

{BACKTEST}

<h2>API</h2>
<pre><code>curl {C.PUBLIC_URL}/v1/free/carry     # free, delayed, top 5 each leg
curl {C.PUBLIC_URL}/v1/carry/rankings # {C.PRICE_RANKINGS} USDC, full live ranking</code></pre>
<p class="dim">Paid endpoints are metered with <a href="https://x402.org">x402</a>: your
client gets a 402, pays USDC on Base, retries, gets data. No account, no API key.
Full docs at <a href="{C.PUBLIC_URL}/docs">/docs</a>, method at
<a href="{C.PUBLIC_URL}/v1/method">/v1/method</a>.</p>

<h2>Use it from an agent</h2>
<pre><code>claude mcp add carrydesk -- uvx --from carrydesk carrydesk-mcp</code></pre>
<p class="dim">One command. No clone, no virtualenv &mdash; <code>uvx</code> fetches and runs it.
Six tools; the free ones work with no wallet configured.</p>

<div class="foot">
<p>Gross of fees, slippage and borrow. Taker fees alone can erase this edge.
Funding data is Hyperliquid's own, with no cross-venue reconciliation.</p>
<p><strong>Informational only. Not investment advice.</strong></p>
<p><a href="https://github.com/pelazas/carrydesk">source</a></p>
</div>
</div></body></html>"""
