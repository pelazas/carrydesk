"""The product: a cross-sectional funding-carry ranking over Hyperliquid perps.

Pure functions over already-fetched data, so this is unit-testable without a network.

The economics, once, so nobody has to re-derive them:

  A perp's funding rate f is paid hourly by longs to shorts. So per dollar per hour:
      long  a coin with funding f  ->  you receive -f
      short a coin with funding f  ->  you receive +f

  Rank the liquid universe by trailing mean funding. Long the k most negative
  (the market pays you to hold them), short the k most positive (you get paid to
  short them), dollar-neutral. At gross G the book is G/2 long and G/2 short, so:

      hourly carry = (G/2) * (mean_funding(short_leg) - mean_funding(long_leg))

  We publish that bracketed quantity as `carry_spread` -- it is the raw edge,
  independent of how much leverage anyone chooses to apply.

This is a structural risk premium, not a prediction. It is compensation for
absorbing crowded leverage, and it can and does go negative.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config as C


def annualize(hourly_rate: float) -> float:
    """Hourly funding rate -> simple annualized rate (not compounded)."""
    return hourly_rate * C.HOURS_PER_YEAR


def build_ranking(
    universe: list[dict],
    funding: dict[str, dict],
    k: int = C.K_PER_LEG,
    lookback_hours: int = C.LOOKBACK_HOURS,
) -> dict:
    """Combine universe metadata + trailing funding into the published ranking.

    `universe` is HLClient.liquid_universe() output, `funding` is
    HLClient.trailing_funding() output. Coins present in one but not the other
    are dropped -- we only rank what we have both liquidity and funding for.
    """
    rows = []
    by_coin = {u["coin"]: u for u in universe}
    for coin, f in funding.items():
        u = by_coin.get(coin)
        if u is None:
            continue
        rows.append(
            {
                "coin": coin,
                "mean_funding_hourly": f["mean_hourly"],
                "mean_funding_annualized": annualize(f["mean_hourly"]),
                "funding_now_hourly": u["funding_now"],
                "funding_now_annualized": annualize(u["funding_now"]),
                "day_notional_volume": u["day_notional_volume"],
                "open_interest": u["open_interest"],
                "mark_price": u["mark_price"],
                "n_points": f["n_points"],
                "coverage": f["coverage"],
            }
        )

    # Ascending by trailing funding: most negative first. Longs come off the top,
    # shorts off the bottom -- identical to signal.target_weights() in the bot.
    rows.sort(key=lambda r: r["mean_funding_hourly"])

    tradable = len(rows) >= 2 * k
    eff_k = k if tradable else max(0, len(rows) // 2)

    for i, r in enumerate(rows):
        r["rank"] = i + 1
        if eff_k and i < eff_k:
            r["leg"] = "long"
            r["weight"] = 0.5 / eff_k  # fraction of gross, per the bot's sizing
        elif eff_k and i >= len(rows) - eff_k:
            r["leg"] = "short"
            r["weight"] = -0.5 / eff_k
        else:
            r["leg"] = None
            r["weight"] = 0.0

    longs = [r for r in rows if r["leg"] == "long"]
    shorts = [r for r in rows if r["leg"] == "short"]

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def _median(xs):
        if not xs:
            return 0.0
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    def _trimmed_mean(xs, trim=1):
        """Mean after dropping `trim` values from each end."""
        if len(xs) <= 2 * trim:
            return _mean(xs)
        return _mean(sorted(xs)[trim:-trim])

    long_rates = [r["mean_funding_hourly"] for r in longs]
    short_rates = [r["mean_funding_hourly"] for r in shorts]

    long_mean = _mean(long_rates)
    short_mean = _mean(short_rates)
    spread_hourly = short_mean - long_mean

    # Robust variants. The plain mean is what an equal-weighted book actually
    # earns, so it stays the headline -- but a single illiquid coin funding at
    # 200%/yr can carry the whole number, and a buyer who acts on that without
    # seeing the dispersion gets hurt. Publishing both is the honest move.
    spread_trimmed = _trimmed_mean(short_rates) - _trimmed_mean(long_rates)
    spread_median = _median(short_rates) - _median(long_rates)

    now = datetime.now(timezone.utc)
    return {
        "as_of": now.isoformat(timespec="seconds"),
        "as_of_ts": int(now.timestamp()),
        "source": "hyperliquid",
        "method": {
            "lookback_hours": lookback_hours,
            "k_per_leg": eff_k,
            "min_daily_volume": C.MIN_DAILY_VOLUME,
            "max_universe": C.MAX_UNIVERSE,
            "funding_interval_hours": C.FUNDING_INTERVAL_HOURS,
        },
        "universe_size": len(rows),
        "tradable": tradable,
        "carry_spread_hourly": spread_hourly,
        "carry_spread_annualized": annualize(spread_hourly),
        # Outlier-robust variants -- see the comment where these are computed.
        # If trimmed is far below the headline, a couple of illiquid names are
        # carrying the number and it will not survive at size.
        "carry_spread_annualized_trimmed": annualize(spread_trimmed),
        "carry_spread_annualized_median": annualize(spread_median),
        "outlier_dominated": bool(
            abs(annualize(spread_hourly)) > 0
            and abs(annualize(spread_trimmed)) < 0.5 * abs(annualize(spread_hourly))
        ),
        "long_leg_mean_annualized": annualize(long_mean),
        "short_leg_mean_annualized": annualize(short_mean),
        # Expected gross carry before costs, at the reference leverages.
        "expected_annual_return": {
            "gross_1.0": 0.5 * annualize(spread_hourly),
            "gross_2.0": 1.0 * annualize(spread_hourly),
        },
        "rankings": rows,
    }


def free_view(snapshot: dict, k: int = C.FREE_TIER_K) -> dict:
    """The public/free slice: top-k each leg, headline numbers, no full universe.

    Deliberately still useful -- it is the demo and the daily proof post. What
    is withheld is breadth (the other ~28 coins) and freshness, not quality.
    """
    rows = snapshot.get("rankings", [])
    longs = [r for r in rows if r.get("leg") == "long"][:k]
    shorts = [r for r in rows if r.get("leg") == "short"][-k:]
    keep = ("coin", "rank", "leg", "mean_funding_annualized", "day_notional_volume")
    trim = lambda r: {x: r[x] for x in keep if x in r}  # noqa: E731
    return {
        "as_of": snapshot.get("as_of"),
        "as_of_ts": snapshot.get("as_of_ts"),
        "source": snapshot.get("source"),
        "method": snapshot.get("method"),
        "universe_size": snapshot.get("universe_size"),
        "carry_spread_annualized": snapshot.get("carry_spread_annualized"),
        "carry_spread_annualized_trimmed": snapshot.get("carry_spread_annualized_trimmed"),
        "carry_spread_annualized_median": snapshot.get("carry_spread_annualized_median"),
        "outlier_dominated": snapshot.get("outlier_dominated"),
        "long_leg_mean_annualized": snapshot.get("long_leg_mean_annualized"),
        "short_leg_mean_annualized": snapshot.get("short_leg_mean_annualized"),
        "expected_annual_return": snapshot.get("expected_annual_return"),
        "tier": "free",
        "showing": f"top {k} of each leg",
        "full_universe_size": snapshot.get("universe_size"),
        "longs": [trim(r) for r in longs],
        "shorts": [trim(r) for r in shorts],
    }
