"""
Confluence evaluator for SMC zones.

Takes a zone and surrounding context (structure, Fibonacci, other zones)
and returns a list of named confluences plus a quality_score (0.0-1.0).

Quality score uses **weighted** confluence values so that higher-conviction
signals (sweep + CHoCH, Fib-618, premium/discount) contribute more than
informational ones (fibo_236, fvg_overlap).  The raw score is capped at 1.0
and kept intentionally generous to avoid over-filtering — markets are noisy.
"""
from __future__ import annotations

from typing import Any

from .fibonacci import nearest_fibo_label

# --- Weighted scoring table ---
# Each confluence has a weight (0.0-1.0).  The quality_score is the sum of
# collected weights divided by MAX_WEIGHTED_SCORE, capped at 1.0.
# Higher weights → higher conviction signals per SMC doctrine.
CONFLUENCE_WEIGHTS: dict[str, float] = {
    # Tier-1 (high conviction)
    "sweep_choch_corr": 0.18,
    "bos_confirmed": 0.14,
    "in_discount": 0.13,
    "in_premium": 0.13,
    "fibo_618": 0.12,
    "structure_aligned": 0.12,
    "choch_at_origin": 0.11,
    "choch_confirmed": 0.10,
    "sweep_present": 0.10,
    # Tier-2 (moderate)
    "ob_unmitigated": 0.08,
    "fvg_unmitigated": 0.08,
    "fibo_50": 0.07,
    "fibo_382": 0.06,
    "fibo_786": 0.06,
    "liquidity_above": 0.06,
    "liquidity_below": 0.06,
    # Tier-3 (informational)
    "fvg_overlap": 0.04,
    "fibo_236": 0.03,
}

# A realistic "full confluence" scenario would score roughly ~0.60-0.70.
# We normalise against a value that makes common setups score in [0.25, 0.85].
MAX_WEIGHTED_SCORE = 0.70


def _zones_overlap(a_high: float, a_low: float, b_high: float, b_low: float) -> bool:
    return a_low <= b_high and b_low <= a_high


