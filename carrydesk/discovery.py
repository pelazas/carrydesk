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
claude mcp add carrydesk -- uvx --from git+https://github.com/pelazas/carrydesk carrydesk-mcp
```

Tools: `carry_snapshot`, `carry_method`, `carry_health` (free);
`carry_rankings`, `carry_history`, `carry_universe` (paid).
Set `CARRYDESK_PRIVATE_KEY` for automatic payment; without it the free tools
work and paid tools return the price instead of failing.

## Reading the numbers honestly

Every response carries three spread figures, not one:

- `carry_spread_annualized` — plain mean, what an equal-weighted book earns
- `carry_spread_annualized_trimmed` — mean after dropping the extremes
- `carry_spread_annualized_median` — median

When these diverge sharply, one or two illiquid names are carrying the headline
and `outlier_dominated` is set to true. Readings of 40% headline against 10%
median are routine. Quote the median, or quote all three.

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
        "isAccessibleForFree": True,
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
            {"@type": "PropertyValue", "name": "universe_size",
             "value": snap.get("universe_size")},
            {"@type": "PropertyValue", "name": "snapshots_published",
             "value": totals.get("snapshots")},
        ],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{u}/v1/free/carry", "name": "Free tier (delayed)"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{u}/v1/carry/rankings", "name": "Full live ranking (paid)"},
        ],
    }
    return json.dumps(doc, separators=(",", ":"))
