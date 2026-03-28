from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from heuristic_mt5_bridge.core.runtime.chart_worker import ChartWorkerUpdate, SymbolChartWorker
from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.shared.symbols.universe import is_operable_symbol, normalize_symbol


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = normalize_symbol(raw)
        if not symbol or symbol in seen or not is_operable_symbol(symbol):
            continue
        ordered.append(symbol)
        seen.add(symbol)
    return ordered


@dataclass(frozen=True)
class WorkerSyncResult:
    created_symbols: list[str]
    removed_symbols: list[str]
    active_symbols: list[str]


class ChartRegistry:
    """Tracks active symbol workers and read-only chart views."""

    def __init__(
        self,
        *,
        market_state: MarketStateService,
        watch_timeframes: list[str],
    ) -> None:
        self.market_state = market_state
        self.watch_timeframes = [str(timeframe).upper() for timeframe in watch_timeframes]
        self._workers: dict[str, SymbolChartWorker] = {}

    def sync_workers(self, subscribed_symbols: Iterable[str]) -> WorkerSyncResult:
        normalized_symbols = _normalize_symbols(subscribed_symbols)
        new_set = set(normalized_symbols)
        current_symbols = list(self._workers.keys())

        removed_symbols: list[str] = []
        for symbol in current_symbols:
            if symbol in new_set:
                continue
            self._workers.pop(symbol, None)
            self.market_state.remove_symbol(symbol)
            removed_symbols.append(symbol)

        created_symbols: list[str] = []
        for symbol in normalized_symbols:
            if symbol in self._workers:
                continue
            self._workers[symbol] = SymbolChartWorker(
                symbol=symbol,
                timeframes=self.watch_timeframes,
                market_state=self.market_state,
            )
            created_symbols.append(symbol)

        return WorkerSyncResult(
            created_symbols=created_symbols,
            removed_symbols=removed_symbols,
            active_symbols=self.active_symbols(),
        )

    def apply_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        poll_duration_ms: float,
        poll_seconds: float,
        server_time_offset_seconds: int,
    ) -> ChartWorkerUpdate | None:
        symbol = normalize_symbol(str(snapshot.get("symbol", "")))
        if not symbol:
            return None
        worker = self._workers.get(symbol)
        if worker is None:
            return None
        return worker.apply_snapshot(
            snapshot,
            poll_duration_ms=poll_duration_ms,
            poll_seconds=poll_seconds,
            server_time_offset_seconds=server_time_offset_seconds,
        )

    def active_symbols(self) -> list[str]:
        return list(self._workers.keys())

    def worker_count(self) -> int:
        return len(self._workers)

    def feed_status_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for worker in self._workers.values():
            rows.extend(worker.feed_rows())
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def state_summaries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for worker in self._workers.values():
            rows.extend(worker.state_summaries())
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def chart_contexts(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for worker in self._workers.values():
            rows.extend(worker.chart_contexts())
        rows.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("timeframe", ""))))
        return rows

    def checkpoint_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for worker in self._workers.values():
            rows.extend(worker.checkpoint_rows())
        rows.sort(key=lambda item: (str(item["symbol"]), str(item["timeframe"])))
        return rows

    def workers_status(self) -> list[dict[str, Any]]:
        rows = [worker.status_snapshot() for worker in self._workers.values()]
        rows.sort(key=lambda item: str(item["symbol"]))
        return rows
