"""
Order Block detection.

An Order Block is the last opposite-direction candle before an impulse move
that produces a Break of Structure (BOS).

Rules:
- Bullish OB: last bearish candle (close < open) immediately before a
  sustained bullish impulse that breaks above a prior swing high.
- Bearish OB: last bullish candle (close > open) immediately before a
  sustained bearish impulse that breaks below a prior swing low.

The OB zone is defined by the body of that candle:
    price_high = max(open, close)   [body top]
    price_low  = min(open, close)   [body bottom]
The full wick range is also stored for reference.
"""
from __future__ import annotations

from typing import Any


def _candle_direction(c: dict[str, Any]) -> str:
    o = float(c.get("open", 0.0) or 0.0)
    cl = float(c.get("close", 0.0) or 0.0)
    if cl > o:
        return "bullish"
    if cl < o:
        return "bearish"
    return "neutral"


def _is_impulse(candles: list[dict[str, Any]], start: int, direction: str, min_candles: int) -> bool:
    """Check if there are at least `min_candles` consecutive same-direction candles from `start`."""
    count = 0
    for j in range(start, min(start + min_candles + 2, len(candles))):
        if _candle_direction(candles[j]) == direction:
            count += 1
        else:
            break
    return count >= min_candles


def _check_mitigated(
    candles: list[dict[str, Any]],
    from_index: int,
    zone_high: float,
    zone_low: float,
    zone_side: str,
) -> bool:
    """Check if an OB/FVG has been mitigated (price revisited and reacted).

    For a bullish zone: mitigated if a candle **closed inside** the zone
    (meaning price tested demand and the zone "absorbed" the order flow).
    For a bearish zone: same logic from above.

    This is a *soft* check — the zone was touched and used.  It does NOT
    mean the zone is invalidated (price broke through completely).
    """
    for k in range(from_index, len(candles)):
        c_close = float(candles[k].get("close", 0.0) or 0.0)
        if zone_side == "bullish":
            # Price came back down into the demand zone
            if zone_low <= c_close <= zone_high:
                return True
        else:
            # Price came back up into the supply zone
            if zone_low <= c_close <= zone_high:
                return True
    return False


def detect_order_blocks(
    candles: list[dict[str, Any]],
    structure: dict[str, Any],
    min_impulse_candles: int = 3,
    max_zones: int = 10,
) -> list[dict[str, Any]]:
    """Detect Order Blocks from OHLC candles and pre-computed structure.

    An OB is valid when the subsequent impulse produces a BOS **or** a CHoCH.
    Each detected OB includes a ``mitigated`` flag set by checking whether
    price has already revisited (closed inside) the zone after formation.

    Returns a list of zone dicts:
        zone_type, price_high, price_low, wick_high, wick_low,
        origin_candle_time, origin_index, impulse_start_index, mitigated
    """
    if len(candles) < min_impulse_candles + 2:
        return []

    zones: list[dict[str, Any]] = []

    # Pre-compute CHoCH info for validation
    choch = structure.get("last_choch")
    choch_idx = int(choch.get("index", -1)) if isinstance(choch, dict) else -1
    choch_dir = str(choch.get("direction", "")) if isinstance(choch, dict) else ""

    # --- Bullish OBs ---
    for i in range(1, len(candles) - min_impulse_candles):
        if _candle_direction(candles[i]) != "bearish":
            continue
        if not _is_impulse(candles, i + 1, "bullish", min_impulse_candles):
            continue
        impulse_start = i + 1
        impulse_high = max(
            float(candles[j].get("high", 0.0) or 0.0)
            for j in range(impulse_start, min(impulse_start + min_impulse_candles + 2, len(candles)))
        )
        earlier_swings = structure.get("swings", [])
        # BOS validation: impulse breaks a prior swing high
        bos_confirmed = any(
            s["type"] == "swing_high" and s["index"] < i and impulse_high > s["price"]
            for s in earlier_swings
        )
        # CHoCH validation: bullish CHoCH occurred near this impulse
        choch_confirmed = (
            choch_dir == "bullish"
            and choch_idx >= impulse_start
            and choch_idx <= impulse_start + min_impulse_candles + 4
        )
        if not (bos_confirmed or choch_confirmed):
            continue

        c = candles[i]
        o = float(c.get("open", 0.0) or 0.0)
        cl = float(c.get("close", 0.0) or 0.0)
        ob_high = max(o, cl)
        ob_low = min(o, cl)

        # Mitigation check: did price close inside the OB zone after formation?
        mitigated = _check_mitigated(candles, impulse_start + min_impulse_candles, ob_high, ob_low, "bullish")

        zones.append({
            "zone_type": "ob_bullish",
            "price_high": ob_high,
            "price_low": ob_low,
            "wick_high": float(c.get("high", ob_high) or ob_high),
            "wick_low": float(c.get("low", ob_low) or ob_low),
            "origin_candle_time": str(c.get("timestamp", "")),
            "origin_index": i,
            "impulse_start_index": impulse_start,
            "mitigated": mitigated,
            "structure_break": "choch" if (choch_confirmed and not bos_confirmed) else "bos",
        })

    # --- Bearish OBs ---
    for i in range(1, len(candles) - min_impulse_candles):
        if _candle_direction(candles[i]) != "bullish":
            continue
        if not _is_impulse(candles, i + 1, "bearish", min_impulse_candles):
            continue
        impulse_start = i + 1
        impulse_low = min(
            float(candles[j].get("low", 0.0) or 0.0)
            for j in range(impulse_start, min(impulse_start + min_impulse_candles + 2, len(candles)))
        )
        earlier_swings = structure.get("swings", [])
        bos_confirmed = any(
            s["type"] == "swing_low" and s["index"] < i and impulse_low < s["price"]
            for s in earlier_swings
        )
        choch_confirmed = (
            choch_dir == "bearish"
            and choch_idx >= impulse_start
            and choch_idx <= impulse_start + min_impulse_candles + 4
        )
        if not (bos_confirmed or choch_confirmed):
            continue

        c = candles[i]
        o = float(c.get("open", 0.0) or 0.0)
        cl = float(c.get("close", 0.0) or 0.0)
        ob_high = max(o, cl)
        ob_low = min(o, cl)

        mitigated = _check_mitigated(candles, impulse_start + min_impulse_candles, ob_high, ob_low, "bearish")

        zones.append({
            "zone_type": "ob_bearish",
            "price_high": ob_high,
            "price_low": ob_low,
            "wick_high": float(c.get("high", ob_high) or ob_high),
            "wick_low": float(c.get("low", ob_low) or ob_low),
            "origin_candle_time": str(c.get("timestamp", "")),
            "origin_index": i,
            "impulse_start_index": impulse_start,
            "mitigated": mitigated,
            "structure_break": "choch" if (choch_confirmed and not bos_confirmed) else "bos",
        })

    # Sort by most recent first, cap at max_zones
    zones.sort(key=lambda z: z["origin_index"], reverse=True)
    return zones[:max_zones]
