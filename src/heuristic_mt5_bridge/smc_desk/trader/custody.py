"""SMC Custody Engine — monitors open positions driven by thesis levels."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig


@dataclass
class SmcCustodyDecision:
    action: str  # "hold", "close", "scale_out", "move_sl_be", "close_invalidated"
    position_id: int = 0
    reason: str = ""
    new_sl: float | None = None
    new_tp: float | None = None
    partial_volume: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SmcCustodyEngine:

    def __init__(self, config: SmcTraderConfig) -> None:
        self._config = config

    def evaluate_position(
        self,
        *,
        position: dict[str, Any],
        thesis: dict[str, Any] | None,
        pip_size: float,
        scaled_out_ids: set[int],
    ) -> SmcCustodyDecision:
        pos_id = int(position.get("position_id", 0) or 0)
        if pos_id <= 0:
            return SmcCustodyDecision(action="hold", reason="missing_position_id")

        side = self._extract_side(position)
        open_price = float(position.get("price_open", 0) or 0)
        current_price = float(position.get("price_current", open_price) or open_price)
        current_sl = float(position.get("stop_loss", position.get("sl", 0)) or 0)
        volume = float(position.get("volume", 0) or 0)

        if open_price <= 0 or current_price <= 0 or pip_size <= 0:
            return SmcCustodyDecision(action="hold", position_id=pos_id, reason="missing_price_data")

        if thesis is None:
            return SmcCustodyDecision(
                action="close",
                position_id=pos_id,
                reason="thesis_gone",
            )

        validator = str(thesis.get("validator_decision", "")).lower()
        if validator == "reject":
            return SmcCustodyDecision(
                action="close_invalidated",
                position_id=pos_id,
                reason="thesis_rejected",
            )

        status = str(thesis.get("status", "")).lower()
        if status == "watching":
            return SmcCustodyDecision(
                action="close_invalidated",
                position_id=pos_id,
                reason="thesis_downgraded_watching",
            )

        candidates = thesis.get("operation_candidates", [])
        cand = candidates[0] if candidates else {}

        tp1 = float(cand.get("take_profit_1", 0) or 0)
        tp2 = float(cand.get("take_profit_2", 0) or 0)
        sl = float(cand.get("stop_loss", 0) or 0)

        if side == "buy":
            profit_pips = (current_price - open_price) / pip_size
            sl_risk_pips = (open_price - current_sl) / pip_size if current_sl > 0 else 0
        else:
            profit_pips = (open_price - current_price) / pip_size
            sl_risk_pips = (current_sl - open_price) / pip_size if current_sl > 0 else 0

        risk_pips = sl_risk_pips if sl_risk_pips > 0 else 30.0

        if profit_pips < 0 and abs(profit_pips) > risk_pips * 1.5:
            return SmcCustodyDecision(
                action="close",
                position_id=pos_id,
                reason=f"hard_cut:{abs(profit_pips):.1f}p>{risk_pips * 1.5:.1f}p",
            )

        if tp2 > 0:
            if side == "buy" and current_price >= tp2:
                return SmcCustodyDecision(action="close", position_id=pos_id, reason="tp2_reached")
            if side == "sell" and current_price <= tp2:
                return SmcCustodyDecision(action="close", position_id=pos_id, reason="tp2_reached")

        if tp1 > 0 and pos_id not in scaled_out_ids and volume > 0.02:
            scale_hit = False
            if side == "buy" and current_price >= tp1:
                scale_hit = True
            elif side == "sell" and current_price <= tp1:
                scale_hit = True

            if scale_hit:
                partial = round(max(0.01, volume * (self._config.scale_out_pct / 100.0)), 2)
                return SmcCustodyDecision(
                    action="scale_out",
                    position_id=pos_id,
                    reason="tp1_scale_out",
                    partial_volume=partial,
                    new_sl=open_price,
                    metadata={"tp1": tp1, "tp2": tp2},
                )

        if tp1 > 0 and pos_id in scaled_out_ids and current_sl != open_price:
            if (side == "buy" and current_price >= tp1) or (side == "sell" and current_price <= tp1):
                return SmcCustodyDecision(
                    action="move_sl_be",
                    position_id=pos_id,
                    reason="post_scale_out_be",
                    new_sl=open_price,
                )

        return SmcCustodyDecision(action="hold", position_id=pos_id, reason="monitoring")

    @staticmethod
    def _extract_side(position: dict[str, Any]) -> str:
        side = str(position.get("side", "")).lower()
        if side in ("buy", "sell"):
            return side
        raw_type = position.get("type")
        if raw_type in (0, "0", "buy", "long"):
            return "buy"
        if raw_type in (1, "1", "sell", "short"):
            return "sell"
        return "buy"
