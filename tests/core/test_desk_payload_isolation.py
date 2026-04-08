"""Tests for desk-scoped account payload isolation.

Verifies that:
- account_payload_for_desk("fast") returns only fast_owned / inherited_fast tickets
- account_payload_for_desk("smc") returns only smc_owned tickets
- smc_owned tickets never appear in the FAST payload
- fast_owned / inherited_fast tickets never appear in the SMC payload
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeService
from heuristic_mt5_bridge.infra.storage.runtime_db import ensure_runtime_db
from heuristic_mt5_bridge.core.ownership import OwnershipRegistry

# Reuse helpers from the existing runtime service test
from tests.core.test_runtime_service import (
    FakeConnector,
    FakeIndicatorBridge,
    FakeSessionsService,
    _build_config,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _account_payload(
    *,
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    now = _iso_now()
    return {
        "account_state": {"balance": 10000.0, "equity": 10000.0, "currency": "USD"},
        "exposure_state": {"open_position_count": len(positions)},
        "positions": positions,
        "orders": orders,
        "recent_deals": [],
        "recent_orders": [],
    }


class _DeskPayloadConnector(FakeConnector):
    """Connector that reports predefined positions and orders."""

    def __init__(self, positions: list[dict[str, Any]], orders: list[dict[str, Any]]) -> None:
        super().__init__(catalog_symbols=["EURUSD"])
        self._positions = positions
        self._orders = orders

    def fetch_account_runtime(self, symbols: list[str]) -> dict[str, Any]:
        base = super().fetch_account_runtime(symbols)
        base["positions"] = self._positions
        base["orders"] = self._orders
        return base


class DeskPayloadIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def test_smc_owned_position_not_in_fast_payload(self) -> None:
        """A smc_owned position must not appear in account_payload_for_desk('fast')."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            smc_position = {
                "position_id": 1001,
                "symbol": "EURUSD",
                "side": "buy",
                "volume": 0.1,
                "price_open": 1.1050,
                "stop_loss": 1.1000,
                "take_profit": 1.1200,
                "comment": "smc:signal_abc",
                "opened_at": _iso_now(),
            }
            connector = _DeskPayloadConnector(
                positions=[smc_position],
                orders=[],
            )
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            # Manually register the position as smc_owned
            assert service.ownership_registry is not None
            service.ownership_registry.register_owned_operation(
                operation_type="position",
                owner="smc",
                position_id=1001,
                reason="smc_execution_result",
                metadata={"symbol": "EURUSD"},
            )

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            fast_position_ids = {p["position_id"] for p in fast_payload.get("positions", [])}
            smc_position_ids = {p["position_id"] for p in smc_payload.get("positions", [])}

            self.assertNotIn(1001, fast_position_ids, "smc_owned position must not appear in FAST payload")
            self.assertIn(1001, smc_position_ids, "smc_owned position must appear in SMC payload")

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_fast_owned_position_not_in_smc_payload(self) -> None:
        """A fast_owned position must not appear in account_payload_for_desk('smc')."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            fast_position = {
                "position_id": 2001,
                "symbol": "EURUSD",
                "side": "sell",
                "volume": 0.05,
                "price_open": 1.1080,
                "stop_loss": 1.1130,
                "take_profit": 1.0900,
                "comment": "",
                "opened_at": _iso_now(),
            }
            connector = _DeskPayloadConnector(
                positions=[fast_position],
                orders=[],
            )
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            assert service.ownership_registry is not None
            service.ownership_registry.register_owned_operation(
                operation_type="position",
                owner="fast",
                position_id=2001,
                reason="fast_execution_result",
                metadata={"symbol": "EURUSD"},
            )

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            fast_position_ids = {p["position_id"] for p in fast_payload.get("positions", [])}
            smc_position_ids = {p["position_id"] for p in smc_payload.get("positions", [])}

            self.assertIn(2001, fast_position_ids, "fast_owned position must appear in FAST payload")
            self.assertNotIn(2001, smc_position_ids, "fast_owned position must not appear in SMC payload")

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_inherited_fast_position_visible_to_fast_not_smc(self) -> None:
        """A ticket adopted as inherited_fast must be visible to FAST but not SMC."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            manual_position = {
                "position_id": 3001,
                "symbol": "GBPUSD",
                "side": "buy",
                "volume": 0.1,
                "price_open": 1.2700,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "comment": "manual",
                "opened_at": _iso_now(),
            }
            connector = _DeskPayloadConnector(
                positions=[manual_position],
                orders=[],
            )
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            # Reconcile will auto-adopt as inherited_fast (auto_adopt_foreign=True)
            assert service.ownership_registry is not None
            service.ownership_registry.reconcile_from_caches(
                positions=[manual_position], orders=[]
            )
            row = service.ownership_registry.get_by_position_id(3001)
            self.assertIsNotNone(row)
            self.assertEqual(row["ownership_status"], "inherited_fast")

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            fast_ids = {p["position_id"] for p in fast_payload.get("positions", [])}
            smc_ids = {p["position_id"] for p in smc_payload.get("positions", [])}

            self.assertIn(3001, fast_ids, "inherited_fast position must appear in FAST payload")
            self.assertNotIn(3001, smc_ids, "inherited_fast position must not appear in SMC payload")

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_smc_owned_order_not_in_fast_payload(self) -> None:
        """A smc_owned pending order must not appear in account_payload_for_desk('fast')."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            smc_order = {
                "order_id": 5001,
                "symbol": "USDCHF",
                "order_type": "buy_stop",
                "volume": 0.1,
                "price_open": 0.9100,
                "stop_loss": 0.9050,
                "take_profit": 0.9250,
                "comment": "smc:pending",
                "created_at": _iso_now(),
            }
            connector = _DeskPayloadConnector(
                positions=[],
                orders=[smc_order],
            )
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            assert service.ownership_registry is not None
            service.ownership_registry.register_owned_operation(
                operation_type="order",
                owner="smc",
                order_id=5001,
                reason="smc_execution_result",
                metadata={"symbol": "USDCHF"},
            )

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            fast_order_ids = {o["order_id"] for o in fast_payload.get("orders", [])}
            smc_order_ids = {o["order_id"] for o in smc_payload.get("orders", [])}

            self.assertNotIn(5001, fast_order_ids, "smc_owned order must not appear in FAST payload")
            self.assertIn(5001, smc_order_ids, "smc_owned order must appear in SMC payload")

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_account_state_remains_global_in_desk_payload(self) -> None:
        """account_state must be the same (global) in both desk payloads."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = _DeskPayloadConnector(positions=[], orders=[])
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            # Both should have account_state
            self.assertIn("account_state", fast_payload)
            self.assertIn("account_state", smc_payload)
            # account_state is global — both desks should see the same balance
            fast_balance = (fast_payload.get("account_state") or {}).get("balance")
            smc_balance = (smc_payload.get("account_state") or {}).get("balance")
            self.assertEqual(fast_balance, smc_balance)

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_ownership_visible_ids_for_desk_empty_when_no_registry(self) -> None:
        """If ownership_registry is None, visible ids are empty sets."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = _DeskPayloadConnector(positions=[], orders=[])
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            # Do NOT call bootstrap — registry remains None
            service.ownership_registry = None

            visible = service.ownership_visible_ids_for_desk(desk="fast")
            self.assertEqual(visible["position_ids"], set())
            self.assertEqual(visible["order_ids"], set())
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_mixed_positions_are_correctly_partitioned(self) -> None:
        """When both SMC and FAST positions exist, each desk sees only its own."""
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            fast_pos = {
                "position_id": 7001, "symbol": "EURUSD", "side": "buy",
                "volume": 0.1, "price_open": 1.1000, "opened_at": _iso_now(),
            }
            smc_pos = {
                "position_id": 7002, "symbol": "EURUSD", "side": "sell",
                "volume": 0.2, "price_open": 1.1100, "opened_at": _iso_now(),
            }
            connector = _DeskPayloadConnector(
                positions=[fast_pos, smc_pos],
                orders=[],
            )
            service = CoreRuntimeService(
                config=_build_config(storage_root),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            assert service.ownership_registry is not None
            service.ownership_registry.register_owned_operation(
                operation_type="position", owner="fast",
                position_id=7001, metadata={"symbol": "EURUSD"},
            )
            service.ownership_registry.register_owned_operation(
                operation_type="position", owner="smc",
                position_id=7002, metadata={"symbol": "EURUSD"},
            )

            fast_payload = service.account_payload_for_desk(desk="fast")
            smc_payload = service.account_payload_for_desk(desk="smc")

            fast_ids = {p["position_id"] for p in fast_payload.get("positions", [])}
            smc_ids = {p["position_id"] for p in smc_payload.get("positions", [])}

            self.assertEqual(fast_ids, {7001})
            self.assertEqual(smc_ids, {7002})

            await service.shutdown()
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)
