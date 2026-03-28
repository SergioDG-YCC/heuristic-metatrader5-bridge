from __future__ import annotations

from heuristic_mt5_bridge.fast_desk.setup.engine import FastSetupConfig, FastSetupEngine
from heuristic_mt5_bridge.fast_desk.trigger.engine import FastTriggerEngine


def _m5_candles(count: int = 80, start: float = 1.1000) -> list[dict]:
    rows = []
    price = start
    for idx in range(count):
        rows.append(
            {
                "timestamp": f"2026-03-24T10:{idx:02d}:00Z",
                "open": price,
                "high": price + 0.0006,
                "low": price - 0.0004,
                "close": price + 0.0002,
            }
        )
        price += 0.00005
    return rows


def _m1_candles_for_displacement(side: str = "buy") -> list[dict]:
    rows = []
    price = 1.1000
    for idx in range(25):
        body = 0.00004
        if idx == 24:
            body = 0.00022
        if side == "buy":
            open_price = price
            close = price + body
        else:
            open_price = price + body
            close = price
        rows.append(
            {
                "timestamp": f"2026-03-24T11:{idx:02d}:00Z",
                "open": open_price,
                "high": max(open_price, close) + 0.00005,
                "low": min(open_price, close) - 0.00005,
                "close": close,
            }
        )
        price += 0.00001
    return rows


def test_core_setup_order_block_retest(monkeypatch) -> None:
    engine = FastSetupEngine()
    candles = _m5_candles()

    def _fake_obs(candles, structure, min_impulse_candles=2, max_zones=6):
        return [
            {
                "zone_type": "ob_bullish",
                "price_high": 1.1045,
                "price_low": 1.1040,
                "wick_low": 1.1036,
                "origin_candle_time": "2026-03-24T10:30:00Z",
            }
        ]

    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.setup.engine.detect_order_blocks", _fake_obs)
    out = engine._order_block_retest(
        symbol="EURUSD",
        candles_m5=candles,
        structure_m5={"swings": []},
        latest_close=1.1043,
        atr=0.0008,
        pip_size=0.0001,
        rr=2.0,
    )

    assert out
    assert out[0].setup_type == "order_block_retest"
    assert out[0].requires_pending is True


def test_core_setup_liquidity_sweep_reclaim(monkeypatch) -> None:
    engine = FastSetupEngine()

    monkeypatch.setattr("heuristic_mt5_bridge.fast_desk.setup.engine.detect_liquidity_pools", lambda *a, **k: [{}])
    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_sweeps",
        lambda *a, **k: [{"zone_type": "sweep_ssl", "swept_level": 1.1000, "price_low": 1.0992, "sweep_candle_time": "x"}],
    )

    out = engine._liquidity_sweep_reclaim(
        symbol="EURUSD",
        candles_m5=_m5_candles(),
        candles_h1=_m5_candles(40),
        structure_h1={},
        latest_close=1.1004,
        atr=0.0009,
        pip_size=0.0001,
        rr=2.0,
    )

    assert out
    assert out[0].setup_type == "liquidity_sweep_reclaim"
    assert out[0].side == "buy"


def test_core_setup_breakout_retest() -> None:
    engine = FastSetupEngine()
    # Build M5 candles: normal bodies + strong impulse at BOS index 11
    candles_m5 = [
        {"open": 1.1000, "close": 1.1002, "high": 1.1003, "low": 1.0999}
        for _ in range(20)
    ]
    # Make BOS candle (index 11) have a clearly above-average body
    candles_m5[11] = {"open": 1.1000, "close": 1.1020, "high": 1.1022, "low": 1.0998}
    out = engine._breakout_retest(
        symbol="EURUSD",
        candles_m5=candles_m5,
        structure_m5={"last_bos": {"direction": "bullish", "price": 1.1020, "index": 11}},
        latest_close=1.1021,
        atr=0.0005,
        pip_size=0.0001,
        rr=2.0,
    )

    assert out
    assert out[0].setup_type == "breakout_retest"
    assert out[0].pending_entry_type == "stop"


