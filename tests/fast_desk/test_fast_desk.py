"""Fast Desk unit tests — covering risk engine and entry policy."""
from __future__ import annotations

import math
import pytest

from heuristic_mt5_bridge.fast_desk.policies.entry import FastEntryPolicy
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig, FastRiskEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PIP = 0.0001  # EURUSD pip


def _make_candle(close: float, high: float | None = None, low: float | None = None, volume: float = 1000.0) -> dict:
    h = high if high is not None else close + PIP * 2
    lo = low if low is not None else close - PIP * 2
    return {"open": close, "high": h, "low": lo, "close": close, "tick_volume": volume}


def _flat_candles(n: int, price: float = 1.1000) -> list[dict]:
    """Candles with no trend and tiny range — choppy market."""
    candles = []
    for _ in range(n):
        candles.append({
            "open": price,
            "high": price + PIP * 0.5,   # ATR << 2 * pip_size
            "low": price - PIP * 0.5,
            "close": price,
            "tick_volume": 500.0,
        })
    return candles


def _momentum_breakout_candles(n: int = 50) -> list[dict]:
    """Flat candles then one bar that crosses decisively above EMA with a volume spike."""
    price = 1.1000
    candles = []
    # n-1 flat candles with healthy ATR range
    for _ in range(n - 1):
        candles.append({
            "open": price,
            "high": price + PIP * 15,   # ~15 pips range → ATR >> 2 pips
            "low": price - PIP * 5,
            "close": price,
            "tick_volume": 800.0,
        })
    # Last candle: clear breakout above EMA + volume spike
    candles.append({
        "open": price,
        "high": price + PIP * 20,
        "low": price - PIP * 2,
        "close": price + PIP * 15,   # decisively above EMA (which is ~price)
        "tick_volume": 2000.0,        # volume spike (2000 > 1.5 × ~860)
    })
    return candles


def _trending_candles(n: int, start: float = 1.1000, step: float = 0.0010) -> list[dict]:
    """Rising candles with clear momentum breakout on the last bar."""
    candles = []
    price = start
    for i in range(n):
        candles.append({
            "open": price,
            "high": price + PIP * 15,
            "low": price - PIP * 5,
            "close": price + (step if i == n - 1 else 0),
            "tick_volume": 1500.0 if i == n - 1 else 800.0,
        })
        price += step if i < n - 2 else 0
    return candles


# ---------------------------------------------------------------------------
# TestFastRiskEngine
# ---------------------------------------------------------------------------


class TestFastRiskEngine:
    """3 tests for the risk engine."""

    def setup_method(self) -> None:
        self.engine = FastRiskEngine()
        self.config = FastRiskConfig(
            risk_per_trade_percent=1.0,
            max_drawdown_percent=5.0,
        )

    def test_calculate_lot_size_known_inputs(self) -> None:
        """$10 000 balance, 1% risk, 50 pips SL, pip_value=$10 → lot = 0.20."""
        balance = 10_000.0
        risk_pct = 1.0
        sl_pips = 50.0
        pip_value = 10.0
        # risk_amount = 100, sl_value = 500 → lot = 0.20
        result = self.engine.calculate_lot_size(balance, risk_pct, sl_pips, pip_value)
        assert math.isclose(result, 0.20, rel_tol=1e-6)

    def test_check_account_safe_false_when_drawdown_exceeds_max(self) -> None:
        """Equity significantly below balance → unsafe."""
        account_state = {"balance": 10_000.0, "equity": 9_400.0}   # 6% drawdown
        assert self.engine.check_account_safe(account_state, self.config) is False

    def test_check_account_safe_true_on_healthy_account(self) -> None:
        """Equity close to balance → safe."""
        account_state = {"balance": 10_000.0, "equity": 9_800.0}   # 2% drawdown
        assert self.engine.check_account_safe(account_state, self.config) is True

    def test_lot_size_clamped_to_minimum(self) -> None:
        """Tiny balance / large SL → clamped to 0.01."""
        result = self.engine.calculate_lot_size(1.0, 1.0, 1000.0, 10.0)
        assert result == 0.01

    def test_lot_size_risk_capped_at_2pct(self) -> None:
        """Even if caller requests 5%, engine caps risk at 2%."""
        result_capped = self.engine.calculate_lot_size(10_000.0, 5.0, 50.0, 10.0)
        result_2pct = self.engine.calculate_lot_size(10_000.0, 2.0, 50.0, 10.0)
        assert result_capped == result_2pct


# ---------------------------------------------------------------------------
# TestFastEntryPolicy
# ---------------------------------------------------------------------------


class TestFastEntryPolicy:
    """2 tests for entry policy."""

    def setup_method(self) -> None:
        self.policy = FastEntryPolicy()
        self.config = FastRiskConfig(max_positions_total=4)

    def test_rejects_when_same_symbol_and_side_already_open(self) -> None:
        """Duplicate symbol+side position → rejected."""
        open_positions = [
            {"symbol": "EURUSD", "type": 0},  # buy
        ]
        allowed, reason = self.policy.can_open("EURUSD", "buy", open_positions, self.config)
        assert allowed is False
        assert "already open" in reason

    def test_allows_when_total_below_max(self) -> None:
        """Fewer positions than max_positions_total and no duplicate → allowed."""
        open_positions = [
            {"symbol": "GBPUSD", "type": 0},  # buy, different symbol
        ]
        allowed, reason = self.policy.can_open("EURUSD", "buy", open_positions, self.config)
        assert allowed is True
        assert reason == "ok"

    def test_rejects_when_total_at_max(self) -> None:
        """Total positions == max → rejected."""
        open_positions = [
            {"symbol": "GBPUSD", "type": 0},
            {"symbol": "USDJPY", "type": 1},
            {"symbol": "XAUUSD", "type": 0},
            {"symbol": "AUDUSD", "type": 1},
        ]
        allowed, reason = self.policy.can_open("EURUSD", "buy", open_positions, self.config)
        assert allowed is False
        assert "max total" in reason

