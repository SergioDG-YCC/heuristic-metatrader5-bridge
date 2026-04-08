from __future__ import annotations

from heuristic_mt5_bridge.fast_desk.context import FastContext
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyEngine, FastCustodyPolicyConfig


def _ctx(m30_bias: str = "buy") -> FastContext:
    return FastContext(
        symbol="EURUSD",
        session_name="london",
        m30_bias=m30_bias,
        volatility_regime="normal",
        spread_pips=0.6,
        expected_slippage_points=2.0,
        stale_feed=False,
        no_trade_regime=False,
        allowed=True,
        reasons=[],
        details={},
    )


def _candles(count: int = 30, start: float = 1.1000) -> list[dict]:
    out = []
    price = start
    for idx in range(count):
        out.append(
            {
                "open": price,
                "high": price + 0.0005,
                "low": price - 0.0004,
                "close": price + 0.0001,
                "timestamp": f"2026-03-24T12:{idx:02d}:00Z",
            }
        )
        price += 0.00008
    return out


def test_custody_hard_cut_close() -> None:
    engine = FastCustodyEngine(FastCustodyPolicyConfig(hard_cut_r=1.2))
    decision = engine.evaluate_position(
        position={
            "position_id": 101,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.0985,
            "stop_loss": 1.0992,
            "volume": 0.10,
        },
        candles_m1=_candles(),
        candles_m5=_candles(),
        context=_ctx("buy"),
        pip_size=0.0001,
        scaled_out_position_ids=set(),
    )
    assert decision.action == "close"


def test_custody_move_to_breakeven() -> None:
    engine = FastCustodyEngine(FastCustodyPolicyConfig(be_trigger_r=1.0, atr_trigger_r=99.0, structural_trigger_r=99.0))
    decision = engine.evaluate_position(
        position={
            "position_id": 102,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1014,
            "stop_loss": 1.0992,
            "volume": 0.10,
        },
        candles_m1=_candles(),
        candles_m5=_candles(),
        context=_ctx("buy"),
        pip_size=0.0001,
        scaled_out_position_ids=set(),
    )
    assert decision.action in {"move_to_be", "trail_atr", "trail_structural"}


def test_custody_quick_trail_at_half_r_profit() -> None:
    """Scalping quick trail kicks in at 0.5R profit and uses tight M1 ATR."""
    engine = FastCustodyEngine(FastCustodyPolicyConfig(
        quick_trail_r=0.5, quick_trail_atr_multiplier=0.5,
        be_trigger_r=99.0, atr_trigger_r=99.0, structural_trigger_r=99.0,
    ))
    decision = engine.evaluate_position(
        position={
            "position_id": 103,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1006,  # 6 pips profit; risk = 8 pips → 0.75R
            "stop_loss": 1.0992,
            "volume": 0.10,
        },
        candles_m1=_candles(),
        candles_m5=_candles(),
        context=_ctx("buy"),
        pip_size=0.0001,
        scaled_out_position_ids=set(),
    )
    assert decision.action == "trail_atr", f"Expected trail_atr, got {decision.action}: {decision.reason}"
    assert "quick_trail" in decision.reason


def test_custody_scale_out_optional() -> None:
    engine = FastCustodyEngine(
        FastCustodyPolicyConfig(enable_scale_out=True, scale_out_r=1.0, be_trigger_r=99.0, atr_trigger_r=99.0, structural_trigger_r=99.0)
    )
    decision = engine.evaluate_position(
        position={
            "position_id": 104,
            "side": "buy",
            "price_open": 1.1000,
            "price_current": 1.1012,
            "stop_loss": 1.0992,
            "volume": 0.20,
        },
        candles_m1=_candles(),
        candles_m5=_candles(),
        context=_ctx("buy"),
        pip_size=0.0001,
        scaled_out_position_ids=set(),
    )
    assert decision.action in {"reduce", "move_to_be", "trail_atr", "trail_structural"}
