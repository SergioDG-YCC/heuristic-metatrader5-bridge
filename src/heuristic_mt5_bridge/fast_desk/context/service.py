from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from heuristic_mt5_bridge.fast_desk.correlation.policy import FastCorrelationPolicy

from heuristic_mt5_bridge.core.runtime.market_state import session_name_from_timestamp
from heuristic_mt5_bridge.infra.storage import runtime_db
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


# Hard gates block execution unconditionally.
_HARD_GATES = frozenset({
    "symbol_closed", "stale_feed", "slippage_exceeded", "spread_exceeded",
    "session_blocked",
})


def _reason_is_hard(reason: str) -> bool:
    """Return True if *reason* matches any hard-gate prefix."""
    tag = reason.split(":")[0]
    return tag in _HARD_GATES


class FastContextService:
    """Build deterministic trading context for FastTraderService.

    Context is evaluated once per scan cycle and reused by setup/trigger/execution.
    HTF = M30 (higher timeframe for directional bias).
    """

    def __init__(self, config: FastContextConfig | None = None, correlation_policy: FastCorrelationPolicy | None = None) -> None:
        self.config = config or FastContextConfig()
        self._correlation_policy = correlation_policy

    def build_context(
        self,
        *,
        symbol: str,
        candles_m1: list[dict[str, Any]],
        candles_m5: list[dict[str, Any]],
        candles_htf: list[dict[str, Any]] | None = None,
        pip_size: float,
        point_size: float,
        connector: Any | None = None,
        prefetched_tick: dict[str, Any] | None = None,
        symbol_spec: dict[str, Any] | None = None,
        db_path: Path | None = None,
        broker_server: str | None = None,
        account_login: int | None = None,
        # Backward compat alias — callers using the old name still work.
        candles_h1: list[dict[str, Any]] | None = None,
        open_positions: list[dict[str, Any]] | None = None,
    ) -> FastContext:
        # Resolve HTF candles: prefer explicit candles_htf, fall back to legacy candles_h1
        htf = candles_htf if candles_htf is not None else (candles_h1 or [])
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

        # HTF (M30) directional bias
        htf_structure = detect_market_structure(htf[-160:], window=3) if len(htf) >= 20 else {}
        trend = str(htf_structure.get("trend", "ranging"))
        htf_bias = "neutral"
        if trend == "bullish":
            htf_bias = "buy"
        elif trend == "bearish":
            htf_bias = "sell"

        # Volatility regime from M5 range/body ratio
        volatility_regime = self._volatility_regime(candles_m5)

        # Market phase from M5 structure ONLY (Phase 3: no HTF dependency)
        market_phase = self._detect_market_phase(candles_m5)

        # Exhaustion risk: detect late-trend signals from M5 body weakening
        exhaustion_risk = self._detect_exhaustion(candles_m5, htf_structure)

        # EMA alignment and overextension check on HTF (M30), ATR-aware threshold
        ema_alignment, overextended, ema_distance_atr = self._ema_check(htf)

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

        # ------- SOFT context (informational, never blocks) -------
        no_trade_regime = volatility_regime == "very_low"
        if no_trade_regime:
            warnings.append("no_trade_regime")

        if market_phase == "ranging":
            warnings.append("m5_ranging")
        elif market_phase in {"pullback_bull", "pullback_bear"}:
            warnings.append(market_phase)

        if overextended:
            warnings.append("ema_overextended")

        smc_context = self._load_smc_context(
            db_path=db_path,
            broker_server=broker_server,
            account_login=account_login,
            symbol=symbol,
        )

        # Phase 1: only HARD gates block execution
        allowed = not any(_reason_is_hard(r) for r in reasons)

        details: dict[str, Any] = {
            "htf_trend": trend,
            "m1_bars": len(candles_m1),
            "m5_bars": len(candles_m5),
            "htf_bars": len(htf),
            "ema_alignment": ema_alignment,
            "overextended": overextended,
            "ema_distance_atr": round(ema_distance_atr, 4),
            "context_warnings": list(warnings),
            "smc_bias": smc_context["smc_bias"],
            "smc_thesis_state": smc_context["smc_thesis_state"],
            "smc_htf_zones": smc_context["smc_htf_zones"],
            "smc_data_freshness_seconds": smc_context["smc_data_freshness_seconds"],
        }

        if self._correlation_policy is not None:
            details["correlation"] = self._correlation_policy.build_details(symbol)
            if open_positions and htf_bias in ("buy", "sell"):
                conflict, conflict_reason = self._correlation_policy.check_entry_conflict(
                    symbol, htf_bias, open_positions
                )
                if conflict:
                    warnings.append(f"correlation_conflict:{conflict_reason}")

        return FastContext(
            symbol=symbol,
            session_name=session_name,
            h1_bias=htf_bias,
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
            details=details,
        )

    @staticmethod
    def _parse_iso8601(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _load_smc_context(
        self,
        *,
        db_path: Path | None,
        broker_server: str | None,
        account_login: int | None,
        symbol: str,
    ) -> dict[str, Any]:
        neutral = {
            "smc_bias": "neutral",
            "smc_thesis_state": "neutral",
            "smc_htf_zones": [],
            "smc_data_freshness_seconds": None,
        }
        if db_path is None or not broker_server or account_login is None:
            return neutral
        try:
            rows = runtime_db.load_active_smc_thesis(
                db_path,
                broker_server=str(broker_server),
                account_login=int(account_login),
                symbol=symbol,
            )
        except Exception:
            return neutral
        if not rows:
            return neutral
        row = rows[0]
        updated_at = self._parse_iso8601(row.get("updated_at"))
        freshness = None
        if updated_at is not None:
            freshness = max(0.0, (datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds())
        prepared = row.get("prepared_zones")
        raw_watch_levels = row.get("watch_levels")
        zones: list[dict[str, Any]] = []
        if isinstance(raw_watch_levels, list):
            for item in raw_watch_levels:
                if not isinstance(item, dict):
                    continue
                high = item.get("price_high", item.get("high"))
                low = item.get("price_low", item.get("low"))
                if high is None and low is None:
                    level = item.get("price", item.get("level"))
                    if level is not None:
                        item = dict(item)
                        item["price_high"] = level
                        item["price_low"] = level
                zones.append(item)
        if not zones and isinstance(prepared, list):
            for item in prepared:
                if isinstance(item, dict):
                    zones.append(item)
        bias = str(row.get("bias", "neutral") or "neutral").lower()
        if bias not in {"buy", "sell"}:
            bias = "neutral"
        state = str(row.get("status", "neutral") or "neutral").lower()
        return {
            "smc_bias": bias,
            "smc_thesis_state": state,
            "smc_htf_zones": zones,
            "smc_data_freshness_seconds": round(freshness, 1) if freshness is not None else None,
        }

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
    def _detect_market_phase(candles_m5: list[dict[str, Any]]) -> str:
        """Classify M5 market phase using ONLY M5 data (Phase 3: no HTF dependency).

        Returns: trending, ranging, compression, breakout, pullback_bull, pullback_bear.
        """
        if len(candles_m5) < 30:
            return "unknown"

        # M5 structure
        m5_struct = detect_market_structure(candles_m5[-80:], window=2)
        m5_trend = str(m5_struct.get("trend", "ranging"))
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

        # M5-only ranging / pullback classification
        if m5_trend == "ranging":
            if recent_delta > 0 and directional_progress >= 0.35:
                return "trending"
            if recent_delta < 0 and directional_progress >= 0.35:
                return "trending"
            # Detect pullbacks purely from M5 delta direction vs trend
            if m5_trend == "ranging" and directional_progress >= 0.25:
                if recent_delta < 0:
                    return "pullback_bear"
                if recent_delta > 0:
                    return "pullback_bull"
            return "ranging"

        # Trending M5 with counter-delta = pullback
        if m5_trend == "bullish" and recent_delta < 0 and directional_progress >= 0.30:
            return "pullback_bull"
        if m5_trend == "bearish" and recent_delta > 0 and directional_progress >= 0.30:
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
    def _ema_check(candles_htf: list[dict[str, Any]], *, overext_k: float = 1.2) -> tuple[str, bool, float]:
        """Compute EMA20/EMA50 alignment and ATR-aware overextension on HTF (M30).

        Returns (alignment, overextended, ema_distance_atr):
         - alignment: "bullish" | "bearish" | "neutral"
         - overextended: True if |price - EMA20| > ATR_HTF * k
         - ema_distance_atr: ratio of distance-to-EMA20 / ATR (for diagnostics)
        """
        if len(candles_htf) < 50:
            return "neutral", False, 0.0

        closes = [float(c.get("close", 0.0) or 0.0) for c in candles_htf[-60:]]
        closes = [c for c in closes if c > 0]
        if len(closes) < 50:
            return "neutral", False, 0.0

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

        # Phase 2: ATR-aware overextension (replaces fixed 2% threshold)
        ema_distance_atr = 0.0
        overextended = False
        if ema20 > 0:
            distance = abs(price - ema20)
            # Compute ATR on the same HTF candles
            atr_htf = 0.0
            trs: list[float] = []
            slice_htf = candles_htf[-60:]
            for idx in range(1, len(slice_htf)):
                h = float(slice_htf[idx].get("high", 0.0) or 0.0)
                lo = float(slice_htf[idx].get("low", 0.0) or 0.0)
                pc = float(slice_htf[idx - 1].get("close", 0.0) or 0.0)
                if h > 0 and lo > 0 and pc > 0:
                    trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
            if trs:
                window = trs[-14:] if len(trs) >= 14 else trs
                atr_htf = sum(window) / len(window)
            if atr_htf > 0:
                ema_distance_atr = distance / atr_htf
                overextended = distance > atr_htf * overext_k

        return alignment, overextended, ema_distance_atr
