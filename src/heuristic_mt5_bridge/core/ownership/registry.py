from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.infra.storage.runtime_db import (
    append_operation_ownership_event,
    get_operation_ownership_by_order_id,
    get_operation_ownership_by_position_id,
    list_operation_ownership,
    purge_operation_ownership_history,
    upsert_operation_ownership,
)
from heuristic_mt5_bridge.shared.time.utc import iso_to_datetime, utc_now, utc_now_iso


_OWNER_TO_STATUS = {
    "fast": "fast_owned",
    "smc": "smc_owned",
    "unassigned": "unassigned",
}

_ORDER_HISTORY_STATES_FILLED = {3, 4}
_ORDER_HISTORY_STATES_CANCELLED = {2, 5, 6}


@dataclass
class OwnershipRegistry:
    db_path: Path
    broker_server: str
    account_login: int
    auto_adopt_foreign: bool = True
    history_retention_days: int = 30

    def _operation_uid(self, operation_type: str, *, position_id: int | None, order_id: int | None) -> str:
        ticket = position_id if operation_type == "position" else order_id
        return f"{self.broker_server}:{self.account_login}:{operation_type}:{int(ticket or 0)}"

    def _append_event(
        self,
        *,
        operation_uid: str,
        event_type: str,
        from_owner: str | None = None,
        to_owner: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        reevaluation_required: bool | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        append_operation_ownership_event(
            self.db_path,
            {
                "broker_server": self.broker_server,
                "account_login": self.account_login,
                "operation_uid": operation_uid,
                "event_type": event_type,
                "from_owner": from_owner,
                "to_owner": to_owner,
                "from_status": from_status,
                "to_status": to_status,
                "reevaluation_required": None if reevaluation_required is None else int(bool(reevaluation_required)),
                "reason": reason,
                "payload": payload or {},
                "created_at": utc_now_iso(),
            },
        )

    def _upsert_row(self, row: dict[str, Any]) -> None:
        upsert_operation_ownership(self.db_path, row)

    def register_owned_operation(
        self,
        *,
        operation_type: str,
        owner: str,
        position_id: int | None = None,
        order_id: int | None = None,
        reason: str | None = None,
        origin_type: str = "runtime_execution",
        metadata: dict[str, Any] | None = None,
        opened_at: str | None = None,
    ) -> dict[str, Any]:
        owner = str(owner or "unassigned").strip().lower()
        desk_owner = owner if owner in {"fast", "smc"} else "unassigned"
        ownership_status = _OWNER_TO_STATUS.get(desk_owner, "unassigned")
        now_iso = utc_now_iso()
        row = {
            "operation_uid": self._operation_uid(operation_type, position_id=position_id, order_id=order_id),
            "broker_server": self.broker_server,
            "account_login": self.account_login,
            "operation_type": operation_type,
            "mt5_position_id": position_id,
            "mt5_order_id": order_id,
            "desk_owner": desk_owner,
            "ownership_status": ownership_status,
            "lifecycle_status": "active",
            "origin_type": origin_type,
            "reevaluation_required": False,
            "reason": reason,
            "adopted_at": None,
            "reassigned_at": None,
            "opened_at": opened_at,
            "closed_at": None,
            "cancelled_at": None,
            "last_seen_open_at": now_iso,
            "metadata": metadata or {},
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        self._upsert_row(row)
        self._append_event(
            operation_uid=row["operation_uid"],
            event_type="owned_registered",
            to_owner=desk_owner,
            to_status=ownership_status,
            reason=reason,
            payload={"operation_type": operation_type, "position_id": position_id, "order_id": order_id},
        )
        return row

    def register_from_execution_result(
        self,
        *,
        owner: str,
        result: dict[str, Any],
        symbol: str,
        reason: str = "execution_result",
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not isinstance(result, dict):
            return rows
        if int(result.get("position", 0) or 0) > 0:
            rows.append(
                self.register_owned_operation(
                    operation_type="position",
                    owner=owner,
                    position_id=int(result.get("position", 0) or 0),
                    reason=reason,
                    metadata={"symbol": symbol, **(metadata or {})},
                )
            )
        elif int(result.get("order", 0) or 0) > 0:
            rows.append(
                self.register_owned_operation(
                    operation_type="order",
                    owner=owner,
                    order_id=int(result.get("order", 0) or 0),
                    reason=reason,
                    metadata={"symbol": symbol, **(metadata or {})},
                )
            )
        return rows

    def get_by_position_id(self, position_id: int) -> dict[str, Any] | None:
        return get_operation_ownership_by_position_id(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            position_id=int(position_id),
        )

    def get_by_order_id(self, order_id: int) -> dict[str, Any] | None:
        return get_operation_ownership_by_order_id(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            order_id=int(order_id),
        )

    def reassign(
        self,
        *,
        target_owner: str,
        position_id: int | None = None,
        order_id: int | None = None,
        reevaluation_required: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        target_owner = str(target_owner).strip().lower()
        if target_owner not in {"fast", "smc"}:
            raise ValueError("target_owner must be 'fast' or 'smc'")
        if position_id is None and order_id is None:
            raise ValueError("position_id or order_id is required")
        row = self.get_by_position_id(int(position_id)) if position_id is not None else self.get_by_order_id(int(order_id or 0))
        if not row:
            raise ValueError("operation ownership not found")
        previous_owner = str(row.get("desk_owner", "unassigned"))
        if previous_owner == "smc" and target_owner == "fast":
            raise ValueError("reassigning from smc to fast is not allowed")
        now_iso = utc_now_iso()
        previous_status = str(row.get("ownership_status", "unassigned"))
        row["desk_owner"] = target_owner
        row["ownership_status"] = _OWNER_TO_STATUS[target_owner]
        row["reevaluation_required"] = bool(reevaluation_required)
        row["reassigned_at"] = now_iso
        row["reason"] = reason
        row["updated_at"] = now_iso
        self._upsert_row(row)
        self._append_event(
            operation_uid=str(row["operation_uid"]),
            event_type="reassigned",
            from_owner=previous_owner,
            to_owner=target_owner,
            from_status=previous_status,
            to_status=str(row["ownership_status"]),
            reevaluation_required=bool(reevaluation_required),
            reason=reason,
            payload={"position_id": row.get("mt5_position_id"), "order_id": row.get("mt5_order_id")},
        )
        return row

    def reconcile_from_caches(
        self,
        *,
        positions: list[dict[str, Any]],
        orders: list[dict[str, Any]],
        recent_deals: list[dict[str, Any]] | None = None,
        recent_orders: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now_iso = utc_now_iso()
        position_ids = {int(item.get("position_id", 0) or 0) for item in positions if int(item.get("position_id", 0) or 0) > 0}
        order_ids = {int(item.get("order_id", 0) or 0) for item in orders if int(item.get("order_id", 0) or 0) > 0}
        recent_deals_rows = recent_deals if isinstance(recent_deals, list) else []
        recent_orders_rows = recent_orders if isinstance(recent_orders, list) else []
        order_ids_with_recent_deals: set[int] = set()
        order_history_state_map: dict[int, int] = {}
        order_ids_marked_filled: set[int] = set()
        order_ids_marked_cancelled: set[int] = set()

        for deal in recent_deals_rows:
            if not isinstance(deal, dict):
                continue
            order_id = int(deal.get("order_id", 0) or 0)
            if order_id > 0:
                order_ids_with_recent_deals.add(order_id)
                order_ids_marked_filled.add(order_id)

        for hist_order in recent_orders_rows:
            if not isinstance(hist_order, dict):
                continue
            order_id = int(hist_order.get("order_id", 0) or 0)
            if order_id <= 0:
                continue
            state = int(hist_order.get("state", -1) or -1)
            order_history_state_map[order_id] = state
            if state in _ORDER_HISTORY_STATES_FILLED:
                order_ids_marked_filled.add(order_id)
            elif state in _ORDER_HISTORY_STATES_CANCELLED:
                order_ids_marked_cancelled.add(order_id)

        order_ids_marked_cancelled.difference_update(order_ids_marked_filled)
        adopted_positions = 0
        adopted_orders = 0
        transitioned_closed = 0
        transitioned_filled = 0
        transitioned_cancelled = 0

        for pos in positions:
            position_id = int(pos.get("position_id", 0) or 0)
            if position_id <= 0:
                continue
            existing = self.get_by_position_id(position_id)
            if not existing:
                if not self.auto_adopt_foreign:
                    continue
                adopted_positions += 1
                row = {
                    "operation_uid": self._operation_uid("position", position_id=position_id, order_id=None),
                    "broker_server": self.broker_server,
                    "account_login": self.account_login,
                    "operation_type": "position",
                    "mt5_position_id": position_id,
                    "mt5_order_id": None,
                    "desk_owner": "fast",
                    "ownership_status": "inherited_fast",
                    "lifecycle_status": "active",
                    "origin_type": "adopted_inherited",
                    "reevaluation_required": False,
                    "reason": "adopted_from_runtime_cache",
                    "adopted_at": now_iso,
                    "reassigned_at": None,
                    "opened_at": str(pos.get("opened_at", "")).strip() or None,
                    "closed_at": None,
                    "cancelled_at": None,
                    "last_seen_open_at": now_iso,
                    "metadata": {
                        "symbol": str(pos.get("symbol", "")).upper(),
                        "side": str(pos.get("side", "")),
                        "comment": str(pos.get("comment", "")),
                    },
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                self._upsert_row(row)
                self._append_event(
                    operation_uid=row["operation_uid"],
                    event_type="adopted_inherited",
                    to_owner="fast",
                    to_status="inherited_fast",
                    reason="adopted_from_runtime_cache",
                    payload={"position_id": position_id, "symbol": row["metadata"]["symbol"]},
                )
                continue
            existing["lifecycle_status"] = "active"
            existing["last_seen_open_at"] = now_iso
            existing["updated_at"] = now_iso
            if not existing.get("opened_at"):
                existing["opened_at"] = str(pos.get("opened_at", "")).strip() or None
            self._upsert_row(existing)

        for order in orders:
            order_id = int(order.get("order_id", 0) or 0)
            if order_id <= 0:
                continue
            existing = self.get_by_order_id(order_id)
            if not existing:
                if not self.auto_adopt_foreign:
                    continue
                adopted_orders += 1
                row = {
                    "operation_uid": self._operation_uid("order", position_id=None, order_id=order_id),
                    "broker_server": self.broker_server,
                    "account_login": self.account_login,
                    "operation_type": "order",
                    "mt5_position_id": None,
                    "mt5_order_id": order_id,
                    "desk_owner": "fast",
                    "ownership_status": "inherited_fast",
                    "lifecycle_status": "active",
                    "origin_type": "adopted_inherited",
                    "reevaluation_required": False,
                    "reason": "adopted_from_runtime_cache",
                    "adopted_at": now_iso,
                    "reassigned_at": None,
                    "opened_at": str(order.get("created_at", "")).strip() or None,
                    "closed_at": None,
                    "cancelled_at": None,
                    "last_seen_open_at": now_iso,
                    "metadata": {
                        "symbol": str(order.get("symbol", "")).upper(),
                        "order_type": str(order.get("order_type", "")),
                        "comment": str(order.get("comment", "")),
                    },
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                self._upsert_row(row)
                self._append_event(
                    operation_uid=row["operation_uid"],
                    event_type="adopted_inherited",
                    to_owner="fast",
                    to_status="inherited_fast",
                    reason="adopted_from_runtime_cache",
                    payload={"order_id": order_id, "symbol": row["metadata"]["symbol"]},
                )
                continue
            existing["lifecycle_status"] = "active"
            existing["last_seen_open_at"] = now_iso
            existing["updated_at"] = now_iso
            if not existing.get("opened_at"):
                existing["opened_at"] = str(order.get("created_at", "")).strip() or None
            self._upsert_row(existing)

        open_rows = self.list_open()
        for row in open_rows:
            operation_type = str(row.get("operation_type", ""))
            position_id = int(row.get("mt5_position_id", 0) or 0)
            order_id = int(row.get("mt5_order_id", 0) or 0)
            if operation_type == "position" and position_id > 0 and position_id not in position_ids:
                previous_status = str(row.get("lifecycle_status", "active"))
                row["lifecycle_status"] = "closed"
                row["closed_at"] = row.get("closed_at") or now_iso
                row["updated_at"] = now_iso
                row["reason"] = "position_disappeared_from_cache"
                self._upsert_row(row)
                transitioned_closed += 1
                self._append_event(
                    operation_uid=str(row["operation_uid"]),
                    event_type="lifecycle_transition",
                    from_status=previous_status,
                    to_status="closed",
                    reason="position_disappeared_from_cache",
                    payload={"position_id": position_id},
                )
            if operation_type == "order" and order_id > 0 and order_id not in order_ids:
                previous_status = str(row.get("lifecycle_status", "active"))
                if order_id in order_ids_marked_filled:
                    row["lifecycle_status"] = "filled"
                    row["closed_at"] = row.get("closed_at") or now_iso
                    row["cancelled_at"] = None
                    row["updated_at"] = now_iso
                    row["reason"] = "order_filled_from_runtime_history"
                    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    metadata["terminal_outcome"] = "filled"
                    metadata["fill_evidence"] = {
                        "recent_deal_detected": order_id in order_ids_with_recent_deals,
                        "recent_order_state": order_history_state_map.get(order_id),
                    }
                    row["metadata"] = metadata
                    self._upsert_row(row)
                    transitioned_filled += 1
                    self._append_event(
                        operation_uid=str(row["operation_uid"]),
                        event_type="lifecycle_transition",
                        from_status=previous_status,
                        to_status="filled",
                        reason="order_filled_from_runtime_history",
                        payload={
                            "order_id": order_id,
                            "recent_deal_detected": order_id in order_ids_with_recent_deals,
                            "recent_order_state": order_history_state_map.get(order_id),
                        },
                    )
                else:
                    row["lifecycle_status"] = "cancelled"
                    row["cancelled_at"] = row.get("cancelled_at") or now_iso
                    row["updated_at"] = now_iso
                    row["reason"] = "order_disappeared_from_cache"
                    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    if order_id in order_ids_marked_cancelled:
                        metadata["terminal_outcome"] = "cancelled"
                        metadata["cancel_evidence"] = {"recent_order_state": order_history_state_map.get(order_id)}
                    row["metadata"] = metadata
                    self._upsert_row(row)
                    transitioned_cancelled += 1
                    self._append_event(
                        operation_uid=str(row["operation_uid"]),
                        event_type="lifecycle_transition",
                        from_status=previous_status,
                        to_status="cancelled",
                        reason="order_disappeared_from_cache",
                        payload={"order_id": order_id, "recent_order_state": order_history_state_map.get(order_id)},
                    )

        cutoff_iso = (utc_now() - timedelta(days=max(0, int(self.history_retention_days)))).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
        purged_history = purge_operation_ownership_history(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            cutoff_iso=cutoff_iso,
        )

        return {
            "adopted_positions": adopted_positions,
            "adopted_orders": adopted_orders,
            "transitioned_closed": transitioned_closed,
            "transitioned_filled": transitioned_filled,
            "transitioned_cancelled": transitioned_cancelled,
            "purged_history": purged_history,
            "open_count": len(self.list_open()),
        }

    def list_all(self) -> list[dict[str, Any]]:
        return list_operation_ownership(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            lifecycle_statuses=None,
        )

    def list_open(self) -> list[dict[str, Any]]:
        return list_operation_ownership(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            lifecycle_statuses=("active",),
        )

    def list_history(self) -> list[dict[str, Any]]:
        return list_operation_ownership(
            self.db_path,
            broker_server=self.broker_server,
            account_login=self.account_login,
            lifecycle_statuses=("closed", "cancelled", "filled"),
        )

    def summary(self) -> dict[str, Any]:
        rows = self.list_all()
        open_rows = [row for row in rows if str(row.get("lifecycle_status", "")) == "active"]
        history_rows = [row for row in rows if str(row.get("lifecycle_status", "")) in {"closed", "cancelled", "filled"}]
        reevaluation_required_count = sum(1 for row in open_rows if bool(row.get("reevaluation_required")))
        return {
            "total": len(rows),
            "open": len(open_rows),
            "history": len(history_rows),
            "reevaluation_required_open": reevaluation_required_count,
            "inherited_open": sum(1 for row in open_rows if str(row.get("ownership_status", "")) == "inherited_fast"),
            "by_owner": {
                "fast": sum(1 for row in open_rows if str(row.get("desk_owner", "")) == "fast"),
                "smc": sum(1 for row in open_rows if str(row.get("desk_owner", "")) == "smc"),
                "unassigned": sum(1 for row in open_rows if str(row.get("desk_owner", "")) == "unassigned"),
            },
        }

    def to_operation_view(self, row: dict[str, Any]) -> dict[str, Any]:
        started_at = row.get("opened_at")
        if not started_at:
            seen = row.get("last_seen_open_at")
            started_at = seen if isinstance(seen, str) and seen.strip() else None
        age_seconds = None
        if isinstance(started_at, str):
            dt = iso_to_datetime(started_at)
            if dt:
                age_seconds = max(0, int((utc_now() - dt).total_seconds()))
        return {
            "operation_uid": row.get("operation_uid"),
            "operation_type": row.get("operation_type"),
            "position_id": row.get("mt5_position_id"),
            "order_id": row.get("mt5_order_id"),
            "desk_owner": row.get("desk_owner"),
            "ownership_status": row.get("ownership_status"),
            "lifecycle_status": row.get("lifecycle_status"),
            "origin_type": row.get("origin_type"),
            "reevaluation_required": bool(row.get("reevaluation_required")),
            "reason": row.get("reason"),
            "adopted_at": row.get("adopted_at"),
            "reassigned_at": row.get("reassigned_at"),
            "opened_at": row.get("opened_at"),
            "closed_at": row.get("closed_at"),
            "cancelled_at": row.get("cancelled_at"),
            "last_seen_open_at": row.get("last_seen_open_at"),
            "updated_at": row.get("updated_at"),
            "age_seconds": age_seconds,
            "metadata": row.get("metadata", {}),
        }
