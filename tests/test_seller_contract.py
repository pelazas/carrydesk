"""Adversarial seller-contract tests for paid GET OpenAPI declarations.

Credential-free. No wallet, signer, payment, secret, or live origin.
"""
from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

from carrydesk import config as C
from carrydesk.carry import build_ranking
from carrydesk.openapi_contract import (
    HISTORY_200,
    RANKINGS_200,
    UNIVERSE_200,
    SUPPORTED_NETWORKS,
    default_usdc_asset,
    payment_info,
)

PAID = {
    "/v1/carry/rankings": C.PRICE_RANKINGS,
    "/v1/carry/history/{coin}": C.PRICE_HISTORY,
    "/v1/universe": C.PRICE_UNIVERSE,
}
FREE = ("/health", "/v1/free/carry", "/v1/method")
ACTION_PIN = "ef519956505b195454aa670230b0936258b451fb"
WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "seller-contract-integrity.yml"
)
FLOOR_SMOKE_WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "x402-floor-smoke.yml"
)
PYPROJECT = (
    pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
)
# First x402 release shipping x402.mechanisms.evm.default_assets.
# 2.17-2.19 lack it and import-fail the app.
X402_FLOOR = "2.20.0"
BASE_MAINNET_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


@pytest.fixture(scope="module")
def openapi() -> dict:
    from carrydesk.api import app

    return app.openapi()


@pytest.fixture
def snapshot() -> dict:
    universe = [
        {
            "coin": f"C{i}",
            "day_notional_volume": 5e6,
            "funding_now": 0.0,
            "open_interest": 1.0,
            "mark_price": 1.0,
            "max_leverage": 10,
        }
        for i in range(40)
    ]
    funding = {
        f"C{i}": {
            "mean_hourly": (i - 20) * 1e-6,
            "n_points": 336,
            "coverage": 1.0,
            "first_ts": 0,
            "last_ts": 1,
        }
        for i in range(40)
    }
    return build_ranking(universe, funding)


def _get(openapi: dict, path: str) -> dict:
    return openapi["paths"][path]["get"]


def _schema200(op: dict) -> dict:
    content = op["responses"]["200"]["content"]
    assert "application/json" in content
    schema = content["application/json"]["schema"]
    assert isinstance(schema, dict)
    return schema


def test_free_routes_still_have_no_payment_declaration(openapi):
    for path in FREE:
        op = _get(openapi, path)
        assert "x-payment-info" not in op
        assert "402" not in op["responses"]


@pytest.mark.parametrize("path", sorted(PAID))
def test_paid_routes_declare_x_payment_info(path, openapi):
    assert "x-payment-info" in _get(openapi, path)


@pytest.mark.parametrize("path,price", sorted(PAID.items()))
def test_declared_price_matches_config_and_is_usdc(path, price, openapi):
    info = _get(openapi, path)["x-payment-info"]
    assert info["price"]["amount"] == price.lstrip("$")
    assert info["price"]["currency"] == "USDC"
    assert info["price"]["mode"] == "fixed"


@pytest.mark.parametrize("path", sorted(PAID))
def test_declared_protocol_is_exact_x402_on_configured_network(path, openapi):
    x402 = _get(openapi, path)["x-payment-info"]["protocols"][0]["x402"]
    assert x402["scheme"] == "exact"
    assert C.X402_NETWORK in SUPPORTED_NETWORKS
    assert x402["network"] == C.X402_NETWORK
    assert x402["asset"] == default_usdc_asset(C.X402_NETWORK)
    assert x402["asset"]
    # Dev/CI have no receiving wallet; live OpenAPI picks it up from X402_PAY_TO.
    assert "payTo" not in x402
    assert x402["resource"].endswith(path)


def test_payment_info_includes_payto_only_when_configured(monkeypatch):
    monkeypatch.setattr(C, "X402_PAY_TO", "0x0000000000000000000000000000000000000001")
    info = payment_info("$0.01", "/v1/universe")
    assert info["protocols"][0]["x402"]["payTo"] == "0x0000000000000000000000000000000000000001"
    monkeypatch.setattr(C, "X402_PAY_TO", "")
    assert "payTo" not in payment_info("$0.01", "/v1/universe")["protocols"][0]["x402"]


