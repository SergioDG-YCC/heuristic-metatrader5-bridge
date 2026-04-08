from __future__ import annotations

from pathlib import Path

from heuristic_mt5_bridge.core.ownership import OwnershipRegistry
from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db


def _mk_registry(db_path: Path) -> OwnershipRegistry:
    ensure_runtime_db(db_path)
    return OwnershipRegistry(
        db_path=db_path,
        broker_server="Broker-1",
        account_login=123456,
        auto_adopt_foreign=True,
        history_retention_days=30,
    )


def test_adopts_orphan_operations_and_avoids_duplicates(tmp_path: Path) -> None:
    reg = _mk_registry(tmp_path / "runtime.db")
    positions = [
        {
            "position_id": 101,
            "symbol": "EURUSD",
            "side": "buy",
            "comment": "external",
            "opened_at": "2026-03-24T10:00:00Z",
        }
    ]

    first = reg.reconcile_from_caches(positions=positions, orders=[])
    second = reg.reconcile_from_caches(positions=positions, orders=[])

    assert first["adopted_positions"] == 1
    assert second["adopted_positions"] == 0

    open_rows = reg.list_open()
    assert len(open_rows) == 1
    assert open_rows[0]["ownership_status"] == "inherited_fast"
    assert open_rows[0]["desk_owner"] == "fast"


def test_reassign_fast_to_smc_persists_reevaluation_required(tmp_path: Path) -> None:
    reg = _mk_registry(tmp_path / "runtime.db")
    reg.reconcile_from_caches(
        positions=[{"position_id": 202, "symbol": "GBPUSD", "side": "sell", "opened_at": "2026-03-24T10:01:00Z"}],
        orders=[],
    )

    reg.reassign(
        target_owner="smc",
        position_id=202,
        reevaluation_required=True,
        reason="manual desk handoff",
    )

    row = reg.get_by_position_id(202)
    assert row is not None
    assert row["desk_owner"] == "smc"
    assert row["ownership_status"] == "smc_owned"
    assert row["reevaluation_required"] is True
    assert row["reason"] == "manual desk handoff"


def test_transitions_to_history_after_disappearing_from_cache(tmp_path: Path) -> None:
    reg = _mk_registry(tmp_path / "runtime.db")
    reg.reconcile_from_caches(
        positions=[{"position_id": 303, "symbol": "USDJPY", "side": "buy", "opened_at": "2026-03-24T10:02:00Z"}],
        orders=[{"order_id": 404, "symbol": "USDJPY", "order_type": "buy_limit", "created_at": "2026-03-24T10:02:00Z"}],
    )

    reg.reconcile_from_caches(positions=[], orders=[])

    assert reg.list_open() == []
    history_rows = reg.list_history()
    assert len(history_rows) == 2
    statuses = {str(item.get("lifecycle_status")) for item in history_rows}
    assert statuses == {"closed", "cancelled"}

    by_position = reg.get_by_position_id(303)
    by_order = reg.get_by_order_id(404)
    assert by_position is not None and by_position["lifecycle_status"] == "closed"
    assert by_order is not None and by_order["lifecycle_status"] == "cancelled"


def test_pending_order_disappearance_is_cancelled_when_no_fill_evidence(tmp_path: Path) -> None:
    reg = _mk_registry(tmp_path / "runtime.db")
    reg.reconcile_from_caches(
        positions=[],
        orders=[{"order_id": 505, "symbol": "EURUSD", "order_type": "buy_limit", "created_at": "2026-03-24T11:00:00Z"}],
    )

    result = reg.reconcile_from_caches(
        positions=[],
        orders=[],
        recent_orders=[{"order_id": 505, "state": 2, "symbol": "EURUSD"}],
    )

    row = reg.get_by_order_id(505)
    assert row is not None
    assert row["lifecycle_status"] == "cancelled"
    assert result["transitioned_cancelled"] == 1
    assert result["transitioned_filled"] == 0


