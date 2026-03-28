"""
Fibonacci retracement and extension level calculator.

All computations are pure functions with no side effects.
"""
from __future__ import annotations

RETRACEMENT_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
EXTENSION_RATIOS = [1.272, 1.382, 1.618, 2.0, 2.618]


def calculate_retracements(
    swing_low: float,
    swing_high: float,
) -> list[dict[str, float | str]]:
    """Calculate Fibonacci retracement levels between swing_low and swing_high."""
    span = swing_high - swing_low
    levels = []
    for ratio in RETRACEMENT_RATIOS:
        price = swing_high - span * ratio
        levels.append({"label": str(ratio), "price": round(price, 8)})
    return levels


def calculate_extensions(
    swing_low: float,
    swing_high: float,
    direction: str = "bullish",
) -> list[dict[str, float | str]]:
    """Calculate Fibonacci extension levels beyond swing_high (bullish)
    or below swing_low (bearish)."""
    span = abs(swing_high - swing_low)
    levels = []
    for ratio in EXTENSION_RATIOS:
        if direction == "bullish":
            price = swing_low + span * ratio
        else:
            price = swing_high - span * ratio
        levels.append({"label": str(ratio), "price": round(price, 8)})
    return levels


def fibo_levels_for_structure(
    structure: dict,
) -> dict[str, list[dict[str, float | str]]]:
    """Convenience: compute both retracements and extensions from structure."""
    lo = structure.get("last_impulse_low")
    hi = structure.get("last_impulse_high")
    trend = str(structure.get("trend", "ranging"))

    if lo is None or hi is None or lo >= hi:
        return {"retracements": [], "extensions": [], "swing_low": None, "swing_high": None}

    direction = "bullish" if trend == "bullish" else "bearish"
    return {
        "retracements": calculate_retracements(lo, hi),
        "extensions": calculate_extensions(lo, hi, direction=direction),
        "swing_low": lo,
        "swing_high": hi,
    }


def nearest_fibo_label(
    price: float,
    fibo: dict,
    tolerance_pct: float = 0.3,
) -> str | None:
    """Return the label of the nearest Fibonacci level within tolerance_pct."""
    best_label: str | None = None
    best_dist = float("inf")

    all_levels = fibo.get("retracements", []) + fibo.get("extensions", [])
    for lvl in all_levels:
        ref = float(lvl.get("price", 0.0) or 0.0)
        if ref <= 0:
            continue
        dist_pct = abs(price - ref) / ref * 100
        if dist_pct <= tolerance_pct and dist_pct < best_dist:
            best_dist = dist_pct
            best_label = str(lvl.get("label", ""))

    return best_label