@pytest.mark.parametrize(
    "network,asset",
    [
        ("eip155:8453", BASE_MAINNET_USDC),
        ("eip155:84532", BASE_SEPOLIA_USDC),
    ],
)
def test_supported_base_networks_declare_the_exact_usdc_asset(monkeypatch, network, asset):
    monkeypatch.setattr(C, "X402_NETWORK", network)
    info = payment_info("$0.01", "/v1/universe")
    x402 = info["protocols"][0]["x402"]
    assert default_usdc_asset(network) == asset
    assert x402["network"] == network
    # The contract label is USDC only because the charged asset really is.
    assert x402["asset"] == asset
    assert info["price"]["currency"] == "USDC"


def test_eip155_988_charges_usdt0_first_and_fails_closed(monkeypatch):
    from x402.mechanisms.evm.default_assets import DEFAULT_ASSETS

    first = DEFAULT_ASSETS["eip155:988"][0]
    assert first["symbol"] != "USDC"
    assert first["symbol"] == "USDT0"
    assert default_usdc_asset("eip155:988") is None
    monkeypatch.setattr(C, "X402_NETWORK", "eip155:988")
    with pytest.raises(RuntimeError):
        payment_info("$0.01", "/v1/universe")


def test_unknown_network_fails_closed_and_never_omits_or_invents_asset(monkeypatch):
    monkeypatch.setattr(C, "X402_NETWORK", "eip155:31337")
    with pytest.raises(RuntimeError) as err:
        payment_info("$0.01", "/v1/carry/rankings")
    assert "eip155:31337" in str(err.value)


def test_supported_network_set_is_exactly_base_mainnet_and_sepolia():
    assert SUPPORTED_NETWORKS == {"eip155:8453", "eip155:84532"}
    assert SUPPORTED_NETWORKS == {C.BASE_MAINNET, C.BASE_SEPOLIA}


def test_sdk_default_assets_match_base_usdc_ids():
    assert default_usdc_asset("eip155:8453") == BASE_MAINNET_USDC
    assert default_usdc_asset("eip155:84532") == BASE_SEPOLIA_USDC


def test_pyproject_keeps_x402_floor_at_the_verified_minimum():
    deps = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    hits = [d for d in deps if re.fullmatch(r"x402\[[^]]*\]>=[0-9.]+", d)]
    assert len(hits) == 1, hits
    assert hits[0].rsplit(">=", 1)[1] == X402_FLOOR, hits[0]


def test_floor_smoke_workflow_pins_the_declared_x402_floor():
    text = FLOOR_SMOKE_WORKFLOW.read_text()
    m = re.search(r'"x402\[[^]]*\]==([0-9.]+)"', text)
    assert m, text
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    floor = next(d.rsplit(">=", 1)[1] for d in declared if d.startswith("x402"))
    assert m.group(1) == floor == X402_FLOOR


def _assert_exact_action_pins(text: str, *, expected: int) -> None:
    uses_lines = [line for line in text.splitlines() if re.match(r"^\s*-\s+uses:\s+", line)]
    assert len(uses_lines) == expected, uses_lines
    for line in uses_lines:
        assert re.fullmatch(
            r"\s*-\s+uses:\s+[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?",
            line,
        ), f"unpinned action: {line.strip()}"


def test_action_pin_guard_rejects_a_moving_ref():
    with pytest.raises(AssertionError, match="unpinned action"):
        _assert_exact_action_pins("steps:\n  - uses: actions/cache@v4\n", expected=1)


@pytest.mark.parametrize("path", sorted(PAID))
def test_paid_success_is_json_object_200(path, openapi):
    op = _get(openapi, path)
    assert "200" in op["responses"]
    schema = _schema200(op)
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is True
    assert isinstance(schema.get("required"), list)
    assert schema["required"]


@pytest.mark.parametrize("path", sorted(PAID))
def test_paid_routes_keep_402_and_503(path, openapi):
    statuses = set(op for op in _get(openapi, path)["responses"])
    assert {"200", "402", "503"} <= statuses


def test_rankings_query_params_are_optional(openapi):
    params = {p["name"]: p for p in _get(openapi, "/v1/carry/rankings").get("parameters") or []}
    assert params["k"]["required"] is False
    assert params["min_volume"]["required"] is False
    assert params["k"]["in"] == "query"
    assert params["min_volume"]["in"] == "query"


def test_universe_has_no_required_query(openapi):
    params = _get(openapi, "/v1/universe").get("parameters") or []
    assert all(p.get("required") is not True for p in params)