def test_pending_order_disappearance_is_filled_when_execution_evidence_exists(tmp_path: Path) -> None:
    reg = _mk_registry(tmp_path / "runtime.db")
    reg.reconcile_from_caches(
        positions=[],
        orders=[{"order_id": 606, "symbol": "GBPUSD", "order_type": "buy_stop", "created_at": "2026-03-24T11:05:00Z"}],
    )

    result = reg.reconcile_from_caches(
        positions=[{"position_id": 707, "symbol": "GBPUSD", "side": "buy", "opened_at": "2026-03-24T11:06:00Z"}],
        orders=[],
        recent_deals=[{"order_id": 606, "symbol": "GBPUSD", "entry": 0}],
        recent_orders=[{"order_id": 606, "state": 4, "symbol": "GBPUSD"}],
    )

    order_row = reg.get_by_order_id(606)
    position_row = reg.get_by_position_id(707)
    assert order_row is not None
    assert order_row["lifecycle_status"] == "filled"
    assert position_row is not None
    assert position_row["lifecycle_status"] == "active"
    assert result["transitioned_filled"] == 1
    assert result["transitioned_cancelled"] == 0

    # Persistence check across next refresh.
    reg.reconcile_from_caches(
        positions=[{"position_id": 707, "symbol": "GBPUSD", "side": "buy", "opened_at": "2026-03-24T11:06:00Z"}],
        orders=[],
        recent_deals=[{"order_id": 606, "symbol": "GBPUSD", "entry": 0}],
        recent_orders=[{"order_id": 606, "state": 4, "symbol": "GBPUSD"}],
    )
    order_row_after = reg.get_by_order_id(606)
    assert order_row_after is not None
    assert order_row_after["lifecycle_status"] == "filled"


def test_smc_pending_order_fill_preserves_desk_ownership(tmp_path: Path) -> None:
    """Broker reuses the same ticket for the position that results from a filled
    pending order.  The reconcile loop must find the SMC order row by that shared
    ticket and promote it to a position row — NOT adopt it as inherited_fast."""
    reg = _mk_registry(tmp_path / "runtime.db")

    # SMC places a limit order; ownership registered at placement time.
    reg.register_owned_operation(
        operation_type="order",
        owner="smc",
        order_id=12345,
        metadata={"symbol": "EURUSD", "side": "buy"},
        reason="smc_execution_result",
    )

    order_row = reg.get_by_order_id(12345)
    assert order_row is not None
    assert order_row["desk_owner"] == "smc"

    # Order fills: MT5 removes it from live orders and creates position #12345
    # (broker reuses the same ticket number).
    result = reg.reconcile_from_caches(
        positions=[
            {
                "position_id": 12345,   # same ticket as the order
                "symbol": "EURUSD",
                "side": "buy",
                "opened_at": "2026-04-06T10:00:00Z",
            }
        ],
        orders=[],  # order gone from live orders (filled)
    )

    # The position must be owned by SMC — not inherited_fast.
    pos_row = reg.get_by_position_id(12345)
    assert pos_row is not None, "position row must exist after fill"
    assert pos_row["desk_owner"] == "smc", "SMC ownership must be preserved after fill"
    assert pos_row["ownership_status"] == "smc_owned"
    assert pos_row["lifecycle_status"] == "active"
    assert pos_row["operation_type"] == "position"
    # Must NOT have been adopted as a foreign position.
    assert result["adopted_positions"] == 0

    # SMC worker can find its own position via list_open filtered by desk_owner.
    smc_open = [r for r in reg.list_open() if r.get("desk_owner") == "smc"]
    assert any(r.get("mt5_position_id") == 12345 for r in smc_open)

    # Idempotent: next reconcile cycle must not re-adopt or change ownership.
    result2 = reg.reconcile_from_caches(
        positions=[
            {
                "position_id": 12345,
                "symbol": "EURUSD",
                "side": "buy",
                "opened_at": "2026-04-06T10:00:00Z",
            }
        ],
        orders=[],
    )
    assert result2["adopted_positions"] == 0
    pos_row2 = reg.get_by_position_id(12345)
    assert pos_row2 is not None
    assert pos_row2["desk_owner"] == "smc"
