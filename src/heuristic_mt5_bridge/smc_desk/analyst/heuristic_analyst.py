"""
SMC Heuristic Analyst.

Pipeline:
1) Build a deterministic thesis from scanner evidence + multi-timeframe structure.
2) Run hard validators (no LLM).
3) Run optional LLM validator (1 call, semantic only, no prices generated).
4) Persist SMC thesis via thesis_store.

All DB calls include broker_server + account_login.
No disk writes outside SQLite — no JSON fallback files.
No module-level CFG — all configuration is passed explicitly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.infra.storage.runtime_db import (
    load_active_smc_zones,
    load_recent_smc_events,
    load_symbol_volume_options,
)
from heuristic_mt5_bridge.smc_desk.detection import (
    count_waves,
    detect_market_structure,
)
from heuristic_mt5_bridge.smc_desk.detection.fibonacci import fibo_levels_for_structure
from heuristic_mt5_bridge.smc_desk.state.thesis_store import (
    load_recent_smc_thesis,
    save_smc_thesis,
)
from heuristic_mt5_bridge.smc_desk.validators.heuristic import (
    BEARISH_ZONE_TYPES,
    BULLISH_ZONE_TYPES,
    validate_heuristic_thesis,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class SmcAnalystConfig:
    max_candidates: int = 3
    min_rr: float = 3.0
    next_review_hint_seconds: int = 14400
    d1_bars: int = 100
    h4_bars: int = 200
    h1_bars: int = 300
    llm_enabled: bool = True
    llm_model: str = "gemma-3-4b-it-qat"
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 500
    llm_temperature: float = 0.1
    analyst_cooldown_seconds: int = 300
    spread_tolerance: str = "high"  # "low" | "medium" | "high" — SMC uses higher default (long-term trades)
    spread_thresholds: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "low":    {"forex_major": 0.02, "forex_minor": 0.04, "metals": 0.05, "indices": 0.03, "crypto": 0.10, "other": 0.05},
        "medium": {"forex_major": 0.04, "forex_minor": 0.08, "metals": 0.10, "indices": 0.06, "crypto": 0.25, "other": 0.10},
        "high":   {"forex_major": 0.10, "forex_minor": 0.15, "metals": 0.20, "indices": 0.12, "crypto": 0.50, "other": 0.20},
    })

    @classmethod
    def from_env(cls) -> "SmcAnalystConfig":
        def _env(key: str, default: str) -> str:
            return os.getenv(key, default)

        return cls(
            max_candidates=int(_env("SMC_HEURISTIC_MAX_CANDIDATES", "3")),
            min_rr=float(_env("SMC_MIN_RR", "3.0")),
            next_review_hint_seconds=int(_env("SMC_HEURISTIC_NEXT_REVIEW_SECONDS", "14400")),
            d1_bars=int(_env("SMC_ANALYST_D1_BARS", "100")),
            h4_bars=int(_env("SMC_ANALYST_H4_BARS", "200")),
            h1_bars=int(_env("SMC_ANALYST_H1_BARS", "300")),
            llm_enabled=_env("SMC_LLM_ENABLED", "true").strip().lower() in ("1", "true", "yes"),
            llm_model=_env("SMC_LLM_MODEL", "gemma-3-4b-it-qat"),
            llm_timeout_seconds=int(_env("SMC_LLM_TIMEOUT_SECONDS", "60")),
            llm_max_tokens=int(_env("SMC_LLM_MAX_TOKENS", "500")),
            llm_temperature=float(_env("SMC_LLM_TEMPERATURE", "0.1")),
            analyst_cooldown_seconds=int(_env("SMC_ANALYST_COOLDOWN_SECONDS", "300")),
            spread_tolerance=_env("SMC_SPREAD_TOLERANCE", "high").strip().lower() if _env("SMC_SPREAD_TOLERANCE", "high").strip().lower() in ("low", "medium", "high") else "high",
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dict for API response."""
        return {
            "max_candidates": self.max_candidates,
            "min_rr": self.min_rr,
            "next_review_hint_seconds": self.next_review_hint_seconds,
            "d1_bars": self.d1_bars,
            "h4_bars": self.h4_bars,
            "h1_bars": self.h1_bars,
            "llm_enabled": self.llm_enabled,
            "llm_model": self.llm_model,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_temperature": self.llm_temperature,
            "analyst_cooldown_seconds": self.analyst_cooldown_seconds,
            "spread_tolerance": self.spread_tolerance,
            "spread_thresholds": self.spread_thresholds,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_price(service: MarketStateService, symbol: str) -> float:
    for tf in ("H1", "M15", "H4", "D1"):
        candles = service.get_candles(symbol, tf, bars=1)
        if candles:
            value = candles[-1].get("close")
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if v > 0:
                return v
    return 0.0


def _bias_from_trend(value: str) -> str:
    trend = str(value or "").lower()
    if trend in {"bullish", "up"}:
        return "bullish"
    if trend in {"bearish", "down"}:
        return "bearish"
    return "neutral"


def _derive_bias(d1_trend: str, h4_trend: str, h1_trend: str) -> tuple[str, str, int]:
    weights = {"D1": 3, "H4": 2, "H1": 1}
    score = 0
    for tf, trend in (("D1", d1_trend), ("H4", h4_trend), ("H1", h1_trend)):
        mapped = _bias_from_trend(trend)
        if mapped == "bullish":
            score += weights[tf]
        elif mapped == "bearish":
            score -= weights[tf]

    if score >= 2:
        bias = "bullish"
    elif score <= -2:
        bias = "bearish"
    else:
        bias = "neutral"

    confidence = "high" if abs(score) >= 5 else "medium" if abs(score) >= 3 else "low"
    return bias, confidence, score


def _build_multi_timeframe_alignment(
    struct_d1: dict[str, Any],
    struct_h4: dict[str, Any],
    struct_h1: dict[str, Any],
) -> dict[str, Any]:
    d1 = _bias_from_trend(struct_d1.get("trend"))
    h4 = _bias_from_trend(struct_h4.get("trend"))
    h1 = _bias_from_trend(struct_h1.get("trend"))
    aligned = d1 == h4 and d1 in {"bullish", "bearish"}
    conflict_note = None
    if d1 != h4 and d1 in {"bullish", "bearish"} and h4 in {"bullish", "bearish"}:
        conflict_note = f"D1={d1} conflicts with H4={h4}. Wait for H1 confirmation."
    return {
        "d1_structure": d1,
        "h4_structure": h4,
        "h1_structure": h1,
        "aligned": aligned,
        "conflict_note": conflict_note,
    }


def _zone_side(zone_type: str) -> str:
    z = str(zone_type or "")
    if z in BULLISH_ZONE_TYPES:
        return "buy"
    if z in BEARISH_ZONE_TYPES:
        return "sell"
    return "observe"


def _score_zone(
    zone: dict[str, Any],
    *,
    trigger_reason: str,
    trigger_payload: dict[str, Any],
    bias: str,
    bias_score: int,
) -> float:
    score = float(zone.get("quality_score", 0.0) or 0.0) * 100.0
    status = str(zone.get("status", "active")).lower()
    if status == "approaching":
        score += 25.0
    elif status == "active":
        score += 8.0

    zone_id = str(zone.get("zone_id", ""))
    if zone_id and zone_id == str(trigger_payload.get("zone_id", "")):
        score += 40.0

    distance_pct = zone.get("distance_pct")
    try:
        distance_value = float(distance_pct)
    except (TypeError, ValueError):
        distance_value = 99.0
    score += max(0.0, 20.0 - distance_value * 2.0)

    confluences = zone.get("confluences") if isinstance(zone.get("confluences"), list) else []
    score += min(16.0, len(confluences) * 2.5)

    side = _zone_side(str(zone.get("zone_type", "")))
    if bias == "bullish" and side == "buy":
        score += 12.0
    if bias == "bearish" and side == "sell":
        score += 12.0
    if (bias == "bullish" and side == "sell") or (bias == "bearish" and side == "buy"):
        score -= 10.0

    if str(trigger_reason) == "sweep_detected":
        if str(zone.get("zone_type", "")) in {
            "ob_bullish", "ob_bearish", "equal_lows", "equal_highs",
            "liquidity_ssl", "liquidity_bsl",
        }:
            score += 10.0

    score += max(0.0, min(8.0, abs(bias_score) * 1.5))
    return round(score, 4)


def _choose_entry_model(
    zone_type: str,
    confluences: list[str],
    elliott: dict[str, Any],
) -> tuple[str, str, str]:
    conf = {str(c).strip() for c in confluences if str(c).strip()}
    pattern = str(elliott.get("pattern_type", "")).lower()
    wave = int(elliott.get("current_wave", 0) or 0)

    if "sweep_present" in conf and zone_type in {
        "ob_bullish", "ob_bearish", "equal_lows", "equal_highs",
        "liquidity_ssl", "liquidity_bsl",
    }:
        return "model_1_ob_after_sweep", "h1_choch_aligned", "sweep_reversal"
    if zone_type in {"fvg_bullish", "fvg_bearish"} and (
        "fvg_overlap" in conf or "bos_confirmed" in conf
    ):
        return "model_2_fvg_ob_overlap", "h1_fvg_fill_and_hold", "fvg_retest"
    if (
        pattern in {"correction_abc_up", "correction_abc_down"}
        and float(elliott.get("confidence", 0.0) or 0.0) >= 0.55
    ):
        return "model_3_abc_completion", "h1_choch_aligned", "abc_completion"
    if pattern in {"impulse_up", "impulse_down"} and wave == 4:
        return "model_4_wave4_to_wave5", "h1_bos_aligned", "wave4_pullback"
    return "model_5_bos_pullback", "h1_bos_aligned", "continuation_pullback"


def _pip_size(symbol: str, spec_registry: SymbolSpecRegistry) -> float:
    pip = spec_registry.pip_size(symbol)
    return max(1e-6, pip) if pip and pip > 0 else 1e-4


def _compute_atr(candles: list[dict[str, Any]], n: int = 14) -> float:
    """Simple ATR over last *n* bars (True Range average)."""
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i].get("high", 0))
        low = float(candles[i].get("low", 0))
        prev_close = float(candles[i - 1].get("close", 0))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    window = trs[-n:] if len(trs) >= n else trs
    return sum(window) / len(window)