def test_history_requires_path_coin_and_optional_days(openapi):
    params = {p["name"]: p for p in _get(openapi, "/v1/carry/history/{coin}").get("parameters") or []}
    assert params["coin"]["in"] == "path"
    assert params["coin"]["required"] is True
    assert params["days"]["in"] == "query"
    assert params["days"]["required"] is False


def test_rankings_schema_allows_null_headline_ratio(openapi):
    schema = _schema200(_get(openapi, "/v1/carry/rankings"))
    ht = schema["properties"]["headline_vs_typical"]["type"]
    assert set(ht) == {"number", "null"}
    assert "headline_vs_typical" in schema["required"]


def test_rankings_schema_required_fields_are_actually_returned(snapshot):
    body = dict(snapshot)
    body["tier"] = "paid"
    for key in RANKINGS_200["required"]:
        assert key in body
    for row in body["rankings"]:
        for key in RANKINGS_200["properties"]["rankings"]["items"]["required"]:
            assert key in row
    # Zero-median path is allowed: the key stays, the value may be null.
    assert "headline_vs_typical" in RANKINGS_200["required"]


def test_universe_schema_required_fields_match_handler_shape(snapshot):
    body = {
        "as_of": snapshot["as_of"],
        "as_of_ts": snapshot["as_of_ts"],
        "n": snapshot["universe_size"],
        "min_daily_volume": C.MIN_DAILY_VOLUME,
        "sorted_by": "day_notional_volume desc",
        "universe": [
            {
                "coin": r["coin"],
                "day_notional_volume": r["day_notional_volume"],
                "open_interest": r["open_interest"],
                "mark_price": r["mark_price"],
                "funding_now_annualized": r["funding_now_annualized"],
                "mean_funding_annualized": r["mean_funding_annualized"],
                "carry_rank": r["rank"],
            }
            for r in snapshot["rankings"]
        ],
    }
    for key in UNIVERSE_200["required"]:
        assert key in body
    for row in body["universe"]:
        for key in UNIVERSE_200["properties"]["universe"]["items"]["required"]:
            assert key in row


def test_history_schema_required_fields_match_handler_shape():
    body = {"coin": "BTC", "days": 30, "n": 0, "history": []}
    for key in HISTORY_200["required"]:
        assert key in body


def test_schemas_do_not_use_anyof():
    for schema in (RANKINGS_200, UNIVERSE_200, HISTORY_200):
        blob = str(schema)
        assert "anyOf" not in blob
        assert "oneOf" not in blob


def test_workflow_is_manual_read_only_and_sha_pinned():
    text = WORKFLOW.read_text()
    assert "workflow_dispatch" in text
    assert "push:" not in text
    assert "pull_request" not in text
    assert "schedule:" not in text
    assert "contents: read" in text
    assert f"epistemedeus/agent-payment-integrity@{ACTION_PIN}" in text
    assert "upload-sarif: \"false\"" in text or "upload-sarif: 'false'" in text
    assert "origin: https://carry.pelazas.com" in text
    assert "route: /v1/universe" in text
    assert "method: GET" in text
    assert "required-paths: as_of,as_of_ts,n,universe" in text
    assert "secrets:" not in text
    assert "${{" not in text
    assert "GITHUB_TOKEN" not in text
    assert "security-events" not in text
    assert "upload-sarif" in text


def test_floor_smoke_workflow_is_manual_read_only_sha_pinned_and_free():
    text = FLOOR_SMOKE_WORKFLOW.read_text()
    assert "workflow_dispatch" in text
    assert "push:" not in text
    assert "pull_request" not in text
    assert "schedule:" not in text
    assert "contents: read" in text
    _assert_exact_action_pins(text, expected=2)
    assert "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert re.search(
        r"- uses: actions/checkout@[0-9a-f]{40}(?:\s+#.*)?\n"
        r"\s+with:\n\s+persist-credentials: false",
        text,
    )
    assert 'python-version: "3.12"' in text
    assert "x402[fastapi,evm,mcp,clients]==2.20.0" in text
    assert "carrydesk.api" in text
    assert "app.openapi()" in text
    assert "secrets." not in text
    assert "${{" not in text
    assert "GITHUB_TOKEN" not in text
    assert "security-events" not in text
    assert "upload-sarif" not in text
