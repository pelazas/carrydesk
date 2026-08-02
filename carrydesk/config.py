"""Configuration. Everything is env-overridable; defaults are the live values.

Numbers that mirror the trading bot (MIN_DAILY_VOLUME, MAX_UNIVERSE, LOOKBACK_HOURS,
K_PER_LEG) come from systematic-trading/10-live/bot/config.py and are validated in
that repo's RESULTS.md. Do not tune them casually -- the whole point of this product
is that the published ranking is the same one a real book trades.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CARRYDESK_DATA_DIR", ROOT / "data"))
SNAPSHOT_DIR = DATA_DIR / "snapshots"

# --- Hyperliquid ------------------------------------------------------------
HL_API_URL = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz")

# --- Universe & signal (mirrors the live bot) -------------------------------
MIN_DAILY_VOLUME = float(os.getenv("MIN_DAILY_VOLUME", 1_000_000))  # $/day notional
MAX_UNIVERSE = int(os.getenv("MAX_UNIVERSE", 40))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", 24 * 14))  # 14-day trailing mean
MIN_COVERAGE = float(os.getenv("MIN_COVERAGE", 0.5))  # need >=50% of expected points
K_PER_LEG = int(os.getenv("K_PER_LEG", 10))

FUNDING_INTERVAL_HOURS = 1  # Hyperliquid funds hourly
HOURS_PER_YEAR = 24 * 365

# --- Refresh ----------------------------------------------------------------
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", 3600))  # funding is hourly
HL_CONCURRENCY = int(os.getenv("HL_CONCURRENCY", 8))
HL_TIMEOUT = float(os.getenv("HL_TIMEOUT", 20.0))

# --- Free tier --------------------------------------------------------------
FREE_TIER_K = int(os.getenv("FREE_TIER_K", 5))  # top-5 each leg
FREE_TIER_DELAY_HOURS = int(os.getenv("FREE_TIER_DELAY_HOURS", 24))

# --- Payments (x402) --------------------------------------------------------
# Networks are CAIP-2 ids, NOT friendly names -- the facilitator advertises
# "eip155:84532", and passing "base-sepolia" fails route validation at startup
# with "No scheme for exact on base-sepolia". Verified against
# https://x402.org/facilitator/supported on 2026-08-02.
#
#   eip155:84532 -> Base Sepolia (testnet). Public facilitator, NO credentials.
#   eip155:8453  -> Base mainnet (real USDC). Needs a CDP-backed facilitator
#                   and CDP API keys; the public facilitator is testnet-only.
BASE_SEPOLIA = "eip155:84532"
BASE_MAINNET = "eip155:8453"
X402_NETWORK = os.getenv("X402_NETWORK", BASE_SEPOLIA)
X402_PAY_TO = os.getenv("X402_PAY_TO", "")  # receiving wallet address
X402_FACILITATOR_URL = os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator")
PAYMENTS_ENABLED = bool(X402_PAY_TO)

PRICE_RANKINGS = os.getenv("PRICE_RANKINGS", "$0.05")
PRICE_HISTORY = os.getenv("PRICE_HISTORY", "$0.02")
PRICE_UNIVERSE = os.getenv("PRICE_UNIVERSE", "$0.01")

SERVICE_NAME = "carrydesk"
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")
