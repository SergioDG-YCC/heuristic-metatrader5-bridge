"""Tests for ownership registry isolation guarantees.

Verifies that:
- External/manual tickets are adopted as inherited_fast
- SMC tickets cannot be reclassified as inherited_fast via reconcile
- The reassign guard blocks smc → fast transitions
"""
from __future__ import annotations

import pytest
from pathlib import Path

from heuristic_mt5_bridge.core.ownership import OwnershipRegistry
from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso


def _mk_registry(db_path: Path, *, auto_adopt: bool = True) -> OwnershipRegistry:
    ensure_runtime_db(db_path)
    return OwnershipRegistry(
        db_path=db_path,
        broker_server="Broker-1",
        account_login=123456,
        auto_adopt_foreign=auto_adopt,
        history_retention_days=30,
    )


def test_manual_ticket_adopted_as_inherited_fast(tmp_path: Path) -> None:
    """An external / manual position with no prior row is adopted as inherited_fast."""
    reg = _mk_registry(tmp_path / "runtime.db")
    manual_position = {
        "position_id": 8001,
        "symbol": "EURUSD",
        "side": "buy",
        "comment": "manual by human",
        "opened_at": utc_now_iso(),
    }

    result = reg.reconcile_from_caches(positions=[manual_position], orders=[])

    assert result["adopted_positions"] == 1
    row = reg.get_by_position_id(8001)
    assert row is not None
    assert row["ownership_status"] == "inherited_fast"
    assert row["desk_owner"] == "fast"
    assert row["origin_type"] == "adopted_inherited"


def test_smc_owned_ticket_not_reclassified_by_reconcile(tmp_path: Path) -> None:
    """A smc_owned position that has a DB row must not be re-adopted as inherited_fast
    when it appears again in the global reconcile snapshot."""
    reg = _mk_registry(tmp_path / "runtime.db")

    # Register a position as SMC-owned
    reg.register_owned_operation(
        operation_type="position",
        owner="smc",
        position_id=9001,
        reason="smc_execution_result",
        metadata={"symbol": "GBPUSD"},
    )

    # Now reconcile with the same position still in the cache
    smc_position = {
        "position_id": 9001,
        "symbol": "GBPUSD",
        "side": "sell",
        "comment": "smc:signal",
        "opened_at": utc_now_iso(),
    }
    result = reg.reconcile_from_caches(positions=[smc_position], orders=[])

    # Must not be re-adopted — existing row found and updated
    assert result["adopted_positions"] == 0

    row = reg.get_by_position_id(9001)
    assert row is not None
    # Must remain smc_owned
    assert row["ownership_status"] == "smc_owned"
    assert row["desk_owner"] == "smc"


def test_reassign_smc_to_fast_is_blocked(tmp_path: Path) -> None:
    """Reassigning a smc_owned ticket to fast desk must raise ValueError."""
    reg = _mk_registry(tmp_path / "runtime.db")
    reg.register_owned_operation(
        operation_type="position",
        owner="smc",
        position_id=9002,
        metadata={"symbol": "USDJPY"},
    )

    with pytest.raises(ValueError, match="reassigning from smc to fast is not allowed"):
        reg.reassign(target_owner="fast", position_id=9002)


def test_manual_order_adopted_as_inherited_fast(tmp_path: Path) -> None:
    """An external pending order with no prior row is adopted as inherited_fast."""
    reg = _mk_registry(tmp_path / "runtime.db")
    manual_order = {
        "order_id": 8002,
        "symbol": "AUDUSD",
        "order_type": "buy_limit",
        "comment": "manual",
        "created_at": utc_now_iso(),
    }

    result = reg.reconcile_from_caches(positions=[], orders=[manual_order])

    assert result["adopted_orders"] == 1
    row = reg.get_by_order_id(8002)
    assert row is not None
    assert row["ownership_status"] == "inherited_fast"
    assert row["desk_owner"] == "fast"


def test_smc_owned_order_not_reclassified_by_reconcile(tmp_path: Path) -> None:
    """A smc_owned pending order that has a DB row must not be re-adopted as inherited_fast."""
    reg = _mk_registry(tmp_path / "runtime.db")

    reg.register_owned_operation(
        operation_type="order",
        owner="smc",
        order_id=9003,
        reason="smc_execution_result",
        metadata={"symbol": "USDCHF"},
    )

    smc_order = {
        "order_id": 9003,
        "symbol": "USDCHF",
        "order_type": "sell_stop",
        "comment": "smc:pending",
        "created_at": utc_now_iso(),
    }
    result = reg.reconcile_from_caches(positions=[], orders=[smc_order])

    assert result["adopted_orders"] == 0

    row = reg.get_by_order_id(9003)
    assert row is not None
    assert row["ownership_status"] == "smc_owned"
    assert row["desk_owner"] == "smc"


def test_auto_adopt_false_does_not_adopt_external_tickets(tmp_path: Path) -> None:
    """When auto_adopt_foreign=False, external tickets are not adopted."""
    reg = _mk_registry(tmp_path / "runtime.db", auto_adopt=False)
    manual_position = {
        "position_id": 8003,
        "symbol": "NZDUSD",
        "side": "sell",
        "opened_at": utc_now_iso(),
    }

    result = reg.reconcile_from_caches(positions=[manual_position], orders=[])

    assert result["adopted_positions"] == 0
    assert reg.get_by_position_id(8003) is None