def test_pattern_setup_wedge_and_flag_and_triangle() -> None:
    engine = FastSetupEngine()

    # Rising wedge shape (bearish)
    wedge_candles = []
    low = 1.1000
    high = 1.1020
    for idx in range(18):
        high += 0.00003
        low += 0.00005
        wedge_candles.append({"high": high, "low": low, "open": low, "close": high, "timestamp": f"t{idx}"})
    wedge = engine._wedge_retest("EURUSD", wedge_candles, wedge_candles[-1]["high"], 0.0006, 0.0001, 2.0)
    assert wedge is not None
    assert wedge.setup_type == "wedge_retest"

    # Bull flag: strong impulse up then pullback
    flag = []
    p = 1.1000
    for _ in range(16):
        flag.append({"open": p, "high": p + 0.0008, "low": p - 0.0002, "close": p + 0.0007})
        p += 0.0005
    for _ in range(10):
        flag.append({"open": p, "high": p + 0.00025, "low": p - 0.00035, "close": p - 0.0001})
        p -= 0.00005
    setup_flag = engine._flag_retest("EURUSD", flag, flag[-1]["close"], 0.0007, 0.0001, 2.0)
    assert setup_flag is not None
    assert setup_flag.setup_type == "flag_retest"

    # Triangle contraction
    tri = []
    hi = 1.1050
    lo = 1.0950
    for _ in range(16):
        hi -= 0.0002
        lo += 0.0002
        tri.append({"high": hi, "low": lo, "open": lo + 0.0003, "close": hi - 0.0003})
    triangle = engine._triangle_retest("EURUSD", tri, tri[-1]["close"], 0.0008, 0.0001, 2.0, "buy")
    assert triangle is not None
    assert triangle.setup_type == "triangle_retest"


def test_pattern_setup_sr_polarity_retest(monkeypatch) -> None:
    engine = FastSetupEngine()
    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_market_structure",
        lambda candles, window=3: {"last_bos": {"direction": "bearish", "price": 1.1010}},
    )
    out = engine._sr_polarity_retest("EURUSD", _m5_candles(), 1.1009, 0.0005, 0.0001, 2.0)
    assert out is not None
    assert out.setup_type == "sr_polarity_retest"


def test_trigger_engine_confirms_displacement() -> None:
    setup = FastSetupEngine._make_setup(
        symbol="EURUSD",
        setup_type="breakout_retest",
        side="buy",
        entry=1.1010,
        stop_loss=1.1000,
        pip_size=0.0001,
        rr=2.0,
        confidence=0.7,
        requires_pending=False,
        pending_entry_type="market",
        retest_level=1.1010,
        metadata={},
    )
    engine = FastTriggerEngine()
    decision = engine.confirm(setup=setup, candles_m1=_m1_candles_for_displacement("buy"), pip_size=0.0001)
    assert decision.confirmed is True
    assert decision.trigger_type in {"displacement", "micro_bos", "micro_choch", "reclaim", "rejection_candle"}


def test_detect_setups_keeps_effective_rr_above_internal_floor(monkeypatch) -> None:
    engine = FastSetupEngine(FastSetupConfig(rr_ratio=3.0))
    candles_m5 = _m5_candles(80, 1.1000)
    candles_h1 = _m5_candles(40, 1.0900)

    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_market_structure",
        lambda candles, window=3: {},
    )
    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_order_blocks",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_liquidity_pools",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.setup.engine.detect_sweeps",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        FastSetupEngine,
        "_pattern_setups",
        lambda *a, **k: [
            FastSetupEngine._make_setup(
                symbol="EURUSD",
                setup_type="wedge_retest",
                side="buy",
                entry=1.1000,
                stop_loss=1.0990,
                pip_size=0.0001,
                rr=3.5,
                confidence=0.8,
                requires_pending=True,
                pending_entry_type="limit",
                retest_level=1.1000,
                metadata={},
            )
        ],
    )

    out = engine.detect_setups(
        symbol="EURUSD",
        candles_m5=candles_m5,
        candles_h1=candles_h1,
        pip_size=0.0001,
        h1_bias="buy",
        spread_pips=0.4,
    )

    assert out
    assert out[0].risk_pips == 10.4
    effective_rr = abs(out[0].take_profit - out[0].entry_price) / abs(out[0].entry_price - out[0].stop_loss)
    assert effective_rr > 3.0
