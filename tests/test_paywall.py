"""Regression guard for the paywall.

The bug this exists to prevent: x402 route patterns use [param] / :param / *,
NOT FastAPI's {param}. Writing "GET /v1/carry/history/{coin}" compiles to
^/v1/carry/history/\\{coin\\}$ which never matches a real request, so the
endpoint returns 200 and serves paid data for free -- with no error anywhere.

Caught in dev on 2026-08-02. These tests make sure it stays caught.
"""
from __future__ import annotations

import pytest

from x402.http.middleware.fastapi import x402HTTPResourceServer
from x402.http.types import PaymentOption, RouteConfig
from x402.mechanisms.evm.exact import register_exact_evm_server
from x402.server import x402ResourceServer

PAY_TO = "0x0000000000000000000000000000000000000001"
NETWORK = "eip155:84532"


def compile_routes(routes: dict):
    server = x402ResourceServer(None)
    register_exact_evm_server(server)
    return x402HTTPResourceServer(server, routes)._compiled_routes


def route(pattern: str) -> dict:
    return {
        pattern: RouteConfig(
            accepts=PaymentOption(
                scheme="exact", pay_to=PAY_TO, price="$0.01", network=NETWORK
            )
        )
    }


def matches(pattern: str, path: str) -> bool:
    return any(r.regex.match(path) for r in compile_routes(route(pattern)))


def test_fastapi_brace_syntax_does_not_match():
    """The footgun itself. If this ever starts passing, x402 changed -- recheck."""
    assert not matches("GET /v1/carry/history/{coin}", "/v1/carry/history/BTC")


def test_bracket_syntax_matches():
    assert matches("GET /v1/carry/history/[coin]", "/v1/carry/history/BTC")
    assert matches("GET /v1/carry/history/[coin]", "/v1/carry/history/SOL")


def test_static_route_matches_exactly():
    assert matches("GET /v1/carry/rankings", "/v1/carry/rankings")
    assert not matches("GET /v1/carry/rankings", "/v1/free/carry")


def test_param_route_does_not_swallow_extra_segments():
    assert not matches("GET /v1/carry/history/[coin]", "/v1/carry/history/BTC/extra")


def test_live_config_gates_every_paid_route():
    """The real config, checked against real sample URLs.

    This is the same assertion the service makes at startup; duplicated here so
    CI fails before a deploy rather than after.
    """
    from carrydesk.api import PAYWALL_SELF_CHECK

    for key, (verb, sample) in PAYWALL_SELF_CHECK.items():
        pattern_path = key.split(" ", 1)[1]
        assert matches(key, sample), (
            f"{key} does not match {sample} -- this route would serve FOR FREE"
        )
        assert "{" not in pattern_path, (
            f"{key} uses FastAPI brace syntax; x402 needs [param] or :param"
        )


def test_self_check_rejects_a_broken_pattern():
    """The guard must actually fail on a bad route, not just pass on good ones."""
    from carrydesk.api import _assert_routes_match

    bad = route("GET /v1/carry/history/{coin}")
    with pytest.raises(RuntimeError, match="serve for free|no self-check sample"):
        _assert_routes_match(bad)
