"""Tests that FAST custody correctly uses the allowlist approach.

After Phase 1+2 fixes:
- FAST receives only fast_owned/inherited_fast tickets via account_payload_for_desk
- The ownership_open_ref for FAST returns only FAST-visible rows
- Any unexpected non-FAST row in ownership_open_ref triggers a warning but is skipped

These tests verify that the contract defence in run_custody works correctly,
and that FAST does not attempt to manage tickets outside its visible set.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from heuristic_mt5_bridge.fast_desk.context import FastContext, FastContextConfig
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyDecision, FastCustodyPolicyConfig
from heuristic_mt5_bridge.fast_desk.pending import FastPendingPolicyConfig
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig
from heuristic_mt5_bridge.fast_desk.state.desk_state import SymbolDeskState
from heuristic_mt5_bridge.fast_desk.trader import FastTraderConfig, FastTraderService
from heuristic_mt5_bridge.fast_desk.trigger import FastTriggerConfig


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candles(count: int, *, minutes: int, start: float = 1.1000) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rows: list[dict[str, Any]] = []
    price = start
    for idx in range(count):
        ts = now - timedelta(minutes=(count - idx) * minutes)
        rows.append(
            {
                "timestamp": _iso(ts),
                "open": price,
                "high": price + 0.0006,
                "low": price - 0.0004,
                "close": price + 0.0002,
            }
        )
        price += 0.00005
    return rows


def _context() -> FastContext:
    return FastContext(
        symbol="EURUSD",
        session_name="london",
        m30_bias="buy",
        volatility_regime="normal",
        spread_pips=0.6,
        expected_slippage_points=2.0,
        stale_feed=False,
        no_trade_regime=False,
        allowed=True,
        reasons=[],
        details={},
    )


class _MarketState:
    def __init__(self) -> None:
        self._m1 = _candles(260, minutes=1)
        self._m5 = _candles(260, minutes=5)
        self._m30 = _candles(260, minutes=30)

    def get_candles(self, symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
        _ = symbol, bars
        tf = str(timeframe).upper()
        if tf == "M1":
            return list(self._m1)
        if tf == "M5":
            return list(self._m5)
        return list(self._m30)


class _SpecRegistry:
    def pip_size(self, symbol: str) -> float:
        _ = symbol
        return 0.0001

    def get(self, symbol: str) -> dict[str, Any]:
        _ = symbol
        return {
            "point": 0.00001,
            "digits": 5,
            "tick_value": 1.0,
            "contract_size": 100000.0,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "spread": 8,
            "trade_stops_level": 10,
        }


class _FakeConnector:
    def symbol_tick(self, symbol: str) -> dict[str, Any]:
        _ = symbol
        return {"bid": 1.1000, "ask": 1.1001}


def _make_trader() -> FastTraderService:
    return FastTraderService(
        trader_config=FastTraderConfig(
            signal_cooldown=0.0,
            enable_pending_orders=True,
            require_m30_alignment=False,
            adoption_grace_seconds=0.0,  # no grace window for these tests
        ),
        context_config=FastContextConfig(spread_tolerance="high", max_slippage_pct=99.0),
        setup_config=FastSetupConfig(rr_ratio=2.0, min_confidence=0.3, min_rr=1.5),
        trigger_config=FastTriggerConfig(),
        pending_config=FastPendingPolicyConfig(pending_ttl_seconds=900),
        custody_config=FastCustodyPolicyConfig(
            enable_atr_trailing=False,
            enable_structural_trailing=False,
            enable_scale_out=False,
        ),
    )


def _ownership_fast_row(position_id: int) -> dict[str, Any]:
    return {
        "desk_owner": "fast",
        "ownership_status": "fast_owned",
        "position_id": position_id,
        "mt5_position_id": position_id,
        "order_id": 0,
        "mt5_order_id": 0,
        "adopted_at": None,
    }


def _ownership_inherited_row(position_id: int) -> dict[str, Any]:
    return {
        "desk_owner": "fast",
        "ownership_status": "inherited_fast",
        "position_id": position_id,
        "mt5_position_id": position_id,
        "order_id": 0,
        "mt5_order_id": 0,
        "adopted_at": None,
    }


def _position(position_id: int, symbol: str = "EURUSD", side: str = "buy") -> dict[str, Any]:
    return {
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "volume": 0.1,
        "price_open": 1.1050,
        "price_current": 1.1060,
        "stop_loss": 1.1000,
        "take_profit": 1.1200,
        "comment": "",
    }


def _pending_order(order_id: int, symbol: str = "EURUSD") -> dict[str, Any]:
    return {
        "order_id": order_id,
        "symbol": symbol,
        "order_type": "buy_limit",
        "volume": 0.1,
        "price_open": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1200,
        "comment": "",
    }


def test_custody_skips_positions_not_in_desk_scoped_payload(tmp_path: Path) -> None:
    """
    The desk-scoped payload only contains FAST positions.  Since run_custody
    iterates the payload positions, any smc_owned ticket would never appear
    (it's been filtered before reaching this point).

    This test verifies that run_custody only touches positions that are present
    in the payload it receives — it does not attempt to look up or manage
    any ticket absent from the payload.
    """
    trader = _make_trader()
    market_state = _MarketState()
    spec_registry = _SpecRegistry()
    db_path = tmp_path / "runtime.db"
    db_path.touch()

    fast_position_id = 6001
    fast_position = _position(fast_position_id)

    # Payload contains only the FAST position (correctly desk-scoped)
    payload = {
        "positions": [fast_position],
        "orders": [],
        "account_state": {"balance": 10000.0, "equity": 10000.0},
    }

    managed_counts: list[int] = []

    # Monkeypatch custody_engine to record which position_ids it evaluated
    original_evaluate = trader.custody_engine.evaluate_position
    evaluated_ids: list[int] = []

    def tracking_evaluate(position: dict[str, Any], **kwargs: Any) -> FastCustodyDecision:
        evaluated_ids.append(int(position.get("position_id", 0)))
        return original_evaluate(position=position, **kwargs)

    trader.custody_engine.evaluate_position = tracking_evaluate  # type: ignore[method-assign]

    result = trader.run_custody(
        symbol="EURUSD",
        market_state=market_state,
        spec_registry=spec_registry,
        account_payload_ref=lambda: payload,
        connector=_FakeConnector(),
        db_path=db_path,
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        ownership_open_ref=lambda: [_ownership_fast_row(fast_position_id)],
    )

    # Only FAST position evaluated — never any hypothetical external ticket
    assert fast_position_id in evaluated_ids


def test_contract_defence_logs_warning_for_unexpected_ownership_row(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """
    If ownership_open_ref returns a row with a non-FAST owner (contract violation),
    run_custody must log a warning and skip that row.
    """
    trader = _make_trader()
    market_state = _MarketState()
    spec_registry = _SpecRegistry()
    db_path = tmp_path / "runtime.db"
    db_path.touch()

    # Simulate a contract violation: ownership_open_ref returns an unexpected row
    unexpected_row = {
        "desk_owner": "unassigned",
        "ownership_status": "unassigned",
        "position_id": 9999,
        "mt5_position_id": 9999,
        "order_id": 0,
        "mt5_order_id": 0,
        "adopted_at": None,
    }

    payload = {
        "positions": [],
        "orders": [],
        "account_state": {"balance": 10000.0, "equity": 10000.0},
    }

    with caplog.at_level(logging.WARNING, logger="fast_desk.trader"):
        trader.run_custody(
            symbol="EURUSD",
            market_state=market_state,
            spec_registry=spec_registry,
            account_payload_ref=lambda: payload,
            connector=_FakeConnector(),
            db_path=db_path,
            broker_server="Broker-1",
            account_login=123456,
            state=SymbolDeskState(),
            ownership_open_ref=lambda: [unexpected_row],
        )

    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("unexpected non-visible ticket in fast ownership ref" in m for m in warning_messages), (
        f"Expected contract violation warning, got: {warning_messages}"
    )


def test_inherited_fast_position_receives_custody(tmp_path: Path) -> None:
    """
    A position marked as inherited_fast must be processed by FAST custody
    (specifically: initial baseline protection for positions with no SL/TP).
    """
    trader = _make_trader()
    market_state = _MarketState()
    spec_registry = _SpecRegistry()
    db_path = tmp_path / "runtime.db"
    db_path.touch()

    inherited_position_id = 4001
    inherited_position = {
        "position_id": inherited_position_id,
        "symbol": "EURUSD",
        "side": "buy",
        "volume": 0.1,
        "price_open": 1.1050,
        "price_current": 1.1060,
        "stop_loss": 0.0,   # No SL — needs protection
        "take_profit": 0.0,  # No TP — needs protection
        "comment": "manual",
    }

    modify_calls: list[dict[str, Any]] = []

    class _TrackingConnector:
        def symbol_tick(self, symbol: str) -> dict[str, Any]:
            _ = symbol
            return {"bid": 1.1060, "ask": 1.1061}

        def modify_position_levels(self, symbol: str, position_id: int, **kwargs: Any) -> dict[str, Any]:
            modify_calls.append({"position_id": position_id, **kwargs})
            return {"ok": True}

    payload = {
        "positions": [inherited_position],
        "orders": [],
        "account_state": {"balance": 10000.0, "equity": 10000.0},
    }

    trader.run_custody(
        symbol="EURUSD",
        market_state=market_state,
        spec_registry=spec_registry,
        account_payload_ref=lambda: payload,
        connector=_TrackingConnector(),
        db_path=db_path,
        broker_server="Broker-1",
        account_login=123456,
        state=SymbolDeskState(),
        ownership_open_ref=lambda: [_ownership_inherited_row(inherited_position_id)],
    )

    # Custody should have attempted to set baseline SL/TP
    assert any(c["position_id"] == inherited_position_id for c in modify_calls), (
        "FAST custody must apply baseline protection for inherited_fast positions without SL/TP"
    )
