from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from heuristic_mt5_bridge.core.runtime.market_state import session_name_from_timestamp
from heuristic_mt5_bridge.smc_desk.detection.structure import detect_market_structure


_FOREX_MAJORS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
_CRYPTO_TOKENS = {"BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "DOT", "DOGE", "BNB"}

DEFAULT_SPREAD_THRESHOLDS: dict[str, dict[str, float]] = {
    "low":    {"forex_major": 0.02, "forex_minor": 0.04, "metals": 0.05, "indices": 0.03, "crypto": 0.10, "other": 0.05},
    "medium": {"forex_major": 0.04, "forex_minor": 0.08, "metals": 0.10, "indices": 0.06, "crypto": 0.25, "other": 0.10},
    "high":   {"forex_major": 0.10, "forex_minor": 0.15, "metals": 0.20, "indices": 0.12, "crypto": 0.50, "other": 0.20},
}


def _default_thresholds() -> dict[str, dict[str, float]]:
    """Return a deep copy of the default spread thresholds."""
    return {level: dict(values) for level, values in DEFAULT_SPREAD_THRESHOLDS.items()}


@dataclass
class FastContextConfig:
    spread_tolerance: str = "medium"    # "low" | "medium" | "high"
    max_slippage_pct: float = 0.05      # max tick-vs-candle divergence as % of price
    stale_feed_seconds: int = 180
    require_h1_alignment: bool = True
    allowed_sessions: tuple[str, ...] = ("london", "overlap", "new_york")
    spread_thresholds: dict[str, dict[str, float]] = field(default_factory=_default_thresholds)


def _classify_asset(symbol: str, spec: dict[str, Any] | None) -> str:
    """Return asset class: forex_major, forex_minor, metals, indices, crypto, other."""
    sym = symbol.upper()
    calc_mode = int((spec or {}).get("trade_calc_mode", -1))
    if calc_mode == 0:
        return "forex_major" if sym in _FOREX_MAJORS else "forex_minor"
    if any(tok in sym for tok in _CRYPTO_TOKENS):
        return "crypto"
    if any(m in sym for m in ("XAU", "XAG", "GOLD", "SILVER")):
        return "metals"
    if any(idx in sym for idx in ("US30", "SPX", "NAS", "DAX", "FTSE", "JP225", "US500", "US100", "US2000")):
        return "indices"
    return "other"


@dataclass
class FastContext:
    symbol: str
    session_name: str
    h1_bias: str
    volatility_regime: str
    spread_pips: float
    expected_slippage_points: float
    stale_feed: bool
    no_trade_regime: bool
    allowed: bool
    market_phase: str = "unknown"  # trending, ranging, compression, breakout
    exhaustion_risk: str = "low"  # low, medium, high
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class FastContextService:
    """Build deterministic trading context for FastTraderService.

    Context is evaluated once per scan cycle and reused by setup/trigger/execution.
    """

    def __init__(self, config: FastContextConfig | None = None) -> None:
        self.config = config or FastContextConfig()

    def build_context(
        self,
        *,
        symbol: str,
        candles_m1: list[dict[str, Any]],
        candles_m5: list[dict[str, Any]],
        candles_h1: list[dict[str, Any]],
        pip_size: float,
        point_size: float,
        connector: Any | None = None,
        prefetched_tick: dict[str, Any] | None = None,
        symbol_spec: dict[str, Any] | None = None,
    ) -> FastContext:
        cfg = self.config
        reasons: list[str] = []
        warnings: list[str] = []

        now = datetime.now(timezone.utc)
        session_name = session_name_from_timestamp(now)
        # Symbol spec gate — always check trade_mode first (authoritative source)
        if symbol_spec:
            trade_mode = symbol_spec.get("trade_mode")
            if trade_mode is not None and int(trade_mode) == 0:
                reasons.append("symbol_closed")
        # Session gate — configurable per Fast Desk only
        if "global" not in cfg.allowed_sessions and "all_markets" not in cfg.allowed_sessions:
            if session_name not in set(cfg.allowed_sessions):
                reasons.append(f"session_blocked:{session_name}")

        # H1 directional bias
        h1_structure = detect_market_structure(candles_h1[-160:], window=3) if len(candles_h1) >= 20 else {}
        trend = str(h1_structure.get("trend", "ranging"))
        h1_bias = "neutral"
        if trend == "bullish":
            h1_bias = "buy"
        elif trend == "bearish":
            h1_bias = "sell"

        # Volatility regime from M5 range/body ratio
        volatility_regime = self._volatility_regime(candles_m5)

        # Market phase from M5 structure: trending / ranging / compression / breakout
        market_phase = self._detect_market_phase(candles_m5, h1_structure)

        # Exhaustion risk: detect late-trend signals from H1
        exhaustion_risk = self._detect_exhaustion(candles_m5, h1_structure)

        # EMA alignment and overextension check on H1
        ema_alignment, overextended = self._ema_check(candles_h1)

        # Spread + expected slippage estimation
        # Priority: pre-fetched tick (lock-safe, from async path) > connector fallback (legacy/tests)
        spread_pips = 0.0
        expected_slippage_points = 0.0
        tick_price = None
        bid = 0.0
        ask = 0.0
        tick: dict[str, Any] | None = prefetched_tick
        if tick is None and connector is not None:
            try:
                tick = connector.symbol_tick(symbol)
            except Exception:
                tick = None
        if tick is not None:
            try:
                bid = float(tick.get("bid", 0.0) or 0.0)
                ask = float(tick.get("ask", 0.0) or 0.0)
                if bid > 0 and ask > 0:
                    tick_price = (bid + ask) / 2.0
            except Exception:
                pass

        last_m1_close = float(candles_m1[-1].get("close", 0.0) or 0.0) if candles_m1 else 0.0
        slippage_pct = 0.0
        if tick_price and last_m1_close > 0:
            slippage_pct = (abs(tick_price - last_m1_close) / tick_price) * 100.0
            expected_slippage_points = abs(tick_price - last_m1_close) / point_size if point_size > 0 else 0.0

        # Spread check — percentage-based, per asset class, with tolerance levels.
        spread_exceeded = False
        spread_pct = 0.0
        if bid > 0 and ask > 0:
            mid_price = (bid + ask) / 2.0
            raw_spread = ask - bid
            spread_pct = (raw_spread / mid_price) * 100.0 if mid_price > 0 else 0.0
            spread_pips = raw_spread / pip_size if pip_size > 0 else 0.0  # for logging

            asset_class = _classify_asset(symbol, symbol_spec)
            level = cfg.spread_tolerance
            threshold_pct = cfg.spread_thresholds.get(level, cfg.spread_thresholds.get("medium", {})).get(asset_class, 0.10)
            spread_exceeded = spread_pct > threshold_pct

        if spread_exceeded:
            reasons.append(f"spread_exceeded:{spread_pct:.4f}%>{threshold_pct:.4f}%")
        if slippage_pct > cfg.max_slippage_pct:
            reasons.append(
                f"slippage_exceeded:{slippage_pct:.4f}%>{cfg.max_slippage_pct:.4f}%"
            )

        # Stale feed gate from M1 latest candle timestamp
        stale_feed = self._is_stale(candles_m1, cfg.stale_feed_seconds)
        if stale_feed:
            reasons.append("stale_feed")

        # No-trade regime: only extreme low-volatility blocks — H1 neutral is context
        # (used upstream in trader/service.py for setup filtering), never a hard gate.
        no_trade_regime = volatility_regime == "very_low"
        if no_trade_regime:
            reasons.append("no_trade_regime")

        # M5 ranging is useful context, but by itself it should not kill the symbol.
        # Selection becomes stricter downstream in trader/service.py.
        if market_phase == "ranging":
            warnings.append("m5_ranging")
        elif market_phase in {"pullback_bull", "pullback_bear"}:
            warnings.append(market_phase)

        # Overextension gate: price too far from EMA20 → chasing
        if overextended:
            reasons.append("ema_overextended")

        allowed = not reasons

        return FastContext(
            symbol=symbol,
            session_name=session_name,
            h1_bias=h1_bias,
            volatility_regime=volatility_regime,
            spread_pips=round(spread_pips, 4),
            expected_slippage_points=round(expected_slippage_points, 4),
            stale_feed=stale_feed,
            no_trade_regime=no_trade_regime,
            allowed=allowed,
            market_phase=market_phase,
            exhaustion_risk=exhaustion_risk,
            reasons=reasons,
            warnings=warnings,
            details={
                "h1_trend": trend,
                "m1_bars": len(candles_m1),
                "m5_bars": len(candles_m5),
                "h1_bars": len(candles_h1),
                "ema_alignment": ema_alignment,
                "overextended": overextended,
                "context_warnings": list(warnings),
            },
        )

    @staticmethod
    def _volatility_regime(candles: list[dict[str, Any]]) -> str:
        if len(candles) < 12:
            return "unknown"
        sample = candles[-24:]
        ranges: list[float] = []
        bodies: list[float] = []
        for candle in sample:
            high = float(candle.get("high", 0.0) or 0.0)
            low = float(candle.get("low", 0.0) or 0.0)
            open_price = float(candle.get("open", 0.0) or 0.0)
            close = float(candle.get("close", 0.0) or 0.0)
            if high <= 0 or low <= 0:
                continue
            ranges.append(max(0.0, high - low))
            bodies.append(abs(close - open_price))
        if not ranges or not bodies:
            return "unknown"
        avg_range = sum(ranges) / len(ranges)
        avg_body = sum(bodies) / len(bodies)
        if avg_body <= 0:
            return "very_low"
        ratio = avg_range / avg_body
        if ratio < 1.6:
            return "very_low"
        if ratio < 2.2:
            return "low"
        if ratio < 3.5:
            return "normal"
        return "high"

    @staticmethod
    def _is_stale(candles: list[dict[str, Any]], stale_seconds: int) -> bool:
        if not candles:
            return True
        ts_raw = str(candles[-1].get("timestamp", "")).strip()
        if not ts_raw:
            return True
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            return True
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > float(max(5, stale_seconds))

    @staticmethod
    def _detect_market_phase(candles_m5: list[dict[str, Any]], h1_structure: dict[str, Any]) -> str:
        """Classify M5 market phase: trending, ranging, compression, breakout.

        Uses M5 swing range contraction and H1 BOS/CHoCH to classify.
        """
        if len(candles_m5) < 30:
            return "unknown"

        # Check for recent BOS on M5 (breakout)
        m5_struct = detect_market_structure(candles_m5[-80:], window=2)
        last_bos = m5_struct.get("last_bos") if isinstance(m5_struct.get("last_bos"), dict) else None

        # Range detection: compare first-half range to second-half range on M5
        half = len(candles_m5) // 2
        first_half = candles_m5[-60: -30] if len(candles_m5) >= 60 else candles_m5[:half]
        second_half = candles_m5[-30:]

        def _half_range(candles: list[dict[str, Any]]) -> float:
            highs = [float(c.get("high", 0.0) or 0.0) for c in candles]
            lows = [float(c.get("low", 0.0) or 0.0) for c in candles]
            valid_h = [h for h in highs if h > 0]
            valid_l = [lo for lo in lows if lo > 0]
            if not valid_h or not valid_l:
                return 0.0
            return max(valid_h) - min(valid_l)

        range_1 = _half_range(first_half)
        range_2 = _half_range(second_half)

        recent = candles_m5[-12:]
        recent_closes = [float(c.get("close", 0.0) or 0.0) for c in recent]
        recent_highs = [float(c.get("high", 0.0) or 0.0) for c in recent]
        recent_lows = [float(c.get("low", 0.0) or 0.0) for c in recent]
        valid_highs = [h for h in recent_highs if h > 0]
        valid_lows = [lo for lo in recent_lows if lo > 0]
        recent_range = (max(valid_highs) - min(valid_lows)) if valid_highs and valid_lows else 0.0
        recent_delta = (
            recent_closes[-1] - recent_closes[0]
            if len(recent_closes) >= 2 and min(recent_closes) > 0
            else 0.0
        )
        directional_progress = (abs(recent_delta) / recent_range) if recent_range > 0 else 0.0

        # Compression: second half range < 60% of first half
        if range_1 > 0 and range_2 < range_1 * 0.6:
            return "compression"

        # Breakout: fresh BOS within last 10 candles
        if last_bos:
            bos_idx = int(last_bos.get("index", 0) or 0)
            if bos_idx >= len(candles_m5[-80:]) - 10:
                return "breakout"

        # Ranging: H1 trend is "ranging" AND M5 shows no strong directional progress
        h1_trend = str(h1_structure.get("trend", "ranging"))
        m5_trend = str(m5_struct.get("trend", "ranging"))
        if m5_trend == "ranging":
            if h1_trend == "bullish":
                if recent_delta > 0 and directional_progress >= 0.35:
                    return "trending"
                if recent_delta < 0 and directional_progress >= 0.25:
                    return "pullback_bull"
            elif h1_trend == "bearish":
                if recent_delta < 0 and directional_progress >= 0.35:
                    return "trending"
                if recent_delta > 0 and directional_progress >= 0.25:
                    return "pullback_bear"
        if h1_trend == "ranging" and m5_trend == "ranging":
            return "ranging"
        if m5_trend == "ranging":
            return "ranging"
        if h1_trend == "bullish" and recent_delta < 0 and directional_progress >= 0.30:
            return "pullback_bull"
        if h1_trend == "bearish" and recent_delta > 0 and directional_progress >= 0.30:
            return "pullback_bear"

        return "trending"

    @staticmethod
    def _detect_exhaustion(candles_m5: list[dict[str, Any]], h1_structure: dict[str, Any]) -> str:
        """Detect exhaustion/late signal risk.

        High exhaustion = mature trend with weakening momentum — new entries
        are likely near the end of the move.
        """
        if len(candles_m5) < 30:
            return "low"

        # Count directional candles in last 30 M5 bars
        sample = candles_m5[-30:]
        bull_count = sum(1 for c in sample if float(c.get("close", 0) or 0) > float(c.get("open", 0) or 0))
        bear_count = len(sample) - bull_count
        dominant_pct = max(bull_count, bear_count) / len(sample)

        # Weakening bodies: compare avg body of last 10 vs previous 20
        def _avg_body(candles: list[dict[str, Any]]) -> float:
            bodies = [abs(float(c.get("close", 0) or 0) - float(c.get("open", 0) or 0)) for c in candles]
            return sum(bodies) / len(bodies) if bodies else 0.0

        recent_body = _avg_body(sample[-10:])
        earlier_body = _avg_body(sample[:-10])

        # H1 CHoCH detected = structural exhaustion
        h1_choch = h1_structure.get("last_choch") if isinstance(h1_structure.get("last_choch"), dict) else None

        if h1_choch is not None:
            return "high"

        # Strong directional dominance + shrinking bodies = exhaustion
        if dominant_pct > 0.7 and earlier_body > 0 and recent_body < earlier_body * 0.6:
            return "high"

        # Moderate signals
        if dominant_pct > 0.65 and earlier_body > 0 and recent_body < earlier_body * 0.75:
            return "medium"

        return "low"

    @staticmethod
    def _ema_check(candles_h1: list[dict[str, Any]]) -> tuple[str, bool]:
        """Compute EMA20/EMA50 alignment and overextension on H1.

        Returns (alignment, overextended):
         - alignment: "bullish" | "bearish" | "neutral"
         - overextended: True if price > 2% from EMA20
        """
        if len(candles_h1) < 50:
            return "neutral", False

        closes = [float(c.get("close", 0.0) or 0.0) for c in candles_h1[-60:]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 50:
            return "neutral", False

        def _ema(data: list[float], period: int) -> float:
            if len(data) < period:
                return data[-1] if data else 0.0
            k = 2.0 / (period + 1)
            ema = data[0]
            for val in data[1:]:
                ema = val * k + ema * (1 - k)
            return ema

        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        price = closes[-1]

        if ema20 > ema50:
            alignment = "bullish"
        elif ema20 < ema50:
            alignment = "bearish"
        else:
            alignment = "neutral"

        # Overextension: price > 2% from EMA20
        if ema20 > 0:
            distance_pct = abs(price - ema20) / ema20 * 100.0
            overextended = distance_pct > 2.0
        else:
            overextended = False

        return alignment, overextended
