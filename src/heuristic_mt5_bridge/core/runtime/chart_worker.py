from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.infra.mt5.connector import determine_feed_status, estimate_local_clock_drift_ms
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso


def _latest_price_from_snapshot(snapshot: dict[str, Any]) -> float | None:
    candles = snapshot.get("ohlc") if isinstance(snapshot.get("ohlc"), list) else []
    if not candles:
        return None
    last = candles[-1]
    if isinstance(last, dict) and isinstance(last.get("close"), (int, float)):
        return float(last["close"])
    return None


@dataclass(frozen=True)
class ChartWorkerUpdate:
    symbol: str
    timeframe: str
    feed_row: dict[str, Any]
    state_summary: dict[str, Any]
    chart_context: dict[str, Any] | None
    local_clock_drift_ms: float | None


class SymbolChartWorker:
    """Owns symbol-local chart state writes in RAM."""

    def __init__(
        self,
        *,
        symbol: str,
        timeframes: list[str],
        market_state: MarketStateService,
    ) -> None:
        self.symbol = str(symbol).upper()
        self.timeframes = [str(timeframe).upper() for timeframe in timeframes]
        self._timeframe_set = set(self.timeframes)
        self.market_state = market_state
        self._feed_by_timeframe: dict[str, dict[str, Any]] = {}
        self._summary_by_timeframe: dict[str, dict[str, Any]] = {}
        self._chart_context_by_timeframe: dict[str, dict[str, Any]] = {}
        self._updated_at_by_timeframe: dict[str, str] = {}

    def apply_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        poll_duration_ms: float,
        poll_seconds: float,
        server_time_offset_seconds: int,
    ) -> ChartWorkerUpdate | None:
        symbol = str(snapshot.get("symbol", "")).upper()
        timeframe = str(snapshot.get("timeframe", "")).upper()
        if symbol != self.symbol or timeframe not in self._timeframe_set:
            return None

        self.market_state.ingest_snapshot(snapshot, source="connector_ingress")
        state_summary = self.market_state.query(symbol, timeframe, "state_summary") or {}
        chart_context = self.market_state.build_chart_context(symbol, timeframe)
        market_context = snapshot.get("market_context") if isinstance(snapshot.get("market_context"), dict) else {}
        local_clock_drift_ms = estimate_local_clock_drift_ms(
            server_time_offset_seconds,
            str(market_context.get("tick_time_raw", "")),
        )
        feed_row = {
            "symbol": symbol,
            "timeframe": timeframe,
            "last_price": _latest_price_from_snapshot(snapshot),
            "bid": snapshot.get("bid"),
            "ask": snapshot.get("ask"),
            "poll_duration_ms": poll_duration_ms,
            "local_clock_drift_ms": local_clock_drift_ms,
            "clock_warning": abs(local_clock_drift_ms) > 1500 if local_clock_drift_ms is not None else False,
            "updated_at": utc_now_iso(),
            **determine_feed_status(snapshot, poll_seconds),
        }
        self._feed_by_timeframe[timeframe] = feed_row
        self._summary_by_timeframe[timeframe] = state_summary
        if chart_context:
            self._chart_context_by_timeframe[timeframe] = chart_context
        self._updated_at_by_timeframe[timeframe] = utc_now_iso()
        return ChartWorkerUpdate(
            symbol=symbol,
            timeframe=timeframe,
            feed_row=feed_row,
            state_summary=state_summary,
            chart_context=chart_context,
            local_clock_drift_ms=local_clock_drift_ms,
        )

    def feed_rows(self) -> list[dict[str, Any]]:
        rows = [self._feed_by_timeframe[timeframe] for timeframe in self.timeframes if timeframe in self._feed_by_timeframe]
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def state_summaries(self) -> list[dict[str, Any]]:
        rows = [
            self._summary_by_timeframe[timeframe]
            for timeframe in self.timeframes
            if timeframe in self._summary_by_timeframe
        ]
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def chart_contexts(self) -> list[dict[str, Any]]:
        rows = [
            self._chart_context_by_timeframe[timeframe]
            for timeframe in self.timeframes
            if timeframe in self._chart_context_by_timeframe
        ]
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def checkpoint_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for timeframe in self.timeframes:
            feed_row = self._feed_by_timeframe.get(timeframe)
            state_summary = self._summary_by_timeframe.get(timeframe)
            if not feed_row or not state_summary:
                continue
            rows.append(
                {
                    "symbol": self.symbol,
                    "timeframe": timeframe,
                    "feed_row": feed_row,
                    "state_summary": state_summary,
                    "chart_context": self._chart_context_by_timeframe.get(timeframe),
                }
            )
        rows.sort(key=lambda item: (str(item["symbol"]), str(item["timeframe"])))
        return rows

    def status_snapshot(self) -> dict[str, Any]:
        updates = [value for value in self._updated_at_by_timeframe.values() if value]
        return {
            "symbol": self.symbol,
            "timeframes": list(self.timeframes),
            "timeframe_count": len(self.timeframes),
            "ready_timeframes": len(self._feed_by_timeframe),
            "last_updated_at": max(updates) if updates else "",
        }
