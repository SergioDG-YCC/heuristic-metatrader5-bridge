"""
SMC Heuristic Validators.

Hard invariants for heuristic SMC theses and operation candidates.
Rejects impossible prices, incoherent side/zone combinations, and
structurally invalid entries before persistence.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any


BULLISH_ZONE_TYPES = {
    "ob_bullish",
    "fvg_bullish",
    "liquidity_ssl",
    "equal_lows",
}

BEARISH_ZONE_TYPES = {
    "ob_bearish",
    "fvg_bearish",
    "liquidity_bsl",
    "equal_highs",
}


@dataclass
class CandidateValidationResult:
    accepted: bool
    candidate: dict[str, Any]
    issues: list[str]


def _is_crypto(symbol: str) -> bool:
    up = str(symbol or "").upper()
    return any(mark in up for mark in ("BTC", "ETH", "LTC", "XRP", "DOGE", "SOL", "ADA", "BNB", "AVAX", "DOT"))


def _is_index_like(symbol: str) -> bool:
    up = str(symbol or "").upper()
    return any(mark in up for mark in ("US30", "US500", "US100", "USTEC", "NAS100", "SPX", "DE30", "UK100", "JP225", "VIX"))


def _max_distance_pct(symbol: str, *, max_fx: float, max_crypto: float, max_index: float) -> float:
    if _is_crypto(symbol):
        return max_crypto
    if _is_index_like(symbol):
        return max_index
    return max_fx


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_rr(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        rr = float(value)
        return rr if rr > 0 else None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"1\s*:\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        try:
            rr = float(m.group(1))
        except ValueError:
            return None
        return rr if rr > 0 else None
    try:
        rr = float(text)
    except ValueError:
        return None
    return rr if rr > 0 else None


def _rr_from_prices(
    side: str,
    entry_zone_high: float,
    entry_zone_low: float,
    stop_loss: float,
    take_profit_1: float,
) -> float | None:
    side_l = str(side or "").lower()
    if side_l == "buy":
        entry_anchor = entry_zone_high
        risk = entry_anchor - stop_loss
        reward = take_profit_1 - entry_anchor
    elif side_l == "sell":
        entry_anchor = entry_zone_low
        risk = stop_loss - entry_anchor
        reward = entry_anchor - take_profit_1
    else:
        return None
    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 4)


def _zone_side_compatibility(zone_type: str, side: str) -> bool:
    side_l = str(side or "").lower()
    if zone_type in BULLISH_ZONE_TYPES:
        return side_l == "buy"
    if zone_type in BEARISH_ZONE_TYPES:
        return side_l == "sell"
    return True


def _price_regime_issue(
    symbol: str,
    current_price: float,
    price_level: float,
    *,
    max_fx: float,
    max_crypto: float,
    max_index: float,
) -> str | None:
    if current_price <= 0 or price_level <= 0:
        return "non_positive_price"
    if abs(math.log10(price_level) - math.log10(current_price)) > 1.0:
        return f"price_magnitude_mismatch({price_level} vs {current_price})"
    dist_pct = abs(price_level - current_price) / current_price * 100.0
    max_dist = _max_distance_pct(symbol, max_fx=max_fx, max_crypto=max_crypto, max_index=max_index)
    if dist_pct > max_dist:
        return f"price_too_far({dist_pct:.2f}%)"
    return None


def _candidate_traceability_issues(candidate: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not str(candidate.get("source_zone_id", "")).strip():
        issues.append("missing_source_zone_id")
    if not str(candidate.get("entry_model", "")).strip():
        issues.append("missing_entry_model")
    if not str(candidate.get("trigger_type", "")).strip():
        issues.append("missing_trigger_type")
    flags = candidate.get("validation_flags")
    if not isinstance(flags, list):
        issues.append("missing_validation_flags")
    return issues


def _normalize_candidate(item: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(item)
    for key in ("entry_zone_high", "entry_zone_low", "stop_loss", "take_profit_1", "take_profit_2"):
        v = _to_float(candidate.get(key))
        if v is not None:
            candidate[key] = round(v, 8)
    if not isinstance(candidate.get("validation_flags"), list):
        candidate["validation_flags"] = []
    if not isinstance(candidate.get("confluences"), list):
        candidate["confluences"] = []
    return candidate


def validate_operation_candidate(
    candidate_raw: dict[str, Any],
    *,
    symbol: str,
    current_price: float,
    bias: str,
    zone_lookup: dict[str, dict[str, Any]],
    min_rr: float,
    max_price_distance_pct_fx: float = 8.0,
    max_price_distance_pct_crypto: float = 15.0,
    max_price_distance_pct_index: float = 12.0,
) -> CandidateValidationResult:
    candidate = _normalize_candidate(candidate_raw)
    issues: list[str] = []

    side = str(candidate.get("side", "")).lower()
    if side not in {"buy", "sell"}:
        issues.append("invalid_side")

    entry_high = _to_float(candidate.get("entry_zone_high"))
    entry_low = _to_float(candidate.get("entry_zone_low"))
    sl = _to_float(candidate.get("stop_loss"))
    tp1 = _to_float(candidate.get("take_profit_1"))
    tp2 = _to_float(candidate.get("take_profit_2"))

    if entry_high is None or entry_low is None or sl is None or tp1 is None:
        issues.append("missing_required_price_fields")
        return CandidateValidationResult(False, candidate, sorted(set(issues)))

    if entry_low > entry_high:
        issues.append("entry_zone_inverted")

    _regime_kwargs = dict(
        max_fx=max_price_distance_pct_fx,
        max_crypto=max_price_distance_pct_crypto,
        max_index=max_price_distance_pct_index,
    )

    for key, level in (
        ("entry_zone_high", entry_high),
        ("entry_zone_low", entry_low),
        ("stop_loss", sl),
        ("take_profit_1", tp1),
    ):
        issue = _price_regime_issue(symbol, current_price, level, **_regime_kwargs)
        if issue:
            issues.append(f"{key}:{issue}")

    if tp2 is not None:
        issue = _price_regime_issue(symbol, current_price, tp2, **_regime_kwargs)
        if issue:
            issues.append(f"take_profit_2:{issue}")

    zone_id = str(candidate.get("source_zone_id", "")).strip()
    zone = zone_lookup.get(zone_id)
    zone_type = str((zone or {}).get("zone_type", ""))
    if zone and not _zone_side_compatibility(zone_type, side):
        issues.append(f"zone_side_incompatible({zone_type},{side})")

    if side == "buy":
        if not (sl < entry_low):
            issues.append("buy_sl_not_below_entry_zone")
        if not (tp1 > entry_high):
            issues.append("buy_tp1_not_above_entry_zone")
        if tp2 is not None and not (tp2 > tp1):
            issues.append("buy_tp2_not_above_tp1")
    elif side == "sell":
        if not (sl > entry_high):
            issues.append("sell_sl_not_above_entry_zone")
        if not (tp1 < entry_low):
            issues.append("sell_tp1_not_below_entry_zone")
        if tp2 is not None and not (tp2 < tp1):
            issues.append("sell_tp2_not_below_tp1")

    if str(bias or "").lower() in {"bullish", "bearish"} and side in {"buy", "sell"}:
        expected = "buy" if str(bias).lower() == "bullish" else "sell"
        if side != expected:
            issues.append(f"bias_side_conflict({bias},{side})")

    traceability_issues = _candidate_traceability_issues(candidate)
    issues.extend(traceability_issues)

    rr = _parse_rr(candidate.get("rr_ratio"))
    if rr is None:
        rr = _rr_from_prices(side, entry_high, entry_low, sl, tp1)
    if rr is None:
        issues.append("rr_not_computable")
    else:
        candidate["rr_value"] = round(rr, 4)
        candidate["rr_ratio"] = f"1:{rr:.2f}"
        if rr < float(min_rr):
            issues.append(f"rr_below_min({rr:.2f}<{min_rr:.2f})")

    accepted = len(issues) == 0
    if accepted:
        flags = [str(item) for item in candidate.get("validation_flags", []) if str(item).strip()]
        flags.extend([
            "price_regime_ok",
            "zone_side_ok",
            "coherence_ok",
            "rr_ok",
            "traceability_ok",
        ])
        candidate["validation_flags"] = sorted(set(flags))

    return CandidateValidationResult(accepted, candidate, sorted(set(issues)))


def validate_heuristic_thesis(
    thesis: dict[str, Any],
    *,
    symbol: str,
    current_price: float,
    active_zones: list[dict[str, Any]],
    min_rr: float = 3.0,
    max_price_distance_pct_fx: float = 8.0,
    max_price_distance_pct_crypto: float = 15.0,
    max_price_distance_pct_index: float = 12.0,
) -> dict[str, Any]:
    """Validate and normalize a heuristic thesis.

    Returns:
        {
          "normalized_thesis": dict,
          "validation_summary": dict,
          "issues": list[str],
          "dropped_candidates": list[dict],
        }
    """
    thesis_norm = dict(thesis)
    zone_lookup = {
        str(z.get("zone_id", "")).strip(): z
        for z in active_zones
        if str(z.get("zone_id", "")).strip()
    }

    raw_candidates = thesis_norm.get("operation_candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    accepted: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    issues: list[str] = []

    price_regime_ok = True
    zone_side_ok = True
    rr_ok = True
    internal_consistency_ok = True
    traceability_ok = True

    bias = str(thesis_norm.get("bias", "neutral"))

    _kwargs = dict(
        min_rr=float(min_rr),
        max_price_distance_pct_fx=max_price_distance_pct_fx,
        max_price_distance_pct_crypto=max_price_distance_pct_crypto,
        max_price_distance_pct_index=max_price_distance_pct_index,
    )

    for idx, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            dropped.append({"index": idx, "issues": ["candidate_not_object"]})
            continue
        result = validate_operation_candidate(
            raw,
            symbol=symbol,
            current_price=current_price,
            bias=bias,
            zone_lookup=zone_lookup,
            **_kwargs,
        )
        if result.accepted:
            accepted.append(result.candidate)
        else:
            dropped.append({"index": idx, "issues": result.issues, "candidate": result.candidate})
            issues.extend([f"candidate_{idx}:{issue}" for issue in result.issues])
            if any("price_" in it or "magnitude" in it for it in result.issues):
                price_regime_ok = False
            if any("zone_side" in it for it in result.issues):
                zone_side_ok = False
            if any("rr_" in it for it in result.issues):
                rr_ok = False
            if any("bias_side" in it or "coherence" in it for it in result.issues):
                internal_consistency_ok = False
            if any("missing_" in it for it in result.issues):
                traceability_ok = False

    if str(thesis_norm.get("status", "watching")).lower() == "active" and not accepted:
        thesis_norm["status"] = "watching"

    if not isinstance(thesis_norm.get("watch_conditions"), list):
        thesis_norm["watch_conditions"] = []
    if not isinstance(thesis_norm.get("invalidations"), list):
        thesis_norm["invalidations"] = []

    if not thesis_norm["watch_conditions"]:
        thesis_norm["watch_conditions"] = ["Wait for zone touch and H1 confirmation before activation."]
        internal_consistency_ok = False
        issues.append("missing_watch_conditions")

    if not thesis_norm["invalidations"]:
        thesis_norm["invalidations"] = ["Invalidate thesis if price closes beyond the primary zone in opposite direction."]
        internal_consistency_ok = False
        issues.append("missing_invalidations")

    thesis_norm["operation_candidates"] = accepted

    summary = {
        "price_regime_ok": price_regime_ok,
        "zone_side_ok": zone_side_ok,
        "rr_ok": rr_ok,
        "internal_consistency_ok": internal_consistency_ok,
        "traceability_ok": traceability_ok,
        "candidate_count_in": len(raw_candidates),
        "candidate_count_out": len(accepted),
        "min_rr": float(min_rr),
    }

    return {
        "normalized_thesis": thesis_norm,
        "validation_summary": summary,
        "issues": sorted(set(issues)),
        "dropped_candidates": dropped,
    }
