"""
Market structure detection: swing points, HH/HL/LH/LL labeling, BOS, CHoCH.

All functions are pure and deterministic. Input is a list of OHLC candle dicts:
    {"timestamp": str, "open": float, "high": float, "low": float, "close": float}
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

def find_swing_points(candles: list[dict[str, Any]], window: int = 3) -> list[dict[str, Any]]:
    """Return swing highs and lows using a pivot window.

    A swing high at index i means candles[i].high is the highest in
    [i-window, i+window].  A swing low is the mirror.

    Returns a list of dicts sorted by index:
        {"type": "swing_high"|"swing_low", "price": float,
         "index": int, "timestamp": str}
    """
    n = len(candles)
    swings: list[dict[str, Any]] = []
    for i in range(window, n - window):
        c = candles[i]
        h = float(c.get("high", 0.0) or 0.0)
        lo = float(c.get("low", 0.0) or 0.0)
        ts = str(c.get("timestamp", ""))

        # Swing high: highest high in [i-window .. i+window]
        is_sh = all(
            h >= float(candles[j].get("high", 0.0) or 0.0)
            for j in range(i - window, i + window + 1)
            if j != i
        )
        # Swing low: lowest low in [i-window .. i+window]
        is_sl = all(
            lo <= float(candles[j].get("low", 0.0) or 0.0)
            for j in range(i - window, i + window + 1)
            if j != i
        )
        if is_sh:
            swings.append({"type": "swing_high", "price": h, "index": i, "timestamp": ts})
        if is_sl:
            swings.append({"type": "swing_low", "price": lo, "index": i, "timestamp": ts})

    # Deduplicate: if same index is both high and low (doji-like), keep both
    seen_idx: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for s in sorted(swings, key=lambda x: x["index"]):
        key = (s["type"], s["index"])
        if key not in seen_idx:
            seen_idx.add(key)
            deduped.append(s)
    return deduped


# ---------------------------------------------------------------------------
# Swing labeling (HH / HL / LH / LL)
# ---------------------------------------------------------------------------

def label_swing_sequence(swings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Label each swing point relative to the previous one of the same type.

    Returns a list of dicts with an additional "label" field:
        "HH", "LH"  (for swing highs)
        "HL", "LL"  (for swing lows)
    """
    labeled: list[dict[str, Any]] = []
    last_high: float | None = None
    last_low: float | None = None

    for s in swings:
        entry = dict(s)
        if s["type"] == "swing_high":
            if last_high is None:
                entry["label"] = "HH"
            elif s["price"] > last_high:
                entry["label"] = "HH"
            else:
                entry["label"] = "LH"
            last_high = s["price"]
        else:  # swing_low
            if last_low is None:
                entry["label"] = "HL"
            elif s["price"] < last_low:
                entry["label"] = "LL"
            else:
                entry["label"] = "HL"
            last_low = s["price"]
        labeled.append(entry)
    return labeled


# ---------------------------------------------------------------------------
# BOS / CHoCH detection
# ---------------------------------------------------------------------------

