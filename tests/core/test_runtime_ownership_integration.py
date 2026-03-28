from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeService
from tests.core.test_runtime_service import (
    FakeConnector,
    FakeIndicatorBridge,
    FakeSessionsService,
    _build_config,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SequencedAccountConnector(FakeConnector):
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        super().__init__(catalog_symbols=["EURUSD"])
        self._payloads = payloads
        self._account_calls = 0

    def fetch_account_runtime(self, symbols: list[str]) -> dict[str, Any]:
        _ = symbols
        idx = min(self._account_calls, len(self._payloads) - 1)
        self._account_calls += 1
        return self._payloads[idx]


def _account_payload(*, positions: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, Any]:
    now = _iso_now()
    return {
        "account_state": {
            "account_state_id": "account_123456",
            "account_login": 123456,
            "broker_server": "Broker-1",
            "broker_company": "Example Broker",
            "account_mode": "demo",
            "currency": "USD",
            "balance": 10000.0,
            "equity": 9990.0,
            "margin": 100.0,
            "free_margin": 9890.0,
            "margin_level": 99.9,
            "profit": -10.0,
            "drawdown_amount": 10.0,
            "drawdown_percent": 0.1,
            "leverage": 100,
            "open_position_count": len(positions),
            "pending_order_count": len(orders),
            "heartbeat_at": now,
            "updated_at": now,
            "account_flags": [],
        },
        "exposure_state": {
            "exposure_state_id": "exposure_123456",
            "updated_at": now,
            "gross_exposure": sum(abs(float(item.get("volume", 0.0) or 0.0)) for item in positions),
            "net_exposure": 0.0,
            "floating_profit": -10.0,
            "open_position_count": len(positions),
            "symbols": [],
        },
        "positions": positions,
        "orders": orders,
        "recent_deals": [],
        "recent_orders": [],
    }


class RuntimeOwnershipIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_reconciles_adoption_and_lifecycle_transitions(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            first_payload = _account_payload(
                positions=[
                    {
                        "position_id": 5001,
                        "symbol": "EURUSD",
                        "side": "buy",
                        "volume": 0.10,
                        "opened_at": "2026-03-24T10:00:00Z",
                    }
                ],
                orders=[
                    {
                        "order_id": 6001,
                        "symbol": "EURUSD",
                        "order_type": "buy_limit",
                        "volume_initial": 0.10,
                        "created_at": "2026-03-24T10:00:00Z",
                    }
                ],
            )
            second_payload = _account_payload(positions=[], orders=[])
            connector = SequencedAccountConnector([first_payload, second_payload])

            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()

            open_snapshot = service.ownership_open()
            assert len(open_snapshot["items"]) == 2
            assert all(item["ownership_status"] == "inherited_fast" for item in open_snapshot["items"])

            await service.run_once()
            history_snapshot = service.ownership_history()
            assert len(history_snapshot["items"]) == 2
            assert service.ownership_open()["items"] == []
            lifecycle_statuses = {item["lifecycle_status"] for item in history_snapshot["items"]}
            assert lifecycle_statuses == {"closed", "cancelled"}

            await service.shutdown()
            await asyncio.sleep(0.05)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_runtime_marks_missing_pending_order_as_filled_when_recent_execution_exists(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            first_payload = _account_payload(
                positions=[],
                orders=[
                    {
                        "order_id": 8001,
                        "symbol": "EURUSD",
                        "order_type": "buy_stop",
                        "volume_initial": 0.10,
                        "created_at": "2026-03-24T12:00:00Z",
                    }
                ],
            )
            second_payload = _account_payload(
                positions=[
                    {
                        "position_id": 9001,
                        "symbol": "EURUSD",
                        "side": "buy",
                        "volume": 0.10,
                        "opened_at": "2026-03-24T12:00:05Z",
                    }
                ],
                orders=[],
            )
            second_payload["recent_deals"] = [{"order_id": 8001, "symbol": "EURUSD", "entry": 0}]
            second_payload["recent_orders"] = [{"order_id": 8001, "symbol": "EURUSD", "state": 4}]

            connector = SequencedAccountConnector([first_payload, second_payload])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()
            await service.run_once()

            history_snapshot = service.ownership_history()
            open_snapshot = service.ownership_open()
            order_items = [item for item in history_snapshot["items"] if item.get("order_id") == 8001]
            position_items = [item for item in open_snapshot["items"] if item.get("position_id") == 9001]

            assert len(order_items) == 1
            assert order_items[0]["lifecycle_status"] == "filled"
            assert len(position_items) == 1
            assert position_items[0]["lifecycle_status"] == "active"

            await service.shutdown()
            await asyncio.sleep(0.05)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)
