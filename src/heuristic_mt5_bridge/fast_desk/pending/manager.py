from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from heuristic_mt5_bridge.fast_desk.context.service import FastContext


@dataclass
class FastPendingPolicyConfig:
    pending_ttl_seconds: int = 900
    reprice_threshold_pips: float = 8.0
    reprice_buffer_pips: float = 1.0


@dataclass
class FastPendingDecision:
    action: str
    order_id: int
    reason: str
    price_open: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FastPendingManager:
    def __init__(self, config: FastPendingPolicyConfig | None = None) -> None:
        self.config = config or FastPendingPolicyConfig()

    def evaluate(
        self,
        *,
        order: dict[str, Any],
        context: FastContext,
        current_price: float,
        pip_size: float,
    ) -> FastPendingDecision:
        order_id = int(order.get("order_id", 0) or 0)
        if order_id <= 0:
            return FastPendingDecision(action="hold", order_id=0, reason="missing_order_id")

        if not context.allowed:
            return FastPendingDecision(action="cancel", order_id=order_id, reason="context_gate_failed")

        if self._is_expired(order):
            return FastPendingDecision(action="cancel", order_id=order_id, reason="pending_ttl_expired")

        price_open = float(order.get("price_open", 0.0) or 0.0)
        if price_open <= 0 or current_price <= 0 or pip_size <= 0:
            return FastPendingDecision(action="hold", order_id=order_id, reason="missing_price_context")

        distance_pips = abs(current_price - price_open) / pip_size
        if distance_pips < self.config.reprice_threshold_pips:
            return FastPendingDecision(action="hold", order_id=order_id, reason="pending_within_range")

        order_type = str(order.get("order_type", "")).lower()
        side = "buy" if "buy" in order_type else "sell"
        entry_type = "stop" if "stop" in order_type else "limit"
        buffer = self.config.reprice_buffer_pips * pip_size

        if side == "buy":
            new_price = current_price + buffer if entry_type == "stop" else max(0.0, current_price - buffer)
        else:
            new_price = current_price - buffer if entry_type == "stop" else current_price + buffer

        return FastPendingDecision(
            action="modify",
            order_id=order_id,
            reason="pending_reprice",
            price_open=round(new_price, 10),
            stop_loss=float(order.get("stop_loss", 0.0) or 0.0) or None,
            take_profit=float(order.get("take_profit", 0.0) or 0.0) or None,
            metadata={"distance_pips": round(distance_pips, 3), "order_type": order_type},
        )

    def _is_expired(self, order: dict[str, Any]) -> bool:
        created = str(order.get("created_at", "")).strip()
        if not created:
            return False
        try:
            created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            return False
        age = (datetime.now(timezone.utc) - created_at).total_seconds()
        return age > float(max(30, self.config.pending_ttl_seconds))
