from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from heuristic_mt5_bridge.fast_desk.setup.engine import FastSetup
from heuristic_mt5_bridge.smc_desk.detection.structure import detect_market_structure


logger = logging.getLogger("fast_desk.trigger")


@dataclass
class FastTriggerConfig:
    displacement_body_factor: float = 1.8


@dataclass
class FastTriggerDecision:
    confirmed: bool
    trigger_type: str
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


_STRONG_TRIGGERS = frozenset({"micro_bos", "displacement", "reclaim"})


class FastTriggerEngine:
    """Confirm M5 setup with deterministic M1 trigger conditions."""

    def __init__(self, config: FastTriggerConfig | None = None) -> None:
        self.config = config or FastTriggerConfig()

    def confirm(
        self,
        *,
        setup: FastSetup,
        candles_m1: list[dict[str, Any]],
        pip_size: float,
        context: Any | None = None,
    ) -> FastTriggerDecision:
        if len(candles_m1) < 18 or pip_size <= 0:
            return FastTriggerDecision(False, "none", 0.0, "insufficient_m1_data")

        # Phase 5: context-based pre-filter
        if context is not None:
            vol_regime = str(getattr(context, "volatility_regime", ""))
            if vol_regime == "very_low":
                logger.debug("trigger rejected: very_low volatility regime")
                return FastTriggerDecision(False, "none", 0.0, "volatility_too_low")

        checks: list[FastTriggerDecision] = []
        checks.append(self._micro_bos(setup, candles_m1))
        checks.append(self._micro_choch(setup, candles_m1))
        checks.append(self._rejection_candle(setup, candles_m1))
        checks.append(self._reclaim(setup, candles_m1))
        checks.append(self._displacement(setup, candles_m1))

        valid = [item for item in checks if item.confirmed]
        if not valid:
            return FastTriggerDecision(False, "none", 0.0, "m1_trigger_missing")

        # Phase 5: trigger stacking — require ≥2 confirmations, or 1 strong + displacement
        strong = [t for t in valid if t.trigger_type in _STRONG_TRIGGERS]
        if len(valid) < 2 and not strong:
            logger.debug("trigger rejected: only weak triggers (%s)", [t.trigger_type for t in valid])
            return FastTriggerDecision(False, "none", 0.0, "weak_trigger_only")

        valid.sort(key=lambda item: item.confidence, reverse=True)
        best = valid[0]

        # Phase 5: exhaustion risk requires higher trigger confidence
        if context is not None:
            exhaustion = str(getattr(context, "exhaustion_risk", "low"))
            if exhaustion == "high" and best.confidence < 0.82:
                logger.debug("trigger rejected: exhaustion=high confidence=%.2f", best.confidence)
                return FastTriggerDecision(False, best.trigger_type, best.confidence, "exhaustion_high_weak_trigger")

        return best

    @staticmethod
    def _micro_bos(setup: FastSetup, candles: list[dict[str, Any]]) -> FastTriggerDecision:
        structure = detect_market_structure(candles[-80:], window=2)
        bos = structure.get("last_bos") if isinstance(structure.get("last_bos"), dict) else None
        if not bos:
            return FastTriggerDecision(False, "micro_bos", 0.0, "no_bos")
        direction = str(bos.get("direction", ""))
        if direction == "bullish" and setup.side == "buy":
            return FastTriggerDecision(True, "micro_bos", 0.86, "m1_bos_bullish")
        if direction == "bearish" and setup.side == "sell":
            return FastTriggerDecision(True, "micro_bos", 0.86, "m1_bos_bearish")
        return FastTriggerDecision(False, "micro_bos", 0.0, "bos_not_aligned")

    @staticmethod
    def _micro_choch(setup: FastSetup, candles: list[dict[str, Any]]) -> FastTriggerDecision:
        structure = detect_market_structure(candles[-80:], window=2)
        choch = structure.get("last_choch") if isinstance(structure.get("last_choch"), dict) else None
        if not choch:
            return FastTriggerDecision(False, "micro_choch", 0.0, "no_choch")
        if not choch.get("confirmed", False):
            return FastTriggerDecision(False, "micro_choch", 0.0, "choch_not_confirmed")
        direction = str(choch.get("direction", ""))
        if direction == "bullish" and setup.side == "buy":
            return FastTriggerDecision(True, "micro_choch", 0.79, "m1_choch_bullish")
        if direction == "bearish" and setup.side == "sell":
            return FastTriggerDecision(True, "micro_choch", 0.79, "m1_choch_bearish")
        return FastTriggerDecision(False, "micro_choch", 0.0, "choch_not_aligned")

    @staticmethod
    def _rejection_candle(setup: FastSetup, candles: list[dict[str, Any]]) -> FastTriggerDecision:
        last = candles[-1]
        open_price = float(last.get("open", 0.0) or 0.0)
        close = float(last.get("close", 0.0) or 0.0)
        high = float(last.get("high", 0.0) or 0.0)
        low = float(last.get("low", 0.0) or 0.0)
        if min(open_price, close, high, low) <= 0:
            return FastTriggerDecision(False, "rejection_candle", 0.0, "invalid_candle")
        body = abs(close - open_price)
        upper_wick = max(0.0, high - max(open_price, close))
        lower_wick = max(0.0, min(open_price, close) - low)
        if setup.side == "buy" and close > open_price and lower_wick > body * 1.25:
            return FastTriggerDecision(True, "rejection_candle", 0.72, "bullish_rejection")
        if setup.side == "sell" and close < open_price and upper_wick > body * 1.25:
            return FastTriggerDecision(True, "rejection_candle", 0.72, "bearish_rejection")
        return FastTriggerDecision(False, "rejection_candle", 0.0, "no_rejection")

    @staticmethod
    def _reclaim(setup: FastSetup, candles: list[dict[str, Any]]) -> FastTriggerDecision:
        level = setup.retest_level
        if not isinstance(level, (int, float)) or level <= 0:
            return FastTriggerDecision(False, "reclaim", 0.0, "missing_level")
        prev_close = float(candles[-2].get("close", 0.0) or 0.0)
        close = float(candles[-1].get("close", 0.0) or 0.0)
        if setup.side == "buy" and prev_close < level <= close:
            return FastTriggerDecision(True, "reclaim", 0.74, "bullish_reclaim")
        if setup.side == "sell" and prev_close > level >= close:
            return FastTriggerDecision(True, "reclaim", 0.74, "bearish_reclaim")
        return FastTriggerDecision(False, "reclaim", 0.0, "no_reclaim")

    def _displacement(self, setup: FastSetup, candles: list[dict[str, Any]]) -> FastTriggerDecision:
        sample = candles[-12:]
        last = sample[-1]
        body = abs(float(last.get("close", 0.0) or 0.0) - float(last.get("open", 0.0) or 0.0))
        avg_body = sum(
            abs(float(c.get("close", 0.0) or 0.0) - float(c.get("open", 0.0) or 0.0)) for c in sample[:-1]
        ) / max(1, len(sample) - 1)
        if avg_body <= 0:
            return FastTriggerDecision(False, "displacement", 0.0, "avg_body_zero")
        direction = "buy" if float(last.get("close", 0.0) or 0.0) > float(last.get("open", 0.0) or 0.0) else "sell"
        if body >= avg_body * float(self.config.displacement_body_factor) and direction == setup.side:
            return FastTriggerDecision(True, "displacement", 0.81, "m1_displacement")
        return FastTriggerDecision(False, "displacement", 0.0, "no_displacement")
