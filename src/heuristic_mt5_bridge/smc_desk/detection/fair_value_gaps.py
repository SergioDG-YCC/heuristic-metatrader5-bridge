"""
Fair Value Gap (FVG) detection.

A Fair Value Gap is a three-candle pattern where there is an imbalance
between supply and demand, evidenced by a price gap that was never retested.

Detection:
- Bullish FVG:  candles[i-2].high < candles[i].low
- Bearish FVG:  candles[i-2].low > candles[i].high

The origin_candle_time is the timestamp of the middle candle (i-1).
"""
from __future__ import annotations

from typing import Any


def detect_fair_value_gaps(
    candles: list[dict[str, Any]],
    min_gap_ratio: float = 0.1,
    max_zones: int = 20,
) -> list[dict[str, Any]]:
    """Detect Fair Value Gaps in an OHLC candle list.

    min_gap_ratio: gap must be at least this fraction of the average body size
                   to filter out noise.

    Each FVG includes a ``mitigated`` flag: True if price has already closed
    inside the gap zone after its formation (the imbalance was filled).

    Returns a list of zone dicts:
        zone_type, price_high, price_low, origin_candle_time, origin_index,
        gap_size, mitigated
    """
    if len(candles) < 3:
        return []

    bodies = [
        abs(float(c.get("close", 0.0) or 0.0) - float(c.get("open", 0.0) or 0.0))
        for c in candles
        if isinstance(c.get("close"), (int, float)) and isinstance(c.get("open"), (int, float))
    ]
    avg_body = sum(bodies) / len(bodies) if bodies else 0.0
    min_gap = avg_body * min_gap_ratio

    zones: list[dict[str, Any]] = []

    for i in range(2, len(candles)):
        c0 = candles[i - 2]
        c1 = candles[i - 1]  # middle candle — origin
        c2 = candles[i]

        h0 = float(c0.get("high", 0.0) or 0.0)
        h2 = float(c2.get("high", 0.0) or 0.0)
        l0 = float(c0.get("low", 0.0) or 0.0)
        l2 = float(c2.get("low", 0.0) or 0.0)

        # Bullish FVG
        gap_bullish = l2 - h0
        if gap_bullish > min_gap:
            fvg_high = l2
            fvg_low = h0
            mitigated = _check_fvg_mitigated(candles, i + 1, fvg_high, fvg_low)
            zones.append({
                "zone_type": "fvg_bullish",
                "price_high": fvg_high,
                "price_low": fvg_low,
                "origin_candle_time": str(c1.get("timestamp", "")),
                "origin_index": i - 1,
                "gap_size": round(gap_bullish, 8),
                "mitigated": mitigated,
            })

        # Bearish FVG
        gap_bearish = l0 - h2
        if gap_bearish > min_gap:
            fvg_high = l0
            fvg_low = h2
            mitigated = _check_fvg_mitigated(candles, i + 1, fvg_high, fvg_low)
            zones.append({
                "zone_type": "fvg_bearish",
                "price_high": fvg_high,
                "price_low": fvg_low,
                "origin_candle_time": str(c1.get("timestamp", "")),
                "origin_index": i - 1,
                "gap_size": round(gap_bearish, 8),
                "mitigated": mitigated,
            })

    zones.sort(key=lambda z: z["origin_index"], reverse=True)
    return zones[:max_zones]


def _check_fvg_mitigated(
    candles: list[dict[str, Any]],
    from_index: int,
    zone_high: float,
    zone_low: float,
) -> bool:
    """Check if an FVG has been mitigated (price closed inside the gap)."""
    for k in range(from_index, len(candles)):
        c_close = float(candles[k].get("close", 0.0) or 0.0)
        if zone_low <= c_close <= zone_high:
            return True
    return False
