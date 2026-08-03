"""Machine-readable discovery surfaces.

The buyer here is increasingly an agent rather than a person, so being findable
by machines is not an afterthought — it is the distribution strategy that can
actually run unattended.

Four surfaces, all generated from the same config so they cannot drift:
  /llms.txt     — what this service is and how to call it, for an LLM
  /robots.txt   — explicitly welcomes crawlers, including AI ones
  /sitemap.xml  — the free pages worth indexing
  JSON-LD       — schema.org Dataset markup embedded in the public page
"""
from __future__ import annotations

import json

from . import config as C

# Crawlers that identify themselves and respect robots.txt. Listed explicitly
# rather than relying on the wildcard, because several of these look for their
# own User-agent block and a bare "*" is sometimes treated conservatively.
AI_CRAWLERS = [
    "GPTBot",
    "ClaudeBot",
    "anthropic-ai",
    "Claude-Web",
    "PerplexityBot",
    "Google-Extended",
    "CCBot",
    "Applebot-Extended",
    "Bingbot",
]


def llms_txt() -> str:
    u = C.PUBLIC_URL.rstrip("/")
    return f"""# carrydesk

> Cross-sectional funding-carry rankings for Hyperliquid perpetual futures,
> published continuously and sold per call in USDC via the x402 protocol.

## What it is

Perpetual futures charge a funding rate hourly between longs and shorts.
carrydesk ranks the liquid Hyperliquid perp universe by trailing 14-day mean
funding. The most negative names pay you to hold them long; the most positive
pay you to short them. Going long the bottom k and short the top k,
dollar-neutral, collects the spread between the legs.

This is a structural risk premium — compensation for absorbing crowded
leverage — not a price prediction. It can and does go negative.

## Free endpoints (no key, no account, no payment)

- `GET {u}/v1/free/carry` — top 5 each leg + headline spreads, delayed 24h (JSON)
- `GET {u}/v1/method` — exact methodology and caveats (JSON)
- `GET {u}/health` — service health and data freshness (JSON)
- `GET {u}/archive` — every snapshot ever published (HTML)
- `GET {u}/openapi.json` — full OpenAPI 3 specification
- `GET {u}/docs` — interactive API documentation

## Paid endpoints (x402, USDC on Base mainnet)

- `GET {u}/v1/carry/rankings` — {C.PRICE_RANKINGS} — full live ranking, all liquid perps,
  with rank, leg assignment and dollar-neutral weights. Accepts `k` (1-20).
- `GET {u}/v1/carry/history/{{coin}}` — {C.PRICE_HISTORY} — archived rank and funding history
- `GET {u}/v1/universe` — {C.PRICE_UNIVERSE} — liquid perps by volume, OI, mark price, funding

Payment is HTTP 402 → pay USDC on Base → retry. No account or API key exists.
The buyer needs no ETH: settlement uses EIP-3009, so the facilitator sponsors gas.

## For agents

An MCP server exposes the same data as tools:

```
claude mcp add carrydesk -- uvx --from carrydesk carrydesk-mcp
```

Tools: `carry_snapshot`, `carry_method`, `carry_health` (free);
`carry_rankings`, `carry_history`, `carry_universe` (paid).
Set `CARRYDESK_PRIVATE_KEY` for automatic payment; without it the free tools
work and paid tools return the price instead of failing.

## Reading the numbers honestly

Every response carries three spread figures, not one:

- `carry_spread_annualized` — plain mean, what an equal-weighted book earns
- `carry_spread_annualized_trimmed` — mean after dropping the extremes
- `carry_spread_annualized_median` — median, what a typical coin pays

Two more fields tell you how far apart they are:

- `headline_vs_typical` — abs(mean / median). Around 4.0 on live data, meaning
  the headline routinely overstates a typical coin fourfold. Set your own
  threshold on this rather than trusting the boolean.
- `outlier_dominated` — true when median < 0.5 * mean. Fires often, because
  this universe genuinely is outlier-driven most of the time.

`expected_annual_return` is given twice for the same reason: `from_median` is
what a typical coin supports and the figure to plan against; `from_mean` is what
an equal-weighted book earns if the extreme funders stay put and stay tradable.
Those have differed by about 4.7x in practice.

Readings of 50% headline against 13% median are routine. **Quote the median, or
quote all three.** One or two illiquid coins funding at 200%/yr carry the mean,
and you cannot trade size in them.

All figures are gross of fees, slippage and borrow. Taker fees alone can erase
the edge. Funding data is Hyperliquid's own, with no cross-venue reconciliation.

## Not investment advice

Informational only. No recommendation to trade is made or implied.

## Source

https://github.com/pelazas/carrydesk
"""


