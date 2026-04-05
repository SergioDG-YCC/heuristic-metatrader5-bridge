from __future__ import annotations

import math
from datetime import datetime, timezone

from heuristic_mt5_bridge.core.correlation.models import AlignmentResult


def _iso_to_epoch(ts: str) -> int | None:
    """Convert an ISO UTC timestamp string to epoch seconds (integer).

    Accepts formats produced by the MT5 connector, e.g.::

        "2026-03-23T08:00:00Z"
        "2026-03-23T08:00:00+00:00"
        "2026-03-23T08:00:00"

    Returns ``None`` on any parse failure.
    """
    text = str(ts or "").strip()
    if not text:
        return None
    # Normalise trailing 'Z' → '+00:00' for fromisoformat (Python < 3.11 compat)
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError, OverflowError):
        return None


def _simple_returns(closes: list[float]) -> list[float]:
    """Compute simple (arithmetic) returns: r[i] = (close[i] - close[i-1]) / close[i-1]."""
    result: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev == 0.0:
            result.append(0.0)
        else:
            result.append((closes[i] - prev) / prev)
    return result


def _log_returns(closes: list[float]) -> list[float]:
    """Compute log returns: r[i] = ln(close[i] / close[i-1])."""
    result: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        curr = closes[i]
        if prev <= 0.0 or curr <= 0.0:
            result.append(0.0)
        else:
            result.append(math.log(curr / prev))
    return result


def align_and_returns(
    candles_a: list[dict],
    candles_b: list[dict],
    *,
    symbol_a: str = "",
    symbol_b: str = "",
    timeframe: str = "",
    return_type: str = "simple",
) -> AlignmentResult | None:
    """Align two candle series by epoch timestamp (inner join) and compute return series.

    Steps:

    1. Parse epoch integers from each candle's ``timestamp`` field.
    2. Find the intersection of epochs (inner join).
    3. Sort by epoch, extract aligned close prices.
    4. Compute return series on the aligned prices.

    Returns ``None`` when:

    * Either input is empty.
    * Fewer than 3 epochs are shared (requires at least 2 returns for Pearson).

    ``AlignmentResult.aligned_count`` is the number of shared close-price bars.
    The return series have ``aligned_count - 1`` elements.
    """
    if not candles_a or not candles_b:
        return None

    # Build epoch → close maps; skip candles with unparseable timestamps or zero closes
    map_a: dict[int, float] = {}
    for candle in candles_a:
        epoch = _iso_to_epoch(str(candle.get("timestamp", "")))
        if epoch is None:
            continue
        try:
            close = float(candle.get("close", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if close > 0.0:
            map_a[epoch] = close

    map_b: dict[int, float] = {}
    for candle in candles_b:
        epoch = _iso_to_epoch(str(candle.get("timestamp", "")))
        if epoch is None:
            continue
        try:
            close = float(candle.get("close", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if close > 0.0:
            map_b[epoch] = close

    if not map_a or not map_b:
        return None

    common_epochs = sorted(set(map_a.keys()) & set(map_b.keys()))
    aligned_count = len(common_epochs)

    # Need at least 3 aligned bars to produce 2 returns (minimum for Pearson)
    if aligned_count < 3:
        return None

    closes_a = [map_a[e] for e in common_epochs]
    closes_b = [map_b[e] for e in common_epochs]

    min_len = min(len(map_a), len(map_b))
    coverage_ratio = aligned_count / min_len if min_len > 0 else 0.0

    if return_type == "log":
        returns_a = _log_returns(closes_a)
        returns_b = _log_returns(closes_b)
    else:
        returns_a = _simple_returns(closes_a)
        returns_b = _simple_returns(closes_b)

    return AlignmentResult(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        timeframe=timeframe,
        returns_a=returns_a,
        returns_b=returns_b,
        aligned_count=aligned_count,
        coverage_ratio=round(coverage_ratio, 4),
    )
