"""
Liquidity pool detection and sweep detection.

Liquidity pools:
- Buy-side liquidity (BSL): cluster of swing highs / equal highs where stops
  from short sellers accumulate above.
- Sell-side liquidity (SSL): cluster of swing lows / equal lows where stops
  from long buyers accumulate below.
- Equal highs / equal lows: two or more candle extremes within a tolerance.

Sweeps:
A sweep is when price temporarily exceeds a liquidity level with a wick but
closes back on the opposite side, indicating stop hunting.
"""
from __future__ import annotations

from typing import Any


def _equal_levels(
    prices: list[float],
    tolerance_pct: float = 0.05,
) -> list[list[float]]:
    """Group prices that are within tolerance_pct of each other into clusters."""
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters: list[list[float]] = []
    current_cluster = [sorted_prices[0]]

    for price in sorted_prices[1:]:
        ref = current_cluster[0]
        if ref > 0 and abs(price - ref) / ref * 100 <= tolerance_pct:
            current_cluster.append(price)
        else:
            clusters.append(current_cluster)
            current_cluster = [price]
    clusters.append(current_cluster)

    return [c for c in clusters if len(c) >= 2]


def detect_liquidity_pools(
    candles_higher: list[dict[str, Any]],
    candles_lower: list[dict[str, Any]],
    structure: dict[str, Any] | None = None,
    tolerance_pct: float = 0.05,
    max_zones: int = 20,
) -> list[dict[str, Any]]:
    """Detect buy-side and sell-side liquidity pools.

    Uses swing highs/lows from structure (if provided) and equal highs/lows
    detected from equal-level clustering.

    Returns a list of zone dicts:
        zone_type, price_high, price_low, origin_candle_time,
        cluster_count, origin_index
    """
    zones: list[dict[str, Any]] = []

    highs = [
        (i, float(c.get("high", 0.0) or 0.0), str(c.get("timestamp", "")))
        for i, c in enumerate(candles_lower)
        if isinstance(c.get("high"), (int, float))
    ]
    lows = [
        (i, float(c.get("low", 0.0) or 0.0), str(c.get("timestamp", "")))
        for i, c in enumerate(candles_lower)
        if isinstance(c.get("low"), (int, float))
    ]

    high_prices = [h[1] for h in highs]
    low_prices = [lo[1] for lo in lows]

    for cluster in _equal_levels(high_prices, tolerance_pct):
        level = max(cluster)
        margin = level * tolerance_pct / 100
        matching = [(i, p, ts) for i, p, ts in highs if abs(p - level) <= margin]
        if not matching:
            continue
        first_idx = min(m[0] for m in matching)
        last_ts = max((m[2] for m in matching), default="")
        zones.append({
            "zone_type": "equal_highs",
            "price_high": level + margin,
            "price_low": level - margin,
            "origin_candle_time": last_ts,
            "origin_index": first_idx,
            "cluster_count": len(matching),
        })

    for cluster in _equal_levels(low_prices, tolerance_pct):
        level = min(cluster)
        margin = level * tolerance_pct / 100
        matching = [(i, p, ts) for i, p, ts in lows if abs(p - level) <= margin]
        if not matching:
            continue
        first_idx = min(m[0] for m in matching)
        last_ts = max((m[2] for m in matching), default="")
        zones.append({
            "zone_type": "equal_lows",
            "price_high": level + margin,
            "price_low": level - margin,
            "origin_candle_time": last_ts,
            "origin_index": first_idx,
            "cluster_count": len(matching),
        })

    # BSL / SSL from confirmed swing highs/lows (higher TF)
    if isinstance(structure, dict):
        swing_labels = structure.get("swing_labels", [])
        for s in swing_labels:
            price = float(s.get("price", 0.0) or 0.0)
            if price <= 0:
                continue
            margin = price * tolerance_pct / 100
            label = s.get("label", "")
            if s["type"] == "swing_high":
                zones.append({
                    "zone_type": "liquidity_bsl",
                    "price_high": price + margin,
                    "price_low": price - margin,
                    "origin_candle_time": str(s.get("timestamp", "")),
                    "origin_index": int(s.get("index", 0)),
                    "cluster_count": 1,
                    "swing_label": label,
                })
            else:
                zones.append({
                    "zone_type": "liquidity_ssl",
                    "price_high": price + margin,
                    "price_low": price - margin,
                    "origin_candle_time": str(s.get("timestamp", "")),
                    "origin_index": int(s.get("index", 0)),
                    "cluster_count": 1,
                    "swing_label": label,
                })

    zones.sort(key=lambda z: z["origin_index"], reverse=True)
    return zones[:max_zones]