def robots_txt() -> str:
    u = C.PUBLIC_URL.rstrip("/")
    lines = [
        "# carrydesk — crawlers and AI agents are welcome.",
        "# The free tier is meant to be read, indexed and quoted.",
        "",
    ]
    for agent in AI_CRAWLERS:
        lines += [f"User-agent: {agent}", "Allow: /", ""]
    lines += [
        "User-agent: *",
        "Allow: /",
        "",
        "# Paid routes are metered, not secret -- crawling them just yields a 402.",
        "",
        f"Sitemap: {u}/sitemap.xml",
        "",
    ]
    return "\n".join(lines)


def sitemap_xml() -> str:
    u = C.PUBLIC_URL.rstrip("/")
    paths = [("/", "hourly", "1.0"), ("/archive", "hourly", "0.9"),
             ("/v1/method", "monthly", "0.7"), ("/docs", "monthly", "0.6"),
             ("/llms.txt", "weekly", "0.5")]
    body = "".join(
        f"<url><loc>{u}{p}</loc><changefreq>{f}</changefreq>"
        f"<priority>{pr}</priority></url>"
        for p, f, pr in paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )


def json_ld(snap: dict, totals: dict) -> str:
    """schema.org Dataset markup so crawlers parse the page as data, not prose."""
    u = C.PUBLIC_URL.rstrip("/")
    doc = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Hyperliquid cross-sectional funding carry",
        "description": (
            "Daily-updated cross-sectional ranking of liquid Hyperliquid "
            "perpetual futures by trailing 14-day mean funding rate, with "
            "long/short leg assignment and outlier-robust carry spread."
        ),
        "url": u,
        "license": "https://opensource.org/licenses/MIT",
        # FALSE on purpose. A reduced, 24h-delayed subset is free, but the full
        # dataset is metered -- and this field is read by dataset aggregators,
        # which would otherwise index carrydesk as freely accessible. Claiming
        # "free" because a free tier exists is the kind of machine-readable
        # overstatement this product cannot afford to make.
        "isAccessibleForFree": False,
        "offers": [
            {
                "@type": "Offer",
                "name": "Full live ranking",
                "url": f"{u}/v1/carry/rankings",
                "price": C.PRICE_RANKINGS.lstrip("$"),
                "priceCurrency": "USDC",
                "description": "Per call, settled on Base via x402. No account required.",
            },
            {
                "@type": "Offer",
                "name": "Per-coin archived history",
                "url": f"{u}/v1/carry/history/",
                "price": C.PRICE_HISTORY.lstrip("$"),
                "priceCurrency": "USDC",
            },
            {
                "@type": "Offer",
                "name": "Liquid perp universe",
                "url": f"{u}/v1/universe",
                "price": C.PRICE_UNIVERSE.lstrip("$"),
                "priceCurrency": "USDC",
            },
        ],
        "keywords": [
            "funding rate", "perpetual futures", "Hyperliquid", "carry trade",
            "market neutral", "crypto derivatives", "x402",
        ],
        "creator": {"@type": "Organization", "name": "carrydesk", "url": u},
        "temporalCoverage": f"{snap.get('as_of', '')}",
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "carry_spread_annualized",
             "value": snap.get("carry_spread_annualized")},
            {"@type": "PropertyValue", "name": "carry_spread_annualized_median",
             "value": snap.get("carry_spread_annualized_median")},
            {"@type": "PropertyValue", "name": "headline_vs_typical",
             "value": snap.get("headline_vs_typical"),
             "description": "How many times the mean overstates the median coin."},
            {"@type": "PropertyValue", "name": "outlier_dominated",
             "value": snap.get("outlier_dominated"),
             "description": "True when the headline materially overstates a typical coin."},
            {"@type": "PropertyValue", "name": "universe_size",
             "value": snap.get("universe_size")},
        ],
        # Archive size belongs here, not in variableMeasured -- it is a property
        # of the collection, not a column a consumer can fetch.
        "includedInDataCatalog": {
            "@type": "DataCatalog",
            "name": "carrydesk published archive",
            "url": f"{u}/archive",
            "description": (
                f"{totals.get('distinct_hours', 0)} distinct hours covered by "
                f"{totals.get('snapshots', 0)} snapshots, append-only and mirrored "
                "to a public git repository. Snapshot count exceeds hours because "
                "the service also recomputes on restart."
            ),
        },
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{u}/v1/free/carry",
             "name": "Free tier — reduced and delayed 24h, no wallet required"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{u}/v1/carry/rankings",
             "name": f"Full live ranking — metered, {C.PRICE_RANKINGS} USDC per call"},
        ],
    }
    return json.dumps(doc, separators=(",", ":"))
