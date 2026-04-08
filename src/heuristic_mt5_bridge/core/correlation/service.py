from __future__ import annotations

import asyncio
import time as _time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from heuristic_mt5_bridge.core.correlation.aligner import align_and_returns
from heuristic_mt5_bridge.core.correlation.models import (
    CorrelationMatrixSnapshot,
    CorrelationPairValue,
)
from heuristic_mt5_bridge.shared.time.utc import iso_to_datetime, utc_now_iso

if TYPE_CHECKING:
    from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
    from heuristic_mt5_bridge.core.runtime.subscriptions import SubscriptionManager


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pure Python Pearson correlation coefficient.

    Returns ``None`` when:

    * ``n < 2``
    * ``len(xs) != len(ys)``
    * ``var(xs) <= 0`` (constant series)
    * ``var(ys) <= 0`` (constant series)

    Result is clamped to ``[-1.0, 1.0]`` to guard against floating-point drift.
    Never returns ``0.0`` as a sentinel — only ``None`` conveys "no data".
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)

    if var_x <= 0.0 or var_y <= 0.0:
        return None

    r = cov / (var_x * var_y) ** 0.5
    return max(-1.0, min(1.0, r))


class CorrelationService:
    """Compute and cache Pearson correlation matrices for all subscribed symbol pairs.

    Design principles:

    * **Core only** — delivers raw :class:`CorrelationPairValue` with coefficient and
      coverage metadata.  No trade logic, no classification, no thresholds.
    * **Elastic universe** — reads ``SubscriptionManager.subscribed_universe()`` on
      every refresh cycle so newly subscribed symbols are picked up automatically.
    * **Atomic swap** — ``self._snapshots[tf] = new_snapshot`` replaces the whole
      snapshot; existing callers of ``get_matrix`` always see a consistent view.
    * **NaN policy** — ``coefficient=None`` on insufficient data or zero-variance.
      ``0.0`` is never used as a sentinel.
    * **Source stale / compute stale** are independent dimensions stored on each object.
    """

    def __init__(
        self,
        market_state: MarketStateService,
        subscription_manager: SubscriptionManager,
        *,
        window_bars: int = 50,
        min_coverage_bars: int = 30,
        return_type: str = "simple",
        refresh_seconds: float = 60.0,
        stale_source_seconds: float = 300.0,
        timeframes: list[str] | None = None,
    ) -> None:
        self._market_state = market_state
        self._subscription_manager = subscription_manager
        self._window_bars = max(10, window_bars)
        self._min_coverage_bars = max(5, min_coverage_bars)
        self._return_type = return_type if return_type in ("simple", "log") else "simple"
        self._refresh_seconds = max(10.0, refresh_seconds)
        self._stale_source_seconds = max(10.0, stale_source_seconds)
        self._timeframes: list[str] = [tf.upper() for tf in (timeframes or ["M5", "H1"])]

        # Atomic snapshot dict: timeframe -> CorrelationMatrixSnapshot.
        # Never mutate a snapshot in place — always assign a new one.
        self._snapshots: dict[str, CorrelationMatrixSnapshot] = {}
        self._stop_event: asyncio.Event | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_source_stale(self, symbol: str, timeframe: str) -> bool:
        """Return True if the market data for (symbol, timeframe) is stale."""
        try:
            updated_at = self._market_state.query(symbol, timeframe, "updated_at")
            if updated_at is None:
                return True
            dt = iso_to_datetime(str(updated_at))
            if dt is None:
                return True
            age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            return age > self._stale_source_seconds
        except Exception:
            return True

    def _compute_pair(
        self,
        symbol_a: str,
        symbol_b: str,
        timeframe: str,
    ) -> CorrelationPairValue:
        """Compute Pearson correlation for one (symbol_a, symbol_b, timeframe) triple."""
        candles_a = self._market_state.get_candles(symbol_a, timeframe, bars=self._window_bars)
        candles_b = self._market_state.get_candles(symbol_b, timeframe, bars=self._window_bars)
        source_stale = (
            self._is_source_stale(symbol_a, timeframe)
            or self._is_source_stale(symbol_b, timeframe)
        )
        computed_at = utc_now_iso()

        alignment = align_and_returns(
            candles_a,
            candles_b,
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            timeframe=timeframe,
            return_type=self._return_type,
        )
        if alignment is None:
            return CorrelationPairValue(
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                timeframe=timeframe,
                coefficient=None,
                bars_used=0,
                coverage_ratio=0.0,
                coverage_ok=False,
                source_stale=source_stale,
                computed_at=computed_at,
            )

        coefficient = _pearson(alignment.returns_a, alignment.returns_b)
        coverage_ok = alignment.aligned_count >= self._min_coverage_bars

        return CorrelationPairValue(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            timeframe=timeframe,
            coefficient=coefficient,
            bars_used=alignment.aligned_count,
            coverage_ratio=alignment.coverage_ratio,
            coverage_ok=coverage_ok,
            source_stale=source_stale,
            computed_at=computed_at,
        )

    def _refresh_timeframe(self, timeframe: str) -> CorrelationMatrixSnapshot:
        """Compute a full correlation matrix for all subscribed pairs on one timeframe.

        Only the upper triangle is computed — pairs are stored as (sym_a, sym_b)
        where sym_a < sym_b lexicographically.  ``get_pair`` resolves both orders.
        """
        symbols = [symbol.upper() for symbol in self._subscription_manager.subscribed_universe()]
        pairs: dict[tuple[str, str], CorrelationPairValue] = {}
        computed_at = utc_now_iso()

        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i + 1:]:
                pair_value = self._compute_pair(sym_a, sym_b, timeframe)
                pairs[(sym_a.upper(), sym_b.upper())] = pair_value

        all_bars = [p.bars_used for p in pairs.values() if p.bars_used > 0]
        min_pair_bars = min(all_bars) if all_bars else 0
        all_pairs_coverage_ok = all(p.coverage_ok for p in pairs.values()) if pairs else False

        return CorrelationMatrixSnapshot(
            timeframe=timeframe,
            symbols=symbols,
            pairs=pairs,
            computed_at=computed_at,
            min_pair_bars=min_pair_bars,
            all_pairs_coverage_ok=all_pairs_coverage_ok,
            compute_stale=False,
        )

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_pair(
        self,
        symbol_a: str,
        symbol_b: str,
        timeframe: str,
    ) -> CorrelationPairValue | None:
        """Return the cached :class:`CorrelationPairValue`, or ``None`` before first refresh."""
        snapshot = self._snapshots.get(timeframe.upper())
        if snapshot is None:
            return None
        return snapshot.get_pair(symbol_a, symbol_b)

    def get_matrix(self, timeframe: str) -> CorrelationMatrixSnapshot | None:
        """Return the current atomic snapshot for *timeframe*, or ``None``."""
        return self._snapshots.get(timeframe.upper())

    def get_exposure_relations(
        self,
        symbol: str,
        timeframe: str,
    ) -> list[CorrelationPairValue]:
        """Return all cached pair values that involve *symbol* on *timeframe*."""
        snapshot = self._snapshots.get(timeframe.upper())
        if snapshot is None:
            return []
        sym_upper = symbol.upper()
        return [
            pair
            for (a, b), pair in snapshot.pairs.items()
            if a == sym_upper or b == sym_upper
        ]

    def active_symbols(self) -> list[str]:
        """Return the current subscribed universe."""
        return self._subscription_manager.subscribed_universe()

    # ------------------------------------------------------------------
    # Async loop
    # ------------------------------------------------------------------

    async def refresh_loop(self) -> None:
        """Continuously refresh matrices for all configured timeframes.

        Runs CPU-bound computation in a thread pool via ``asyncio.to_thread`` to
        avoid blocking the event loop.  Each snapshot is atomically replaced after
        computation.  Errors on a single timeframe are silently swallowed to keep
        the loop alive.

        Exits cleanly when the enclosing ``asyncio.TaskGroup`` cancels this task
        (e.g. when ``CoreRuntimeService.shutdown`` is called).
        """
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

        symbols = self.active_symbols()
        print(
            f"[correlation] started"
            f" timeframes={','.join(self._timeframes)}"
            f" window={self._window_bars} bars"
            f" min_coverage={self._min_coverage_bars}"
            f" symbols={len(symbols)}"
            f" refresh={int(self._refresh_seconds)}s",
            flush=True,
        )

        while not self._stop_event.is_set():
            for timeframe in self._timeframes:
                if self._stop_event.is_set():
                    break
                try:
                    _t0 = _time.monotonic()
                    new_snapshot = await asyncio.to_thread(
                        self._refresh_timeframe, timeframe
                    )
                    self._snapshots[timeframe] = new_snapshot  # atomic swap
                    elapsed = _time.monotonic() - _t0
                    total = len(new_snapshot.pairs)
                    ok = sum(1 for p in new_snapshot.pairs.values() if p.coverage_ok)
                    stale = sum(1 for p in new_snapshot.pairs.values() if p.source_stale)
                    print(
                        f"[correlation] {timeframe}"
                        f" pairs={total} coverage_ok={ok} stale={stale}"
                        f" elapsed={elapsed:.1f}s",
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[correlation] {timeframe} ERROR: {exc}", flush=True)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(self._refresh_seconds, 10.0),
                )
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        """Signal the refresh loop to stop (standalone use only)."""
        if self._stop_event is not None:
            self._stop_event.set()
