"""Tests for session filtering (Bloque A) and spread tolerance (Bloque B)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from heuristic_mt5_bridge.fast_desk.context.service import (
    FastContextConfig,
    FastContextService,
    _classify_asset,
    DEFAULT_SPREAD_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(count: int, *, start: float = 1.1000, step: float = 0.0001, minutes: int = 1) -> list[dict]:
    end = datetime.now(timezone.utc)
    rows: list[dict] = []
    price = start
    for idx in range(count):
        ts = end - timedelta(minutes=(count - idx) * minutes)
        rows.append({
            "timestamp": ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "open": price,
            "high": price + 0.0004,
            "low": price - 0.0003,
            "close": price + 0.0001,
        })
        price += step
    return rows


class _TickConnector:
    def __init__(self, bid: float, ask: float) -> None:
        self._bid = bid
        self._ask = ask

    def symbol_tick(self, symbol: str) -> dict:
        return {"bid": self._bid, "ask": self._ask}


def _build(service: FastContextService, *, symbol: str = "EURUSD", bid: float = 1.1000,
           ask: float = 1.1001, spec: dict | None = None):
    """Build context with tight spread (bid/ask close) to avoid spread_exceeded noise."""
    return service.build_context(
        symbol=symbol,
        candles_m1=_candles(40),
        candles_m5=_candles(80, minutes=5),
        candles_h1=_candles(40, minutes=60),
        pip_size=0.0001,
        point_size=0.0001,
        connector=_TickConnector(bid, ask),
        symbol_spec=spec or {"trade_calc_mode": 0},
    )


# ---------------------------------------------------------------------------
# A — Session tests
# ---------------------------------------------------------------------------

_PATCH_SESSION = "heuristic_mt5_bridge.fast_desk.context.service.session_name_from_timestamp"


def test_global_allows_any_hour():
    """With 'global', no session is blocked (only symbol_closed matters)."""
    cfg = FastContextConfig(allowed_sessions=("global",), spread_tolerance="high")
    svc = FastContextService(cfg)
    for session in ["tokyo", "london", "overlap", "new_york"]:
        with patch(_PATCH_SESSION, return_value=session):
            ctx = _build(svc)
        assert not any(r.startswith("session_blocked") for r in ctx.reasons), f"session={session} should not block"


def test_global_blocks_symbol_closed():
    """With 'global', symbol with trade_mode=0 is still blocked."""
    cfg = FastContextConfig(allowed_sessions=("global",), spread_tolerance="high", max_slippage_pct=99.0)
    svc = FastContextService(cfg)
    ctx = _build(svc, spec={"trade_calc_mode": 0, "trade_mode": 0})
    assert "symbol_closed" in ctx.reasons


def test_all_markets_allows_known_sessions():
    """'all_markets' allows all sessions including late hours (no 'unknown' concept)."""
    cfg = FastContextConfig(allowed_sessions=("all_markets",), spread_tolerance="high")
    svc = FastContextService(cfg)
    with patch(_PATCH_SESSION, return_value="tokyo"):
        ctx = _build(svc)
    assert not any(r.startswith("session_blocked") for r in ctx.reasons)


def test_all_markets_allows_late_hours():
    """'all_markets' allows 22-23 UTC (now maps to new_york, not 'unknown')."""
    cfg = FastContextConfig(allowed_sessions=("all_markets",), spread_tolerance="high")
    svc = FastContextService(cfg)
    with patch(_PATCH_SESSION, return_value="new_york"):
        ctx = _build(svc)
    assert not any(r.startswith("session_blocked") for r in ctx.reasons)


def test_subset_sessions_blocks_tokyo():
    """Default sessions (london, overlap, new_york) block tokyo."""
    cfg = FastContextConfig(spread_tolerance="high")
    svc = FastContextService(cfg)
    with patch(_PATCH_SESSION, return_value="tokyo"):
        ctx = _build(svc)
    assert any(r.startswith("session_blocked") for r in ctx.reasons)


# ---------------------------------------------------------------------------
# B — Asset classification tests
# ---------------------------------------------------------------------------

def test_classify_forex_major():
    assert _classify_asset("EURUSD", {"trade_calc_mode": 0}) == "forex_major"
    assert _classify_asset("GBPUSD", {"trade_calc_mode": 0}) == "forex_major"
    assert _classify_asset("USDJPY", {"trade_calc_mode": 0}) == "forex_major"


def test_classify_forex_minor():
    assert _classify_asset("EURAUD", {"trade_calc_mode": 0}) == "forex_minor"
    assert _classify_asset("NZDCHF", {"trade_calc_mode": 0}) == "forex_minor"


def test_classify_crypto():
    assert _classify_asset("BTCUSD", {"trade_calc_mode": 2}) == "crypto"
    assert _classify_asset("ETHUSD", None) == "crypto"


def test_classify_metals():
    assert _classify_asset("XAUUSD", {"trade_calc_mode": 2}) == "metals"
    assert _classify_asset("XAGUSD", {"trade_calc_mode": 4}) == "metals"


def test_classify_indices():
    assert _classify_asset("US30", {"trade_calc_mode": 2}) == "indices"
    assert _classify_asset("NAS100", {"trade_calc_mode": 4}) == "indices"


def test_classify_other():
    assert _classify_asset("UNKNOWN_SYMBOL", {"trade_calc_mode": 2}) == "other"


# ---------------------------------------------------------------------------
# B — Spread tolerance tests
# ---------------------------------------------------------------------------

def test_spread_low_blocks_forex_major():
    """Low tolerance blocks 0.027% spread on forex major (threshold 0.02%)."""
    cfg = FastContextConfig(spread_tolerance="low", allowed_sessions=("global",))
    svc = FastContextService(cfg)
    # bid=1.1000, ask=1.1003 → spread=0.0003 → pct=0.0003/1.10015*100 ≈ 0.027%
    ctx = _build(svc, bid=1.1000, ask=1.1003, spec={"trade_calc_mode": 0})
    assert any("spread_exceeded" in r for r in ctx.reasons)


def test_spread_medium_accepts_forex_major():
    """Medium tolerance accepts 0.027% spread on forex major (threshold 0.04%)."""
    cfg = FastContextConfig(spread_tolerance="medium", allowed_sessions=("global",))
    svc = FastContextService(cfg)
    ctx = _build(svc, bid=1.1000, ask=1.1003, spec={"trade_calc_mode": 0})
    assert not any("spread_exceeded" in r for r in ctx.reasons)


def test_spread_high_accepts_crypto():
    """High tolerance accepts 0.4% spread on crypto (threshold 0.50%)."""
    cfg = FastContextConfig(spread_tolerance="high", allowed_sessions=("global",))
    svc = FastContextService(cfg)
    # BTCUSD: bid=60000, ask=60240 → pct=240/60120*100 ≈ 0.399%
    ctx = _build(svc, symbol="BTCUSD", bid=60000.0, ask=60240.0,
                 spec={"trade_calc_mode": 2})
    assert not any("spread_exceeded" in r for r in ctx.reasons)


def test_spread_low_blocks_crypto():
    """Low tolerance blocks 0.4% spread on crypto (threshold 0.10%)."""
    cfg = FastContextConfig(spread_tolerance="low", allowed_sessions=("global",))
    svc = FastContextService(cfg)
    ctx = _build(svc, symbol="BTCUSD", bid=60000.0, ask=60240.0,
                 spec={"trade_calc_mode": 2})
    assert any("spread_exceeded" in r for r in ctx.reasons)


def test_m5_ranging_is_warning_not_hard_block(monkeypatch):
    cfg = FastContextConfig(spread_tolerance="high", allowed_sessions=("global",), max_slippage_pct=99.0)
    svc = FastContextService(cfg)
    monkeypatch.setattr(svc, "_detect_market_phase", lambda *args, **kwargs: "ranging")
    ctx = _build(svc)
    assert ctx.allowed is True
    assert "m5_ranging" not in ctx.reasons
    assert "m5_ranging" in ctx.warnings


def test_detect_market_phase_recognizes_pullback_bear(monkeypatch):
    candles: list[dict] = []
    price = 100.0
    for idx in range(80):
        ts = datetime.now(timezone.utc) - timedelta(minutes=(80 - idx) * 5)
        if idx < 68:
            close = price - 0.7
        else:
            close = price + 0.9
        high = max(price, close) + 0.4
        low = min(price, close) - 0.4
        candles.append({
            "timestamp": ts.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "open": price,
            "high": high,
            "low": low,
            "close": close,
        })
        price = close

    monkeypatch.setattr(
        "heuristic_mt5_bridge.fast_desk.context.service.detect_market_structure",
        lambda *_args, **_kwargs: {"trend": "ranging", "last_bos": None},
    )
    phase = FastContextService._detect_market_phase(candles, {"trend": "bearish"})
    assert phase == "pullback_bear"


# ---------------------------------------------------------------------------
# B — Env parsing tests
# ---------------------------------------------------------------------------

def test_parse_allowed_sessions(monkeypatch):
    from heuristic_mt5_bridge.fast_desk.runtime import _parse_allowed_sessions
    monkeypatch.setenv("FAST_TRADER_ALLOWED_SESSIONS", "tokyo,london")
    assert _parse_allowed_sessions() == ("tokyo", "london")


def test_parse_allowed_sessions_default(monkeypatch):
    from heuristic_mt5_bridge.fast_desk.runtime import _parse_allowed_sessions
    monkeypatch.delenv("FAST_TRADER_ALLOWED_SESSIONS", raising=False)
    assert _parse_allowed_sessions() == ("london", "overlap", "new_york")


def test_parse_spread_tolerance(monkeypatch):
    from heuristic_mt5_bridge.fast_desk.runtime import _parse_spread_tolerance
    monkeypatch.setenv("FAST_TRADER_SPREAD_TOLERANCE", "high")
    monkeypatch.delenv("FAST_TRADER_SPREAD_MAX_PIPS", raising=False)
    assert _parse_spread_tolerance() == "high"


def test_parse_spread_tolerance_legacy_fallback(monkeypatch):
    from heuristic_mt5_bridge.fast_desk.runtime import _parse_spread_tolerance
    monkeypatch.delenv("FAST_TRADER_SPREAD_TOLERANCE", raising=False)
    monkeypatch.setenv("FAST_TRADER_SPREAD_MAX_PIPS", "3.0")
    assert _parse_spread_tolerance() == "medium"
