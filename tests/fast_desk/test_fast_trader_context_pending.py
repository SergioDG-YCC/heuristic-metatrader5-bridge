from __future__ import annotations

from datetime import datetime, timedelta, timezone

from heuristic_mt5_bridge.fast_desk.context import FastContext, FastContextConfig, FastContextService
from heuristic_mt5_bridge.fast_desk.pending import FastPendingManager, FastPendingPolicyConfig


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candles(count: int, *, start: float = 1.1000, step: float = 0.0001, minutes: int = 1, stale: bool = False) -> list[dict]:
    end = datetime.now(timezone.utc)
    if stale:
        end = end - timedelta(minutes=20)
    rows: list[dict] = []
    price = start
    for idx in range(count):
        ts = end - timedelta(minutes=(count - idx) * minutes)
        rows.append(
            {
                "timestamp": _iso(ts),
                "open": price,
                "high": price + 0.0004,
                "low": price - 0.0003,
                "close": price + 0.0001,
            }
        )
        price += step
    return rows


class _TickConnector:
    def __init__(self, bid: float, ask: float) -> None:
        self._bid = bid
        self._ask = ask

    def symbol_tick(self, symbol: str) -> dict:
        _ = symbol
        return {"bid": self._bid, "ask": self._ask}


def test_context_blocks_when_spread_exceeds_limit() -> None:
    service = FastContextService(FastContextConfig(spread_tolerance="low", max_slippage_pct=5.0))
    ctx = service.build_context(
        symbol="EURUSD",
        candles_m1=_candles(40),
        candles_m5=_candles(80, minutes=5),
        candles_h1=_candles(40, minutes=60),
        pip_size=0.0001,
        point_size=0.0001,
        connector=_TickConnector(1.1000, 1.1003),
        symbol_spec={"trade_calc_mode": 0},
    )

    assert ctx.allowed is False
    assert any(reason.startswith("spread_exceeded") for reason in ctx.reasons)


def test_context_blocks_when_m1_feed_is_stale() -> None:
    service = FastContextService(FastContextConfig(stale_feed_seconds=60, spread_tolerance="high", max_slippage_pct=99.0))
    ctx = service.build_context(
        symbol="EURUSD",
        candles_m1=_candles(40, stale=True),
        candles_m5=_candles(80, minutes=5),
        candles_h1=_candles(40, minutes=60),
        pip_size=0.0001,
        point_size=0.0001,
        connector=_TickConnector(1.1000, 1.1001),
    )

    assert ctx.allowed is False
    assert "stale_feed" in ctx.reasons


def _ok_context() -> FastContext:
    return FastContext(
        symbol="EURUSD",
        session_name="london",
        h1_bias="buy",
        volatility_regime="normal",
        spread_pips=0.6,
        expected_slippage_points=2.0,
        stale_feed=False,
        no_trade_regime=False,
        allowed=True,
        reasons=[],
        details={},
    )


def test_pending_manager_cancels_when_context_gate_fails() -> None:
    manager = FastPendingManager(FastPendingPolicyConfig(pending_ttl_seconds=900, reprice_threshold_pips=5.0))
    bad_ctx = FastContext(
        symbol="EURUSD",
        session_name="tokyo",
        h1_bias="neutral",
        volatility_regime="low",
        spread_pips=3.5,
        expected_slippage_points=55.0,
        stale_feed=False,
        no_trade_regime=True,
        allowed=False,
        reasons=["session_blocked"],
        details={},
    )
    decision = manager.evaluate(
        order={"order_id": 7001, "order_type": "buy_limit", "price_open": 1.0990, "created_at": _iso(datetime.now(timezone.utc))},
        context=bad_ctx,
        current_price=1.1000,
        pip_size=0.0001,
    )

    assert decision.action == "cancel"


def test_pending_manager_modifies_when_price_far_from_entry() -> None:
    manager = FastPendingManager(FastPendingPolicyConfig(pending_ttl_seconds=900, reprice_threshold_pips=5.0, reprice_buffer_pips=1.0))
    decision = manager.evaluate(
        order={"order_id": 7002, "order_type": "buy_limit", "price_open": 1.0900, "created_at": _iso(datetime.now(timezone.utc))},
        context=_ok_context(),
        current_price=1.1000,
        pip_size=0.0001,
    )

    assert decision.action == "modify"
    assert decision.price_open is not None
