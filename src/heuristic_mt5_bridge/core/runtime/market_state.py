from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from heuristic_mt5_bridge.shared.time.utc import iso_to_datetime, utc_now_iso

if TYPE_CHECKING:
    from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry


def session_name_from_timestamp(ts: datetime) -> str:
    hour = ts.hour
    if 7 <= hour < 13:
        return "london"
    if 13 <= hour < 17:
        return "overlap"
    if 17 <= hour < 23:
        return "new_york"
    # 23:00-06:59 UTC → tokyo (covers Asia/Pacific including Sydney open)
    return "tokyo"


def trend_from_closes(candles: list[dict[str, Any]], window: int) -> str:
    closes = [float(item["close"]) for item in candles[-window:] if isinstance(item.get("close"), (int, float))]
    if len(closes) < 2:
        return "unclear"
    if closes[-1] > closes[0]:
        return "up"
    if closes[-1] < closes[0]:
        return "down"
    return "flat"


def count_impulses_and_pullbacks(candles: list[dict[str, Any]]) -> tuple[int, int]:
    if len(candles) < 3:
        return 0, 0
    impulse_count = 0
    pullback_count = 0
    prev_close = None
    prev_direction = None
    for candle in candles:
        close = candle.get("close")
        if not isinstance(close, (int, float)):
            continue
        if prev_close is None:
            prev_close = float(close)
            continue
        direction = "up" if close > prev_close else "down" if close < prev_close else "flat"
        if direction == "flat":
            prev_close = float(close)
            continue
        if prev_direction and direction != prev_direction:
            pullback_count += 1
        else:
            impulse_count += 1
        prev_close = float(close)
        prev_direction = direction
    return impulse_count, pullback_count


def merge_candles(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], max_bars: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candle in existing + incoming:
        timestamp = str(candle.get("timestamp", "")).strip()
        if timestamp:
            merged[timestamp] = candle
    return [merged[key] for key in sorted(merged.keys())][-max_bars:]


@dataclass(frozen=True)
class MarketStateKey:
    symbol: str
    timeframe: str

    @property
    def value(self) -> str:
        return f"{self.symbol.upper()}::{self.timeframe.upper()}"


