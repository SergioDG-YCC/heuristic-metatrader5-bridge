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
