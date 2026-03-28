from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from heuristic_mt5_bridge.fast_desk.context.service import FastContext


@dataclass
class FastCustodyPolicyConfig:
    be_trigger_r: float = 1.2
    atr_trigger_r: float = 1.8
    structural_trigger_r: float = 2.2
    hard_cut_r: float = 1.25
    enable_atr_trailing: bool = True
    enable_structural_trailing: bool = True
    enable_scale_out: bool = False
    scale_out_r: float = 2.5
    atr_trailing_multiplier: float = 1.3


@dataclass
class FastCustodyDecision:
    action: str
    position_id: int
    reason: str
    new_sl: float | None = None
    new_tp: float | None = None
    partial_volume: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FastCustodyEngine:
    """Professional deterministic custody for fast-owned positions."""

    def __init__(self, config: FastCustodyPolicyConfig | None = None) -> None:
        self.config = config or FastCustodyPolicyConfig()

    def evaluate_position(
        self,
        *,
        position: dict[str, Any],
        candles_m1: list[dict[str, Any]],
        candles_m5: list[dict[str, Any]],
        context: FastContext,
        pip_size: float,
        scaled_out_position_ids: set[int],
    ) -> FastCustodyDecision:
        pos_id = int(position.get("position_id", 0) or 0)
        if pos_id <= 0:
            return FastCustodyDecision(action="hold", position_id=0, reason="missing_position_id")

        side = str(position.get("side", "")).lower()
        if side not in {"buy", "sell"}:
            raw_type = position.get("type")
            if isinstance(raw_type, int):
                side = "buy" if raw_type == 0 else "sell"
            else:
                side = "buy"

        open_price = float(position.get("price_open", 0.0) or 0.0)
        current_price = float(position.get("price_current", open_price) or open_price)
        current_sl = float(position.get("stop_loss", position.get("sl", 0.0)) or 0.0)
        volume = float(position.get("volume", 0.0) or 0.0)
        if open_price <= 0 or current_price <= 0 or pip_size <= 0:
            return FastCustodyDecision(action="hold", position_id=pos_id, reason="missing_price_data")

        if side == "buy":
            profit_pips = (current_price - open_price) / pip_size
            sl_risk_pips = (open_price - current_sl) / pip_size if current_sl > 0 else 0.0
        else:
            profit_pips = (open_price - current_price) / pip_size
            sl_risk_pips = (current_sl - open_price) / pip_size if current_sl > 0 else 0.0
        loss_pips = max(0.0, -profit_pips)

        atr = max(self._atr(candles_m5, 14), pip_size * 10)
        fallback_risk_pips = max((atr / pip_size) * 1.2, 12.0)
        risk_pips = sl_risk_pips if sl_risk_pips > 0 else fallback_risk_pips

        # Hard cut: structural invalidation / over-loss.
        if loss_pips >= risk_pips * self.config.hard_cut_r:
            return FastCustodyDecision(
                action="close",
                position_id=pos_id,
                reason=f"hard_cut:{loss_pips:.2f}p>{risk_pips * self.config.hard_cut_r:.2f}p",
            )

        # No passive underwater: losing + opposite H1 bias.
        if loss_pips > risk_pips * 0.55 and ((context.h1_bias == "buy" and side == "sell") or (context.h1_bias == "sell" and side == "buy")):
            return FastCustodyDecision(action="close", position_id=pos_id, reason="no_passive_underwater")

        # Optional scale out.
        if (
            self.config.enable_scale_out
            and pos_id not in scaled_out_position_ids
            and volume > 0.02
            and profit_pips >= risk_pips * self.config.scale_out_r
        ):
            partial = round(max(0.01, volume / 2.0), 2)
            return FastCustodyDecision(
                action="reduce",
                position_id=pos_id,
                reason="scale_out_partial",
                partial_volume=partial,
            )

        # Break-even step.
        if profit_pips >= risk_pips * self.config.be_trigger_r:
            be_sl = open_price + pip_size if side == "buy" else open_price - pip_size
            if self._is_tighter(side, be_sl, current_sl):
                return FastCustodyDecision(
                    action="move_to_be",
                    position_id=pos_id,
                    reason="breakeven_trigger",
                    new_sl=round(be_sl, 10),
                )

        # ATR trailing.
        if self.config.enable_atr_trailing and profit_pips >= risk_pips * self.config.atr_trigger_r:
            atr_sl = self._atr_stop(side=side, current_price=current_price, atr=atr, multiplier=self.config.atr_trailing_multiplier)
            if self._is_tighter(side, atr_sl, current_sl):
                return FastCustodyDecision(
                    action="trail_atr",
                    position_id=pos_id,
                    reason="atr_trailing",
                    new_sl=round(atr_sl, 10),
                    metadata={"atr": atr},
                )

        # Structural trailing.
        if self.config.enable_structural_trailing and profit_pips >= risk_pips * self.config.structural_trigger_r:
            struct_level = self._structural_level(side=side, candles=candles_m1, fallback=current_price)
            if struct_level is not None and self._is_tighter(side, struct_level, current_sl):
                return FastCustodyDecision(
                    action="trail_structural",
                    position_id=pos_id,
                    reason="structural_trailing",
                    new_sl=round(struct_level, 10),
                )

        return FastCustodyDecision(action="hold", position_id=pos_id, reason="hold")

    @staticmethod
    def _atr(candles: list[dict[str, Any]], period: int) -> float:
        if len(candles) < 2:
            return 0.0
        trs: list[float] = []
        for idx in range(1, len(candles)):
            high = float(candles[idx].get("high", 0.0) or 0.0)
            low = float(candles[idx].get("low", 0.0) or 0.0)
            prev_close = float(candles[idx - 1].get("close", 0.0) or 0.0)
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        if not trs:
            return 0.0
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window)

    @staticmethod
    def _atr_stop(*, side: str, current_price: float, atr: float, multiplier: float) -> float:
        distance = atr * max(0.5, multiplier)
        if side == "buy":
            return current_price - distance
        return current_price + distance

    @staticmethod
    def _is_tighter(side: str, candidate_sl: float, current_sl: float) -> bool:
        if current_sl <= 0:
            return True
        if side == "buy":
            return candidate_sl > current_sl
        return candidate_sl < current_sl

    @staticmethod
    def _structural_level(*, side: str, candles: list[dict[str, Any]], fallback: float) -> float | None:
        if len(candles) < 6:
            return None
        sample = candles[-8:]
        if side == "buy":
            lows = [float(item.get("low", 0.0) or 0.0) for item in sample if float(item.get("low", 0.0) or 0.0) > 0]
            if not lows:
                return None
            return min(lows[-4:])
        highs = [float(item.get("high", 0.0) or 0.0) for item in sample if float(item.get("high", 0.0) or 0.0) > 0]
        if not highs:
            return None
        return max(highs[-4:])