def _round_to_pip(price: float, symbol: str, spec_registry: SymbolSpecRegistry) -> float:
    pip = _pip_size(symbol, spec_registry)
    if pip >= 1:
        digits = 0
    else:
        text = f"{pip:.10f}".rstrip("0")
        digits = len(text.split(".", 1)[1]) if "." in text else 0
    return round(price, max(2, min(8, digits if digits > 0 else 5)))


def _build_targets(
    *,
    side: str,
    entry_high: float,
    entry_low: float,
    active_zones: list[dict[str, Any]],
    fibo: dict[str, Any],
    symbol: str,
    spec_registry: SymbolSpecRegistry,
) -> tuple[float, float]:
    span = max(0.0, entry_high - entry_low)
    if span <= 0:
        span = max(0.0001, _pip_size(symbol, spec_registry) * 8)

    zone_prices: list[float] = []
    for z in active_zones:
        ztype = str(z.get("zone_type", ""))
        zhigh = float(z.get("price_high", 0.0) or 0.0)
        zlow = float(z.get("price_low", 0.0) or 0.0)
        if side == "buy" and ztype in BEARISH_ZONE_TYPES and zlow > entry_high:
            zone_prices.append(zlow)
        if side == "sell" and ztype in BULLISH_ZONE_TYPES and zhigh < entry_low:
            zone_prices.append(zhigh)

    fib_ext_prices = [
        float(item.get("price", 0.0) or 0.0)
        for item in (fibo.get("extensions") if isinstance(fibo.get("extensions"), list) else [])
        if float(item.get("price", 0.0) or 0.0) > 0
    ]

    if side == "buy":
        candidates = sorted([p for p in zone_prices if p > entry_high])
        fib_candidates = sorted([p for p in fib_ext_prices if p > entry_high])
        tp1 = candidates[0] if candidates else (
            fib_candidates[0] if fib_candidates else entry_high + span * 2.4
        )
        tp2 = candidates[1] if len(candidates) > 1 else (
            fib_candidates[1] if len(fib_candidates) > 1 else tp1 + span * 1.8
        )
    else:
        candidates = sorted([p for p in zone_prices if p < entry_low], reverse=True)
        fib_candidates = sorted([p for p in fib_ext_prices if p < entry_low], reverse=True)
        tp1 = candidates[0] if candidates else (
            fib_candidates[0] if fib_candidates else entry_low - span * 2.4
        )
        tp2 = candidates[1] if len(candidates) > 1 else (
            fib_candidates[1] if len(fib_candidates) > 1 else tp1 - span * 1.8
        )

    return (
        _round_to_pip(tp1, symbol, spec_registry),
        _round_to_pip(tp2, symbol, spec_registry),
    )