def detect_sweeps(
    candles: list[dict[str, Any]],
    liquidity_zones: list[dict[str, Any]],
    lookback: int = 50,
) -> list[dict[str, Any]]:
    """Detect sweeps of known liquidity zones.

    A sweep of BSL: wick exceeds zone price_high but candle closes below it.
    A sweep of SSL: wick goes below zone price_low but closes above it.

    Each sweep includes ``sweep_quality``: "clean" if the wick barely
    exceeded the level (within 0.15% of the swept level), "deep" otherwise.

    Returns a list of sweep event dicts:
        zone_type (sweep_bsl | sweep_ssl), price_high, price_low,
        sweep_candle_time, sweep_index, origin_zone_type, swept_level,
        sweep_quality
    """
    if not candles or not liquidity_zones:
        return []

    recent_candles = candles[-lookback:]
    offset = len(candles) - len(recent_candles)
    sweeps: list[dict[str, Any]] = []
    taken_zone_keys: set[str] = set()

    for zone in liquidity_zones:
        zone_high = float(zone.get("price_high", 0.0) or 0.0)
        zone_low = float(zone.get("price_low", 0.0) or 0.0)
        z_type = str(zone.get("zone_type", ""))

        is_bsl = z_type in {"liquidity_bsl", "equal_highs"}
        is_ssl = z_type in {"liquidity_ssl", "equal_lows"}

        if not (is_bsl or is_ssl):
            continue

        zone_key = f"{z_type}:{zone_high}:{zone_low}"

        for j, c in enumerate(recent_candles):
            c_high = float(c.get("high", 0.0) or 0.0)
            c_low = float(c.get("low", 0.0) or 0.0)
            c_close = float(c.get("close", 0.0) or 0.0)
            c_ts = str(c.get("timestamp", ""))
            abs_idx = offset + j

            if is_bsl and c_high > zone_high and c_close < zone_high:
                overshoot_pct = (c_high - zone_high) / zone_high * 100 if zone_high > 0 else 0
                quality = "clean" if overshoot_pct <= 0.15 else "deep"
                sweeps.append({
                    "zone_type": "sweep_bsl",
                    "price_high": c_high,
                    "price_low": zone_low,
                    "sweep_candle_time": c_ts,
                    "sweep_index": abs_idx,
                    "origin_zone_type": z_type,
                    "swept_level": zone_high,
                    "sweep_quality": quality,
                })
                taken_zone_keys.add(zone_key)

            if is_ssl and c_low < zone_low and c_close > zone_low:
                overshoot_pct = (zone_low - c_low) / zone_low * 100 if zone_low > 0 else 0
                quality = "clean" if overshoot_pct <= 0.15 else "deep"
                sweeps.append({
                    "zone_type": "sweep_ssl",
                    "price_high": zone_high,
                    "price_low": c_low,
                    "sweep_candle_time": c_ts,
                    "sweep_index": abs_idx,
                    "origin_zone_type": z_type,
                    "swept_level": zone_low,
                    "sweep_quality": quality,
                })
                taken_zone_keys.add(zone_key)

    # Mark liquidity zones as taken (mutates the input list in-place for caller convenience)
    for zone in liquidity_zones:
        z_type = str(zone.get("zone_type", ""))
        zone_high = float(zone.get("price_high", 0.0) or 0.0)
        zone_low = float(zone.get("price_low", 0.0) or 0.0)
        zone_key = f"{z_type}:{zone_high}:{zone_low}"
        zone["taken"] = zone_key in taken_zone_keys

    sweeps.sort(key=lambda s: s["sweep_index"], reverse=True)
    return sweeps