def _find_bos_choch(
    candles: list[dict[str, Any]],
    labeled: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Detect the most recent BOS and CHoCH events.

    CHoCH includes a ``confirmed`` flag: True when a subsequent BOS in the
    new direction appears after the CHoCH break.  A CHoCH without
    confirmation is an *alert* only (lower weight in scoring).
    """
    if not labeled or not candles:
        return None, None

    highs = [s for s in labeled if s["type"] == "swing_high"]
    lows = [s for s in labeled if s["type"] == "swing_low"]

    last_bos: dict[str, Any] | None = None
    last_choch: dict[str, Any] | None = None

    # BOS bullish: close above the last swing high
    if highs:
        last_sh = highs[-1]
        for i in range(last_sh["index"] + 1, len(candles)):
            c = candles[i]
            close = float(c.get("close", 0.0) or 0.0)
            if close > last_sh["price"]:
                last_bos = {
                    "direction": "bullish",
                    "price": last_sh["price"],
                    "index": i,
                    "timestamp": str(c.get("timestamp", "")),
                    "label": last_sh.get("label", ""),
                }
                break

    # BOS bearish: close below the last swing low
    if lows:
        last_sl = lows[-1]
        for i in range(last_sl["index"] + 1, len(candles)):
            c = candles[i]
            close = float(c.get("close", 0.0) or 0.0)
            if close < last_sl["price"]:
                candidate = {
                    "direction": "bearish",
                    "price": last_sl["price"],
                    "index": i,
                    "timestamp": str(c.get("timestamp", "")),
                    "label": last_sl.get("label", ""),
                }
                if last_bos is None or candidate["index"] > last_bos["index"]:
                    last_bos = candidate
                break

    # CHoCH: first break opposite to the current trend
    recent = labeled[-8:] if len(labeled) >= 8 else labeled
    recent_highs = [s for s in recent if s["type"] == "swing_high"]
    recent_lows = [s for s in recent if s["type"] == "swing_low"]

    bullish_structure = (
        any(s["label"] == "HH" for s in recent_highs)
        and any(s["label"] == "HL" for s in recent_lows)
    )
    bearish_structure = (
        any(s["label"] == "LH" for s in recent_highs)
        and any(s["label"] == "LL" for s in recent_lows)
    )

    if bullish_structure and lows:
        last_hl = next((s for s in reversed(recent_lows) if s["label"] == "HL"), None)
        if last_hl:
            for i in range(last_hl["index"] + 1, len(candles)):
                c = candles[i]
                if float(c.get("close", 0.0) or 0.0) < last_hl["price"]:
                    last_choch = {
                        "direction": "bearish",
                        "price": last_hl["price"],
                        "index": i,
                        "timestamp": str(c.get("timestamp", "")),
                        "confirmed": False,
                    }
                    break

    if bearish_structure and highs:
        last_lh = next((s for s in reversed(recent_highs) if s["label"] == "LH"), None)
        if last_lh:
            for i in range(last_lh["index"] + 1, len(candles)):
                c = candles[i]
                if float(c.get("close", 0.0) or 0.0) > last_lh["price"]:
                    candidate_choch = {
                        "direction": "bullish",
                        "price": last_lh["price"],
                        "index": i,
                        "timestamp": str(c.get("timestamp", "")),
                        "confirmed": False,
                    }
                    if last_choch is None or candidate_choch["index"] > last_choch["index"]:
                        last_choch = candidate_choch
                    break

    # --- CHoCH confirmation: look for a BOS in the new direction after CHoCH ---
    if last_choch is not None:
        choch_dir = str(last_choch.get("direction", ""))
        choch_idx = int(last_choch.get("index", 0))
        # Scan swings that formed AFTER the CHoCH for a follow-through BOS
        post_choch_swings = [s for s in labeled if s["index"] > choch_idx]
        if choch_dir == "bearish":
            # Need a new swing low broken to the downside after CHoCH
            for sw in post_choch_swings:
                if sw["type"] != "swing_low":
                    continue
                for k in range(sw["index"] + 1, len(candles)):
                    if float(candles[k].get("close", 0.0) or 0.0) < sw["price"]:
                        last_choch["confirmed"] = True
                        break
                if last_choch.get("confirmed"):
                    break
        elif choch_dir == "bullish":
            for sw in post_choch_swings:
                if sw["type"] != "swing_high":
                    continue
                for k in range(sw["index"] + 1, len(candles)):
                    if float(candles[k].get("close", 0.0) or 0.0) > sw["price"]:
                        last_choch["confirmed"] = True
                        break
                if last_choch.get("confirmed"):
                    break

    return last_bos, last_choch


# ---------------------------------------------------------------------------
# Premium / Discount midpoint
# ---------------------------------------------------------------------------

def _impulse_bounds(
    labeled: list[dict[str, Any]],
    last_bos: dict[str, Any] | None = None,
    last_choch: dict[str, Any] | None = None,
) -> tuple[float | None, float | None]:
    """Return (impulse_low, impulse_high) for the *relevant* impulse.

    Strategy:
    1. If a BOS or CHoCH exists, find the swing pair that brackets the
       structural break (the impulse that produced it).
    2. Fallback: most recent significant swing high and swing low that
       form a proper range (high > low).
    """
    highs = [s for s in labeled if s["type"] == "swing_high"]
    lows = [s for s in labeled if s["type"] == "swing_low"]

    # Try to find the impulse that produced the most recent structural event
    ref_event = None
    if last_bos and last_choch:
        ref_event = last_bos if last_bos.get("index", 0) >= last_choch.get("index", 0) else last_choch
    elif last_bos:
        ref_event = last_bos
    elif last_choch:
        ref_event = last_choch

    if ref_event is not None:
        ref_idx = int(ref_event.get("index", 0))
        ref_dir = str(ref_event.get("direction", ""))

        if ref_dir == "bullish":
            # Impulse went up: low is the swing low before the break, high is the break level or higher
            relevant_lows = [s for s in lows if s["index"] < ref_idx]
            relevant_highs = [s for s in highs if s["index"] <= ref_idx]
            if relevant_lows and relevant_highs:
                imp_low = relevant_lows[-1]["price"]
                imp_high = max(relevant_highs[-1]["price"], ref_event.get("price", 0.0))
                if imp_high > imp_low:
                    return imp_low, imp_high
        elif ref_dir == "bearish":
            relevant_highs = [s for s in highs if s["index"] < ref_idx]
            relevant_lows = [s for s in lows if s["index"] <= ref_idx]
            if relevant_highs and relevant_lows:
                imp_high = relevant_highs[-1]["price"]
                imp_low = min(relevant_lows[-1]["price"], ref_event.get("price", 0.0))
                if imp_high > imp_low:
                    return imp_low, imp_high

    # Fallback: last swing high and last swing low
    impulse_high: float | None = None
    impulse_low: float | None = None

    if highs:
        impulse_high = highs[-1]["price"]
    if lows:
        impulse_low = lows[-1]["price"]

    if impulse_high is not None and impulse_low is not None and impulse_high < impulse_low:
        impulse_high, impulse_low = impulse_low, impulse_high

    return impulse_low, impulse_high


# ---------------------------------------------------------------------------
# Overall trend
# ---------------------------------------------------------------------------

def _derive_trend(labeled: list[dict[str, Any]]) -> str:
    """Derive overall trend: 'bullish', 'bearish', or 'ranging'."""
    if not labeled:
        return "ranging"
    recent = labeled[-8:] if len(labeled) >= 8 else labeled

    hh_count = sum(1 for s in recent if s.get("label") == "HH")
    hl_count = sum(1 for s in recent if s.get("label") == "HL")
    lh_count = sum(1 for s in recent if s.get("label") == "LH")
    ll_count = sum(1 for s in recent if s.get("label") == "LL")

    bull_score = hh_count + hl_count
    bear_score = lh_count + ll_count

    if bull_score > bear_score + 1:
        return "bullish"
    if bear_score > bull_score + 1:
        return "bearish"
    return "ranging"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_market_structure(
    candles: list[dict[str, Any]],
    window: int = 3,
) -> dict[str, Any]:
    """Detect market structure from a list of OHLC candles.

    Returns a structure dict with:
        trend, swings, swing_labels, last_bos, last_choch,
        last_impulse_high, last_impulse_low, premium_discount_level
    """
    if len(candles) < window * 2 + 1:
        return {
            "trend": "ranging",
            "swings": [],
            "swing_labels": [],
            "last_bos": None,
            "last_choch": None,
            "last_impulse_high": None,
            "last_impulse_low": None,
            "premium_discount_level": None,
        }

    swings = find_swing_points(candles, window=window)
    labeled = label_swing_sequence(swings)
    last_bos, last_choch = _find_bos_choch(candles, labeled)
    trend = _derive_trend(labeled)
    impulse_low, impulse_high = _impulse_bounds(labeled, last_bos, last_choch)

    premium_discount_level: float | None = None
    if impulse_high is not None and impulse_low is not None:
        premium_discount_level = round((impulse_high + impulse_low) / 2.0, 8)

    return {
        "trend": trend,
        "swings": swings,
        "swing_labels": labeled,
        "last_bos": last_bos,
        "last_choch": last_choch,
        "last_impulse_high": impulse_high,
        "last_impulse_low": impulse_low,
        "premium_discount_level": premium_discount_level,
    }