def _build_operation_candidate(
    *,
    symbol: str,
    zone: dict[str, Any],
    side: str,
    trigger_reason: str,
    confluences: list[str],
    elliott: dict[str, Any],
    fibo: dict[str, Any],
    active_zones: list[dict[str, Any]],
    volume_options: list[float],
    spec_registry: SymbolSpecRegistry,
    h4_candles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entry_high = float(zone.get("price_high", 0.0) or 0.0)
    entry_low = float(zone.get("price_low", 0.0) or 0.0)
    span = max(0.0, entry_high - entry_low)
    pip = _pip_size(symbol, spec_registry)
    margin = max(span * 0.25, pip * 8)

    # ATR floor: SL margin must be at least 1.2 × ATR(H4, 14)
    if h4_candles and len(h4_candles) > 14:
        atr = _compute_atr(h4_candles, 14)
        atr_margin = atr * 1.2
        margin = max(margin, atr_margin)

    sl_method = "zone_invalidation_margin"
    if h4_candles and len(h4_candles) > 14 and margin >= _compute_atr(h4_candles, 14) * 1.2:
        sl_method = "atr_calibrated_zone_margin"

    if side == "buy":
        sl = _round_to_pip(entry_low - margin, symbol, spec_registry)
    else:
        sl = _round_to_pip(entry_high + margin, symbol, spec_registry)

    tp1, tp2 = _build_targets(
        side=side,
        entry_high=entry_high,
        entry_low=entry_low,
        active_zones=active_zones,
        fibo=fibo,
        symbol=symbol,
        spec_registry=spec_registry,
    )

    if side == "buy":
        risk = max(1e-9, entry_high - sl)
        reward = max(1e-9, tp1 - entry_high)
    else:
        risk = max(1e-9, sl - entry_low)
        reward = max(1e-9, entry_low - tp1)
    rr = reward / risk

    entry_model, requires_confirmation, trigger_type = _choose_entry_model(
        str(zone.get("zone_type", "")), confluences, elliott
    )
    quality = "high" if len(confluences) >= 3 and rr >= 3.0 else "medium"

    return {
        "setup_label": f"{str(zone.get('zone_type', 'zone'))} {side} setup",
        "side": side,
        "entry_zone_high": _round_to_pip(entry_high, symbol, spec_registry),
        "entry_zone_low": _round_to_pip(entry_low, symbol, spec_registry),
        "stop_loss": sl,
        "stop_loss_justification": "Beyond zone invalidation boundary with structural safety margin.",
        "take_profit_1": tp1,
        "take_profit_1_justification": "Nearest opposing liquidity / first structural objective.",
        "take_profit_2": tp2,
        "take_profit_2_justification": "Second opposing liquidity / extended objective.",
        "rr_ratio": f"1:{rr:.2f}",
        "confluences": confluences[:10],
        "quality": quality,
        "requires_confirmation": requires_confirmation,
        "trigger": str(trigger_reason),
        "entry_model": entry_model,
        "sl_method": sl_method,
        "tp_method": "opposing_liquidity_then_extension",
        "source_zone_id": str(zone.get("zone_id", "")),
        "trigger_type": trigger_type,
        "validation_flags": [],
        "volume_options": volume_options,
    }


# ---------------------------------------------------------------------------
# Core build function
# ---------------------------------------------------------------------------


def build_heuristic_output(
    *,
    symbol: str,
    trigger_reason: str,
    trigger_payload: dict[str, Any],
    service: MarketStateService,
    db_path: Path,
    broker_server: str,
    account_login: int,
    spec_registry: SymbolSpecRegistry,
    config: SmcAnalystConfig,
) -> dict[str, Any]:
    d1 = service.get_candles(symbol, "D1", bars=config.d1_bars)
    h4 = service.get_candles(symbol, "H4", bars=config.h4_bars)
    h1 = service.get_candles(symbol, "H1", bars=config.h1_bars)

    struct_d1 = detect_market_structure(d1, window=3)
    struct_h4 = detect_market_structure(h4, window=3)
    struct_h1 = detect_market_structure(h1, window=2)

    fibo = fibo_levels_for_structure(struct_d1)
    elliott = count_waves(struct_d1)

    active_zones = load_active_smc_zones(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
        timeframe=None,
        status_filter=["active", "approaching"],
    )
    sweeps = load_recent_smc_events(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
        event_type="sweep_detected",
        limit=12,
    )
    prior = load_recent_smc_thesis(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
    )
    current_price = _current_price(service, symbol)
    volume_options = load_symbol_volume_options(
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
    )

    d1_trend = str(struct_d1.get("trend", "ranging"))
    h4_trend = str(struct_h4.get("trend", "ranging"))
    h1_trend = str(struct_h1.get("trend", "ranging"))

    bias, bias_confidence, bias_score = _derive_bias(d1_trend, h4_trend, h1_trend)
    mtf = _build_multi_timeframe_alignment(struct_d1, struct_h4, struct_h1)

    # Rank active zones
    zones_ranked: list[dict[str, Any]] = []
    for zone in active_zones:
        item = dict(zone)
        item["_score"] = _score_zone(
            zone,
            trigger_reason=trigger_reason,
            trigger_payload=trigger_payload,
            bias=bias,
            bias_score=bias_score,
        )
        zones_ranked.append(item)
    zones_ranked.sort(key=lambda x: float(x.get("_score", 0.0)), reverse=True)

    prepared_zone_ids = [
        str(z.get("zone_id", "")).strip()
        for z in zones_ranked
        if str(z.get("zone_id", "")).strip()
    ][:12]
    primary_zone = zones_ranked[0] if zones_ranked else None
    primary_zone_id = str(primary_zone.get("zone_id", "")) if primary_zone else None

    # Build operation candidates
    # Gate: minimum 2 confluences required to emit a candidate.
    # Gate: when zone side opposes D1 trend, require H4 CHoCH confirmed.
    h4_choch = struct_h4.get("last_choch")
    h4_choch_confirmed = isinstance(h4_choch, dict) and h4_choch.get("confirmed")

    operation_candidates: list[dict[str, Any]] = []
    for zone in zones_ranked[: max(1, config.max_candidates)]:
        zone_type = str(zone.get("zone_type", ""))
        side = _zone_side(zone_type)
        if side not in {"buy", "sell"}:
            continue
        confluences = (
            zone.get("confluences")
            if isinstance(zone.get("confluences"), list)
            else []
        )
        if sweeps and "sweep_present" not in confluences:
            confluences = list(confluences) + ["sweep_present"]

        # Minimum confluence gate (≥2)
        if len(confluences) < 2:
            continue

        # Anti-D1 guard: trading against D1 requires H4 CHoCH confirmed
        d1_bias = _bias_from_trend(d1_trend)
        if d1_bias in {"bullish", "bearish"}:
            expected_side = "buy" if d1_bias == "bullish" else "sell"
            if side != expected_side and not h4_choch_confirmed:
                continue

        if bias in {"bullish", "bearish"}:
            expected = "buy" if bias == "bullish" else "sell"
            if side != expected and operation_candidates:
                continue

        candidate = _build_operation_candidate(
            symbol=symbol,
            zone=zone,
            side=side,
            trigger_reason=trigger_reason,
            confluences=confluences,
            elliott=elliott,
            fibo=fibo,
            active_zones=zones_ranked,
            volume_options=volume_options,
            spec_registry=spec_registry,
            h4_candles=h4,
        )
        operation_candidates.append(candidate)

    if len(operation_candidates) > config.max_candidates:
        operation_candidates = operation_candidates[: config.max_candidates]

    # Watch levels at primary zone edges
    watch_levels: list[dict[str, Any]] = []
    if primary_zone:
        zh = float(primary_zone.get("price_high", 0.0) or 0.0)
        zl = float(primary_zone.get("price_low", 0.0) or 0.0)
        watch_levels.extend([
            {
                "label": "Primary Zone High",
                "price": _round_to_pip(zh, symbol, spec_registry),
                "relation": "touch",
                "action_hint": "Watch reaction at upper edge.",
            },
            {
                "label": "Primary Zone Low",
                "price": _round_to_pip(zl, symbol, spec_registry),
                "relation": "touch",
                "action_hint": "Watch reaction at lower edge.",
            },
        ])

    if operation_candidates:
        c0 = operation_candidates[0]
        s = str(c0.get("side", "")).lower()
        if s == "buy":
            watch_conditions = [
                "Price must revisit the selected demand zone and hold above its lower boundary.",
                "Require H1 bullish confirmation before enabling aggressive execution.",
            ]
            invalidations = [
                "H4 close below primary zone low invalidates bullish setup.",
                "Failure to react after liquidity sweep invalidates current candidate.",
            ]
        else:
            watch_conditions = [
                "Price must revisit the selected supply zone and reject from its upper boundary.",
                "Require H1 bearish confirmation before enabling aggressive execution.",
            ]
            invalidations = [
                "H4 close above primary zone high invalidates bearish setup.",
                "Failure to reject after liquidity sweep invalidates current candidate.",
            ]
    else:
        watch_conditions = [
            "No candidate passes minimum confluence and coherence criteria yet.",
            "Wait for zone approach or sweep event before re-arming candidates.",
        ]
        invalidations = [
            "Invalidate thesis if active zones are mitigated or structurally broken.",
        ]

    if primary_zone:
        ztype = str(primary_zone.get("zone_type", "unknown"))
        dist = primary_zone.get("distance_pct")
        base_scenario = (
            f"Primary zone {primary_zone_id} ({ztype}) remains in focus. "
            f"Bias={bias}. Wait for H1 confirmation near zone reaction. "
            f"Distance={dist}% from current price."
        )
    else:
        base_scenario = (
            "No active high-quality zone currently available; remain in monitoring mode."
        )

    output: dict[str, Any] = {
        "symbol": str(symbol).upper(),
        "strategy_type": "smc_prepared",
        "bias": bias,
        "bias_confidence": bias_confidence,
        "base_scenario": base_scenario,
        "alternate_scenarios": [],
        "prepared_zones": prepared_zone_ids,
        "primary_zone_id": primary_zone_id,
        "watch_levels": watch_levels,
        "watch_conditions": watch_conditions,
        "invalidations": invalidations,
        "operation_candidates": operation_candidates,
        "multi_timeframe_alignment": mtf,
        "elliott_count": {
            "pattern_type": elliott.get("pattern_type"),
            "current_wave": elliott.get("current_wave"),
            "confidence": elliott.get("confidence"),
            "completed": elliott.get("completed"),
            "violations": elliott.get("violations", []),
        },
        "fibo_levels": fibo,
        "review_strategy": {
            "next_review_hint_seconds": config.next_review_hint_seconds,
            "review_on_event": [
                "zone_approaching",
                "sweep_detected",
                "zone_invalidated",
                "smc_trader_reanalysis_request",
            ],
            "review_deadline_hours": 24,
        },
        "next_review_hint_seconds": config.next_review_hint_seconds,
        "analyst_notes": "heuristic-only thesis",
        "status": "watching",
    }

    analyst_input: dict[str, Any] = {
        "symbol": str(symbol).upper(),
        "trigger_reason": str(trigger_reason),
        "trigger_payload": trigger_payload,
        "current_price": current_price,
        "d1_structure": struct_d1,
        "h4_structure": struct_h4,
        "h1_structure": struct_h1,
        "active_zones": active_zones,
        "recent_sweeps": sweeps,
        "fibo": fibo,
        "elliott": elliott,
        "prior_thesis": prior,
        "generated_at": _utc_now_iso(),
    }

    return {
        "analyst_input": analyst_input,
        "heuristic_output": output,
        "active_zones": active_zones,
        "current_price": float(current_price),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_smc_heuristic_analyst(
    *,
    symbol: str,
    trigger_reason: str,
    trigger_payload: dict[str, Any],
    service: MarketStateService,
    db_path: Path,
    broker_server: str,
    account_login: int,
    spec_registry: SymbolSpecRegistry,
    config: SmcAnalystConfig,
) -> dict[str, Any]:
    """Run full SMC analyst pipeline and persist the resulting thesis.

    Returns a dict with keys:
        analyst_input, heuristic_output, hard_validation, validator_step, thesis
    """
    import asyncio

    print(f"[smc-heuristic-analyst] {symbol} triggered by {trigger_reason}")

    payload = await asyncio.to_thread(
        build_heuristic_output,
        symbol=symbol,
        trigger_reason=trigger_reason,
        trigger_payload=trigger_payload,
        service=service,
        db_path=db_path,
        broker_server=broker_server,
        account_login=account_login,
        spec_registry=spec_registry,
        config=config,
    )
    analyst_input = payload["analyst_input"]
    heuristic_output = payload["heuristic_output"]
    active_zones = payload["active_zones"]
    current_price = payload["current_price"]

    # Hard validation (CPU-bound, no LLM)
    hard_validation = await asyncio.to_thread(
        validate_heuristic_thesis,
        heuristic_output,
        symbol=symbol,
        current_price=current_price,
        active_zones=active_zones,
        min_rr=config.min_rr,
    )

    normalized_thesis = hard_validation["normalized_thesis"]
    validation_summary = hard_validation["validation_summary"]
    hard_issues = hard_validation["issues"]

    if hard_issues:
        notes = str(normalized_thesis.get("analyst_notes", "")).strip()
        notes = (notes + " | " if notes else "") + f"hard_validator_issues={len(hard_issues)}"
        normalized_thesis["analyst_notes"] = notes[:1000]

    # Optional LLM validation (1 call)
    validator_step: dict[str, Any]
    if config.llm_enabled:
        from heuristic_mt5_bridge.smc_desk.llm.validator import call_smc_validator

        validator_step = await call_smc_validator(
            symbol=symbol,
            current_price=float(current_price or 0.0),
            trigger_reason=trigger_reason,
            heuristic_thesis=normalized_thesis,
            validation_summary=validation_summary,
            config={
                "llm_model": config.llm_model,
                "llm_timeout_seconds": config.llm_timeout_seconds,
            },
        )
    else:
        # LLM disabled — pass through with accept decision
        validator_step = {
            "validated_thesis": normalized_thesis,
            "validator_result": {
                "decision": "accept",
                "confidence": "low",
                "notes": "llm_disabled",
                "refinements": [],
            },
        }

    final_output = dict(validator_step["validated_thesis"])
    final_output["validation_summary"] = validation_summary
    final_output["validator_result"] = validator_step["validator_result"]
    final_output["validator_decision"] = validator_step["validator_result"].get("decision", "accept")

    if str(final_output.get("validator_decision", "")).lower() == "reject":
        final_output["status"] = "watching"
        final_output["operation_candidates"] = []

    # Persist
    thesis = await asyncio.to_thread(
        save_smc_thesis,
        db_path,
        broker_server=broker_server,
        account_login=account_login,
        symbol=symbol,
        analyst_output=final_output,
        prepared_zones=[
            str(z).strip()
            for z in final_output.get("prepared_zones", [])
            if str(z).strip()
        ],
        multi_tf_alignment=final_output.get("multi_timeframe_alignment"),
        elliott_count=final_output.get("elliott_count"),
        fibo_levels=final_output.get("fibo_levels"),
    )

    return {
        "analyst_input": analyst_input,
        "heuristic_output": heuristic_output,
        "hard_validation": hard_validation,
        "validator_step": validator_step,
        "thesis": thesis,
    }
