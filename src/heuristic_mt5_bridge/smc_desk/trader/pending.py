"""SMC Pending Order Manager — lifecycle for thesis-driven pending orders."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig


@dataclass
class SmcPendingDecision:
    action: str  # "hold", "place", "modify", "cancel"
    order_id: int = 0
    reason: str = ""
    entry_type: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    volume: float | None = None
    side: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SmcPendingManager:

    def __init__(self, config: SmcTraderConfig) -> None:
        self._config = config

    def evaluate_new_thesis(
        self,
        *,
        thesis: dict[str, Any],
        current_price: float,
        pip_size: float,
    ) -> SmcPendingDecision:
        status = str(thesis.get("status", "")).lower()
        if status not in ("active", "prepared", "watching"):
            return SmcPendingDecision(action="hold", reason=f"thesis_status:{status}")

        candidates = thesis.get("operation_candidates", [])
        if not candidates:
            return SmcPendingDecision(action="hold", reason="no_candidates")

        cand = candidates[0]
        side = str(cand.get("side", "")).lower()
        if side not in ("buy", "sell"):
            return SmcPendingDecision(action="hold", reason=f"invalid_side:{side}")

        entry_low = float(cand.get("entry_zone_low", 0) or 0)
        entry_high = float(cand.get("entry_zone_high", 0) or 0)
        sl = float(cand.get("stop_loss", 0) or 0)
        tp1 = float(cand.get("take_profit_1", 0) or 0)

        if entry_low <= 0 or entry_high <= 0 or sl <= 0 or tp1 <= 0:
            return SmcPendingDecision(action="hold", reason="missing_price_levels")

        entry_price = (entry_low + entry_high) / 2.0

        if pip_size > 0:
            buffer = self._config.entry_zone_buffer_pips * pip_size
        else:
            buffer = 0.0

        entry_type = self._derive_entry_type(side, entry_price, current_price, buffer)

        return SmcPendingDecision(
            action="place",
            reason="thesis_candidate",
            entry_type=entry_type,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp1,
            side=side,
            metadata={
                "entry_zone_low": entry_low,
                "entry_zone_high": entry_high,
                "take_profit_2": float(cand.get("take_profit_2", 0) or 0),
                "quality": str(cand.get("quality", "")),
                "thesis_id": str(thesis.get("thesis_id", "")),
            },
        )

    def evaluate_existing_order(
        self,
        *,
        order: dict[str, Any],
        thesis: dict[str, Any] | None,
        current_price: float,
        pip_size: float,
    ) -> SmcPendingDecision:
        order_id = int(order.get("order_id", order.get("mt5_order_id", 0)) or 0)

        if thesis is None:
            return SmcPendingDecision(action="cancel", order_id=order_id, reason="thesis_gone")

        status = str(thesis.get("status", "")).lower()
        if status in ("invalidated", "expired", "closed"):
            return SmcPendingDecision(action="cancel", order_id=order_id, reason=f"thesis_{status}")

        validator = str(thesis.get("validator_decision", "")).lower()
        if validator == "reject":
            return SmcPendingDecision(action="cancel", order_id=order_id, reason="thesis_rejected")

        if self._is_expired(order):
            return SmcPendingDecision(action="cancel", order_id=order_id, reason="ttl_expired")

        candidates = thesis.get("operation_candidates", [])
        if not candidates:
            return SmcPendingDecision(action="cancel", order_id=order_id, reason="no_candidates")

        cand = candidates[0]
        new_entry_low = float(cand.get("entry_zone_low", 0) or 0)
        new_entry_high = float(cand.get("entry_zone_high", 0) or 0)
        new_sl = float(cand.get("stop_loss", 0) or 0)
        new_tp1 = float(cand.get("take_profit_1", 0) or 0)

        if new_entry_low <= 0 or new_entry_high <= 0:
            return SmcPendingDecision(action="cancel", order_id=order_id, reason="thesis_missing_levels")

        current_order_price = float(order.get("price_open", 0) or 0)
        current_order_sl = float(order.get("stop_loss", order.get("sl", 0)) or 0)
        current_order_tp = float(order.get("take_profit", order.get("tp", 0)) or 0)

        new_entry_price = (new_entry_low + new_entry_high) / 2.0

        needs_modify = False
        if pip_size > 0:
            price_delta_pips = abs(new_entry_price - current_order_price) / pip_size
            sl_delta_pips = abs(new_sl - current_order_sl) / pip_size if current_order_sl > 0 else 0
            tp_delta_pips = abs(new_tp1 - current_order_tp) / pip_size if current_order_tp > 0 else 0
            if price_delta_pips > 3.0 or sl_delta_pips > 3.0 or tp_delta_pips > 5.0:
                needs_modify = True
        else:
            if abs(new_entry_price - current_order_price) > 0:
                needs_modify = True

        if needs_modify:
            side = str(cand.get("side", "")).lower()
            buffer = self._config.entry_zone_buffer_pips * pip_size if pip_size > 0 else 0.0
            entry_type = self._derive_entry_type(side, new_entry_price, current_price, buffer)
            return SmcPendingDecision(
                action="modify",
                order_id=order_id,
                reason="thesis_changed",
                entry_type=entry_type,
                entry_price=new_entry_price,
                stop_loss=new_sl,
                take_profit=new_tp1,
                metadata={
                    "price_delta_pips": round(price_delta_pips, 2) if pip_size > 0 else None,
                },
            )

        return SmcPendingDecision(action="hold", order_id=order_id, reason="within_tolerance")

    def _is_expired(self, order: dict[str, Any]) -> bool:
        created = str(order.get("created_at", order.get("time_setup", ""))).strip()
        if not created:
            return False
        try:
            if created.replace("-", "").replace(":", "").replace("T", "").replace("Z", "").isdigit() and len(created) <= 12:
                created_at = datetime.fromtimestamp(float(created), tz=timezone.utc)
            else:
                created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, OSError):
            return False
        age = (datetime.now(timezone.utc) - created_at).total_seconds()
        return age > float(max(3600, self._config.pending_ttl_seconds))

    @staticmethod
    def _derive_entry_type(side: str, entry_price: float, current_price: float, buffer: float) -> str:
        if side == "buy":
            if entry_price < current_price - buffer:
                return "buy_limit"
            return "buy_stop"
        else:
            if entry_price > current_price + buffer:
                return "sell_limit"
            return "sell_stop"
