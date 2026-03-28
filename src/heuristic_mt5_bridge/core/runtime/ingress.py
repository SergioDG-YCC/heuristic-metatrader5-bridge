from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from heuristic_mt5_bridge.core.runtime.chart_registry import ChartRegistry
from heuristic_mt5_bridge.core.runtime.subscriptions import SubscriptionManager
from heuristic_mt5_bridge.infra.mt5.connector import MT5Connector


@dataclass
class IngressCycleResult:
    feed_rows: list[dict[str, Any]] = field(default_factory=list)
    state_summaries: list[dict[str, Any]] = field(default_factory=list)
    chart_contexts: list[dict[str, Any]] = field(default_factory=list)
    poll_durations_ms: list[float] = field(default_factory=list)
    clock_drifts_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ConnectorIngress:
    """Single-owner connector ingress that fans out to symbol workers."""

    def __init__(
        self,
        *,
        connector: MT5Connector,
        mt5_call: Callable[..., Awaitable[Any]],
        subscription_manager: SubscriptionManager,
        chart_registry: ChartRegistry,
        watch_timeframes: list[str],
        bars_per_pull: int,
        poll_seconds: float,
    ) -> None:
        self.connector = connector
        self.mt5_call = mt5_call
        self.subscription_manager = subscription_manager
        self.chart_registry = chart_registry
        self.watch_timeframes = [str(timeframe).upper() for timeframe in watch_timeframes]
        self.bars_per_pull = int(bars_per_pull)
        self.poll_seconds = float(poll_seconds)

    async def poll_subscribed_once(self) -> IngressCycleResult:
        result = IngressCycleResult()
        subscribed_symbols = self.subscription_manager.subscribed_universe()
        if not subscribed_symbols or not self.watch_timeframes:
            return result

        for symbol in subscribed_symbols:
            for timeframe in self.watch_timeframes:
                started = time.perf_counter()
                try:
                    snapshot = await self.mt5_call(
                        self.connector.fetch_snapshot,
                        symbol,
                        timeframe,
                        self.bars_per_pull,
                    )
                except Exception as exc:  # noqa: PERF203 - keep symbol/timeframe context
                    result.errors.append(f"{symbol}/{timeframe}: {exc}")
                    continue

                poll_duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
                update = self.chart_registry.apply_snapshot(
                    snapshot,
                    poll_duration_ms=poll_duration_ms,
                    poll_seconds=self.poll_seconds,
                    server_time_offset_seconds=int(getattr(self.connector, "server_time_offset_seconds", 0) or 0),
                )
                if update is None:
                    continue
                result.poll_durations_ms.append(poll_duration_ms)
                if isinstance(update.local_clock_drift_ms, (int, float)):
                    result.clock_drifts_ms.append(float(update.local_clock_drift_ms))

        result.feed_rows = self.chart_registry.feed_status_rows()
        result.state_summaries = self.chart_registry.state_summaries()
        result.chart_contexts = self.chart_registry.chart_contexts()
        return result