def evaluate_confluences(
    zone: dict[str, Any],
    structure: dict[str, Any],
    fibo: dict[str, Any],
    all_zones: list[dict[str, Any]],
) -> tuple[list[str], float]:
    """Evaluate confluences for a single zone.

    Parameters
    ----------
    zone     : zone dict (price_high, price_low, zone_type, origin_index, ...)
    structure: output from detect_market_structure
    fibo     : output from fibo_levels_for_structure
    all_zones: all currently known zones (to find overlaps)

    Returns
    -------
    (confluences: list[str], quality_score: float)
    """
    confluences: list[str] = []
    z_high = float(zone.get("price_high", 0.0) or 0.0)
    z_low = float(zone.get("price_low", 0.0) or 0.0)
    z_mid = (z_high + z_low) / 2.0
    z_type = str(zone.get("zone_type", ""))
    z_origin_idx = int(zone.get("origin_index", 0) or 0)

    is_bullish_zone = z_type in {"ob_bullish", "fvg_bullish", "liquidity_ssl", "equal_lows"}
    is_bearish_zone = z_type in {"ob_bearish", "fvg_bearish", "liquidity_bsl", "equal_highs"}

    # ------------------------------------------------------------------
    # BOS confirmed
    # ------------------------------------------------------------------
    bos = structure.get("last_bos")
    if isinstance(bos, dict):
        bos_index = int(bos.get("index", -1))
        bos_dir = str(bos.get("direction", ""))
        if (bos_index > z_origin_idx
                and ((bos_dir == "bullish" and is_bullish_zone)
                     or (bos_dir == "bearish" and is_bearish_zone))):
            confluences.append("bos_confirmed")

    # ------------------------------------------------------------------
    # CHoCH at origin  +  CHoCH confirmed (new)
    # ------------------------------------------------------------------
    choch = structure.get("last_choch")
    if isinstance(choch, dict):
        choch_index = int(choch.get("index", -1))
        choch_price = float(choch.get("price", 0.0) or 0.0)
        if abs(choch_index - z_origin_idx) <= 3 and _zones_overlap(z_high, z_low, choch_price * 1.001, choch_price * 0.999):
            confluences.append("choch_at_origin")
        if choch.get("confirmed"):
            confluences.append("choch_confirmed")

    # ------------------------------------------------------------------
    # Premium / Discount
    # ------------------------------------------------------------------
    mid = structure.get("premium_discount_level")
    if isinstance(mid, (int, float)) and mid > 0:
        if is_bullish_zone and z_mid < mid:
            confluences.append("in_discount")
        if is_bearish_zone and z_mid > mid:
            confluences.append("in_premium")

    # ------------------------------------------------------------------
    # Structure alignment
    # ------------------------------------------------------------------
    trend = str(structure.get("trend", "ranging"))
    if (trend == "bullish" and is_bullish_zone) or (trend == "bearish" and is_bearish_zone):
        confluences.append("structure_aligned")

    # ------------------------------------------------------------------
    # Fibonacci overlaps
    # ------------------------------------------------------------------
    fibo_map = {
        "0.236": "fibo_236",
        "0.382": "fibo_382",
        "0.5": "fibo_50",
        "0.618": "fibo_618",
        "0.786": "fibo_786",
    }
    label = nearest_fibo_label(z_mid, fibo, tolerance_pct=0.3)
    if label and label in fibo_map:
        confluences.append(fibo_map[label])
    for edge in [z_high, z_low]:
        edge_label = nearest_fibo_label(edge, fibo, tolerance_pct=0.3)
        if edge_label and edge_label in fibo_map:
            c_label = fibo_map[edge_label]
            if c_label not in confluences:
                confluences.append(c_label)

    # ------------------------------------------------------------------
    # OB / FVG unmitigated (zone-level flags from detection layer)
    # ------------------------------------------------------------------
    if z_type in {"ob_bullish", "ob_bearish"} and not zone.get("mitigated"):
        confluences.append("ob_unmitigated")
    if z_type in {"fvg_bullish", "fvg_bearish"} and not zone.get("mitigated"):
        confluences.append("fvg_unmitigated")

    # ------------------------------------------------------------------
    # Overlapping zones + sweep detection
    # ------------------------------------------------------------------
    has_sweep = False
    for other in all_zones:
        if other is zone:
            continue
        o_high = float(other.get("price_high", 0.0) or 0.0)
        o_low = float(other.get("price_low", 0.0) or 0.0)
        o_type = str(other.get("zone_type", ""))

        if not _zones_overlap(z_high, z_low, o_high, o_low):
            continue

        if o_type in {"fvg_bullish", "fvg_bearish"} and "fvg_overlap" not in confluences:
            confluences.append("fvg_overlap")

        if o_type in {"liquidity_bsl", "equal_highs"} and "liquidity_above" not in confluences:
            if o_low >= z_mid:
                confluences.append("liquidity_above")

        if o_type in {"liquidity_ssl", "equal_lows"} and "liquidity_below" not in confluences:
            if o_high <= z_mid:
                confluences.append("liquidity_below")

        if o_type in {"sweep_bsl", "sweep_ssl"} and "sweep_present" not in confluences:
            confluences.append("sweep_present")
            has_sweep = True

    # ------------------------------------------------------------------
    # Sweep → CHoCH temporal correlation (T1-7)
    # A sweep that occurs shortly before a CHoCH is a high-conviction signal
    # (liquidity grab → structural reversal).  We compare sweep origin index
    # with the CHoCH index allowing a ≤5 candle window.
    # ------------------------------------------------------------------
    if has_sweep and isinstance(choch, dict):
        choch_index = int(choch.get("index", -1))
        for other in all_zones:
            if str(other.get("zone_type", "")) not in {"sweep_bsl", "sweep_ssl"}:
                continue
            sweep_idx = int(other.get("origin_index", 0) or other.get("sweep_candle_index", 0) or 0)
            if sweep_idx > 0 and 0 < choch_index - sweep_idx <= 5:
                if "sweep_choch_corr" not in confluences:
                    confluences.append("sweep_choch_corr")
                break

    # ------------------------------------------------------------------
    # Weighted quality score
    # ------------------------------------------------------------------
    weighted_sum = sum(CONFLUENCE_WEIGHTS.get(c, 0.05) for c in confluences)
    quality_score = round(min(1.0, weighted_sum / MAX_WEIGHTED_SCORE), 4)
    return confluences, quality_score