class MarketStateService:
    def __init__(self, max_bars: int = 300, spec_registry: SymbolSpecRegistry | None = None) -> None:
        self.max_bars = max_bars
        self._spec_registry = spec_registry
        self._states: dict[str, dict[str, Any]] = {}

    @staticmethod
    def key(symbol: str, timeframe: str) -> MarketStateKey:
        return MarketStateKey(symbol=str(symbol).upper(), timeframe=str(timeframe).upper())

    def ingest_snapshot(self, snapshot: dict[str, Any], source: str = "live") -> dict[str, Any]:
        symbol = str(snapshot.get("symbol", "")).upper()
        timeframe = str(snapshot.get("timeframe", "")).upper()
        key = self.key(symbol, timeframe).value
        incoming = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), list) else []
        state = self._states.setdefault(
            key,
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": deque(maxlen=self.max_bars),
                "bootstrap_source": source,
                "indicator_enrichment": {},
            },
        )
        merged = merge_candles(list(state["candles"]), incoming, self.max_bars)
        state["candles"] = deque(merged, maxlen=self.max_bars)
        state["last_snapshot"] = snapshot
        state["last_snapshot_at"] = snapshot.get("created_at", utc_now_iso())
        state["last_source"] = source
        state["updated_at"] = utc_now_iso()
        return self.build_chart_context(symbol, timeframe) or {}

    def ingest_indicator_snapshot(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(payload.get("symbol", "")).upper()
        timeframe = str(payload.get("timeframe", "")).upper()
        key = self.key(symbol, timeframe).value
        state = self._states.get(key)
        if not state:
            return None
        indicator_values = payload.get("indicator_values") if isinstance(payload.get("indicator_values"), dict) else {}
        state["indicator_enrichment"] = {
            "status": "ready",
            "request_id": payload.get("request_id", ""),
            "computed_at": payload.get("computed_at", ""),
            "source": payload.get("source", ""),
            "indicator_values": indicator_values,
        }
        state["updated_at"] = utc_now_iso()
        return self.query(symbol, timeframe, "state_summary")

    def bootstrap_snapshots(self, snapshots: list[dict[str, Any]], source: str = "bootstrap") -> dict[str, int]:
        counts: dict[str, int] = {}
        for snapshot in snapshots:
            key = self.key(snapshot.get("symbol", ""), snapshot.get("timeframe", "")).value
            self.ingest_snapshot(snapshot, source=source)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def build_chart_context(self, symbol: str, timeframe: str, *, pip_size: float | None = None) -> dict[str, Any] | None:
        if pip_size is None and self._spec_registry is not None:
            pip_size = self._spec_registry.pip_size(symbol)
        key = self.key(symbol, timeframe).value
        state = self._states.get(key)
        if not state:
            return None
        snapshot = state.get("last_snapshot")
        candles = list(state.get("candles", []))
        enrichment = state.get("indicator_enrichment") if isinstance(state.get("indicator_enrichment"), dict) else {}
        if not isinstance(snapshot, dict) or not candles:
            return None

        now_dt = iso_to_datetime(str(snapshot.get("created_at", ""))) or datetime.now(timezone.utc)
        closes = [float(item["close"]) for item in candles if isinstance(item.get("close"), (int, float))]
        highs = [float(item["high"]) for item in candles if isinstance(item.get("high"), (int, float))]
        lows = [float(item["low"]) for item in candles if isinstance(item.get("low"), (int, float))]
        current_bid = float(snapshot.get("bid", 0.0) or 0.0)
        structure = snapshot.get("structure") if isinstance(snapshot.get("structure"), dict) else {}
        short_trend = trend_from_closes(candles, 12)
        medium_trend = trend_from_closes(candles, 36)
        impulse_count, pullback_count = count_impulses_and_pullbacks(candles[-40:])
        session = session_name_from_timestamp(now_dt)
        same_day_candles = [
            item for item in candles if (iso_to_datetime(str(item.get("timestamp", ""))) or now_dt).date() == now_dt.date()
        ]
        day_high = max((float(item["high"]) for item in same_day_candles if isinstance(item.get("high"), (int, float))), default=current_bid)
        day_low = min((float(item["low"]) for item in same_day_candles if isinstance(item.get("low"), (int, float))), default=current_bid)
        session_candles = [
            item for item in same_day_candles if session_name_from_timestamp(iso_to_datetime(str(item.get("timestamp", ""))) or now_dt) == session
        ]
        session_high = max((float(item["high"]) for item in session_candles if isinstance(item.get("high"), (int, float))), default=day_high)
        session_low = min((float(item["low"]) for item in session_candles if isinstance(item.get("low"), (int, float))), default=day_low)
        range_size = (max(highs) - min(lows)) if highs and lows else 0.0
        bodies = [
            abs(float(item.get("close", 0.0)) - float(item.get("open", 0.0)))
            for item in candles
            if isinstance(item.get("close"), (int, float)) and isinstance(item.get("open"), (int, float))
        ]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.0
        volatility_regime = "normal"
        if avg_body > 0 and range_size > avg_body * 20:
            volatility_regime = "high"
        elif avg_body > 0 and range_size < avg_body * 8:
            volatility_regime = "low"

        market_phase = "unknown"
        if short_trend == "down" and medium_trend == "down":
            market_phase = "impulse_down" if pullback_count <= impulse_count else "pullback_down"
        elif short_trend == "up" and medium_trend == "up":
            market_phase = "impulse_up" if pullback_count <= impulse_count else "pullback_up"
        elif structure.get("market_regime") == "range":
            market_phase = "range"
        elif structure.get("retest_state") == "confirmed":
            market_phase = "retest"
        elif structure.get("last_breakout_direction") in {"up", "down"}:
            market_phase = "breakout"
        elif structure.get("market_regime") == "compression":
            market_phase = "compression"

        structure_state = str(structure.get("market_regime", "unknown"))
        if structure_state not in {"trend_up", "trend_down", "range", "transition"}:
            structure_state = "transition" if short_trend != medium_trend else "unknown"

        breakout_dir = str(structure.get("last_breakout_direction", "none"))
        breakout_state = "none"
        breakout_strength = float(structure.get("breakout_strength", 0.0) or 0.0)
        if breakout_dir == "up":
            breakout_state = "confirmed_up" if breakout_strength >= 0.35 else "attempt_up"
        elif breakout_dir == "down":
            breakout_state = "confirmed_down" if breakout_strength >= 0.35 else "attempt_down"

        retest_state = str(structure.get("retest_state", "none"))
        if retest_state not in {"none", "pending", "confirmed", "failed"}:
            retest_state = "none"

        extension_state = "not_extended"
        if closes:
            recent_span = abs(closes[-1] - closes[max(0, len(closes) - 10)])
            if avg_body > 0 and recent_span > avg_body * 8:
                extension_state = "highly_extended"
            elif avg_body > 0 and recent_span > avg_body * 4:
                extension_state = "moderately_extended"

        late_signal_risk = "low"
        if breakout_state.startswith("confirmed") and extension_state == "highly_extended":
            late_signal_risk = "high"
        elif extension_state == "moderately_extended" or pullback_count == 0:
            late_signal_risk = "medium"

        compression_state = "none"
        if structure.get("market_regime") == "compression":
            compression_state = "active"
        elif structure.get("market_regime") == "expansion":
            compression_state = "released"
        elif range_size and avg_body and range_size < avg_body * 10:
            compression_state = "building"

        pattern_stack = [str(structure.get("pattern_hypothesis", "none"))]
        if breakout_state != "none":
            pattern_stack.append(breakout_state)
        if retest_state != "none":
            pattern_stack.append(f"retest:{retest_state}")

        return {
            "schema_version": "1.0.0",
            "context_id": f"context_{symbol.lower()}_{timeframe.lower()}",
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "symbol": symbol,
            "timeframe": timeframe,
            "generated_at": utc_now_iso(),
            "window_bars": len(candles),
            "session": session,
            "short_trend": short_trend,
            "medium_trend": medium_trend,
            "market_phase": market_phase,
            "impulse_count": impulse_count,
            "pullback_count": pullback_count,
            "last_confirmed_swing_high": float(structure.get("range_high", day_high) or day_high),
            "last_confirmed_swing_low": float(structure.get("range_low", day_low) or day_low),
            "distance_to_session_high_pips": round((session_high - current_bid) / pip_size, 2) if pip_size else None,
            "distance_to_session_low_pips": round((current_bid - session_low) / pip_size, 2) if pip_size else None,
            "distance_to_day_high_pips": round((day_high - current_bid) / pip_size, 2) if pip_size else None,
            "distance_to_day_low_pips": round((current_bid - day_low) / pip_size, 2) if pip_size else None,
            "structure_state": structure_state,
            "breakout_state": breakout_state,
            "retest_state": retest_state,
            "late_signal_risk": late_signal_risk,
            "extension_state": extension_state,
            "compression_state": compression_state,
            "volatility_regime": volatility_regime,
            "pattern_stack": pattern_stack[:10],
            "indicator_enrichment": {
                "status": enrichment.get("status", "missing"),
                "request_id": enrichment.get("request_id", ""),
                "computed_at": enrichment.get("computed_at", ""),
                "source": enrichment.get("source", ""),
                "indicator_values": enrichment.get("indicator_values", {}) if isinstance(enrichment.get("indicator_values"), dict) else {},
            },
            "notes": f"market_state derived from {len(candles)} buffered candles",
        }

    def get_candles(self, symbol: str, timeframe: str, bars: int | None = None) -> list[dict[str, Any]]:
        key = self.key(symbol, timeframe).value
        state = self._states.get(key)
        if not state:
            return []
        candles = list(state.get("candles", []))
        if bars is not None and bars > 0:
            candles = candles[-bars:]
        return candles

    def remove(self, symbol: str, timeframe: str) -> bool:
        key = self.key(symbol, timeframe).value
        return self._states.pop(key, None) is not None

    def remove_symbol(self, symbol: str) -> int:
        normalized = str(symbol).upper()
        prefix = f"{normalized}::"
        keys_to_remove = [key for key in self._states.keys() if key.startswith(prefix)]
        for key in keys_to_remove:
            self._states.pop(key, None)
        return len(keys_to_remove)

    def query(self, symbol: str, timeframe: str, query_type: str) -> dict[str, Any] | None:
        context = self.build_chart_context(symbol, timeframe)
        if not context:
            return None
        query_type = str(query_type).lower()
        if query_type == "micro":
            return {
                "symbol": context["symbol"],
                "timeframe": context["timeframe"],
                "query_type": "micro",
                "short_trend": context["short_trend"],
                "extension_state": context["extension_state"],
                "late_signal_risk": context["late_signal_risk"],
                "compression_state": context["compression_state"],
                "window_bars": context["window_bars"],
            }
        if query_type == "short":
            return {
                "symbol": context["symbol"],
                "timeframe": context["timeframe"],
                "query_type": "short",
                "short_trend": context["short_trend"],
                "medium_trend": context["medium_trend"],
                "impulse_count": context["impulse_count"],
                "pullback_count": context["pullback_count"],
                "market_phase": context["market_phase"],
            }
        if query_type == "structure":
            return {
                "symbol": context["symbol"],
                "timeframe": context["timeframe"],
                "query_type": "structure",
                "market_phase": context["market_phase"],
                "structure_state": context["structure_state"],
                "breakout_state": context["breakout_state"],
                "retest_state": context["retest_state"],
                "last_confirmed_swing_high": context["last_confirmed_swing_high"],
                "last_confirmed_swing_low": context["last_confirmed_swing_low"],
            }
        if query_type == "session":
            return {
                "symbol": context["symbol"],
                "timeframe": context["timeframe"],
                "query_type": "session",
                "session": context["session"],
                "distance_to_session_high_pips": context["distance_to_session_high_pips"],
                "distance_to_session_low_pips": context["distance_to_session_low_pips"],
                "distance_to_day_high_pips": context["distance_to_day_high_pips"],
                "distance_to_day_low_pips": context["distance_to_day_low_pips"],
            }
        if query_type == "state_summary":
            enrichment = context.get("indicator_enrichment") if isinstance(context.get("indicator_enrichment"), dict) else {}
            indicator_values = enrichment.get("indicator_values") if isinstance(enrichment.get("indicator_values"), dict) else {}
            return {
                "symbol": context["symbol"],
                "timeframe": context["timeframe"],
                "query_type": "state_summary",
                "market_phase": context["market_phase"],
                "short_trend": context["short_trend"],
                "medium_trend": context["medium_trend"],
                "late_signal_risk": context["late_signal_risk"],
                "volatility_regime": context["volatility_regime"],
                "pattern_stack": context["pattern_stack"],
                "window_bars": context["window_bars"],
                "indicator_enrichment_status": enrichment.get("status", "missing"),
                "indicator_enrichment_at": enrichment.get("computed_at", ""),
                "indicator_summary": {
                    "ema_20": indicator_values.get("ema_20"),
                    "ema_50": indicator_values.get("ema_50"),
                    "rsi_14": indicator_values.get("rsi_14"),
                    "atr_14": indicator_values.get("atr_14"),
                    "macd_main": indicator_values.get("macd_main"),
                    "macd_signal": indicator_values.get("macd_signal"),
                },
            }
        return context

    def bootstrap_status(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for state in self._states.values():
            rows.append(
                {
                    "symbol": state.get("symbol"),
                    "timeframe": state.get("timeframe"),
                    "window_bars": len(state.get("candles", [])),
                    "last_snapshot_at": state.get("last_snapshot_at"),
                    "bootstrap_source": state.get("bootstrap_source", state.get("last_source", "unknown")),
                    "ready_for_scheduler": len(state.get("candles", [])) >= 20,
                    "indicator_enrichment_status": str((state.get("indicator_enrichment") or {}).get("status", "missing")),
                }
            )
        return sorted(rows, key=lambda item: (str(item["symbol"]), str(item["timeframe"])))
