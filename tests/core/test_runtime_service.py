from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeConfig, CoreRuntimeService, build_runtime_service


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class FakeConnector:
    def __init__(
        self,
        *,
        catalog_symbols: list[str] | None = None,
        broker_server: str = "Broker-1",
        broker_company: str = "Example Broker",
        account_login: int = 123456,
    ) -> None:
        self.server_time_offset_seconds = 7200
        self.connected = False
        self.catalog_symbols = [symbol.upper() for symbol in (catalog_symbols or ["EURUSD"])]
        self.broker_server = broker_server
        self.broker_company = broker_company
        self.account_login = account_login
        self.snapshot_calls: list[tuple[str, str, int]] = []

    def connect(self) -> None:
        self.connected = True

    def shutdown(self) -> None:
        self.connected = False

    def broker_identity(self) -> dict[str, Any]:
        return {
            "broker_server": self.broker_server,
            "broker_company": self.broker_company,
            "account_login": self.account_login,
            "terminal_name": "MT5",
            "terminal_path": "",
        }

    def fetch_available_symbol_count(self) -> int:
        return len(self.catalog_symbols)

    def fetch_available_symbol_catalog(self) -> list[dict[str, Any]]:
        now = _iso(datetime.now(timezone.utc))
        items: list[dict[str, Any]] = []
        for symbol in self.catalog_symbols:
            items.append(
                {
                    "broker_server": self.broker_server,
                    "account_login": self.account_login,
                    "symbol": symbol,
                    "updated_at": now,
                    "description": f"{symbol} description",
                    "path": "Forex\\Majors",
                    "asset_class": "Forex",
                    "path_group": "Majors",
                    "path_subgroup": "",
                    "visible": True,
                    "selected": True,
                    "custom": False,
                    "trade_mode": 0,
                    "digits": 5,
                    "currency_base": symbol[:3],
                    "currency_profit": symbol[3:6] if len(symbol) >= 6 else "USD",
                    "currency_margin": "USD",
                }
            )
        return items

    def fetch_symbol_specification(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "updated_at": _iso(datetime.now(timezone.utc)),
            "broker_server": self.broker_server,
            "digits": 5,
            "point": 0.00001,
            "tick_size": 0.00001,
            "tick_value": 1.0,
            "contract_size": 100000.0,
            "spread_float": True,
            "spread_points": 15,
            "stops_level_points": 10,
            "freeze_level_points": 0,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "volume_limit": 0.0,
            "currency_base": "EUR",
            "currency_profit": "USD",
            "currency_margin": "USD",
            "trade_mode": 0,
            "filling_mode": 3,
            "order_mode": 127,
            "expiration_mode": 15,
            "trade_calc_mode": 0,
            "margin_initial": 0.0,
            "margin_maintenance": 0.0,
            "margin_hedged": 0.0,
            "swap_long": 0.0,
            "swap_short": 0.0,
        }

    def fetch_snapshot(self, symbol: str, timeframe: str, bars: int = 200) -> dict[str, Any]:
        normalized_symbol = symbol.upper()
        normalized_timeframe = timeframe.upper()
        self.snapshot_calls.append((normalized_symbol, normalized_timeframe, bars))
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        candles: list[dict[str, Any]] = []
        price = 1.1000
        for idx in range(30):
            ts = end - timedelta(minutes=(30 - idx) * 5)
            candles.append(
                {
                    "timestamp": _iso(ts),
                    "open": round(price, 5),
                    "high": round(price + 0.0005, 5),
                    "low": round(price - 0.0003, 5),
                    "close": round(price + 0.0002, 5),
                }
            )
            price += 0.0001
        return {
            "snapshot_id": f"snap_{normalized_symbol}_{normalized_timeframe}",
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "created_at": _iso(end),
            "bid": round(price, 5),
            "ask": round(price + 0.0002, 5),
            "ohlc": candles,
            "structure": {
                "market_regime": "trend_up",
                "range_high": round(price + 0.0005, 5),
                "range_low": round(price - 0.004, 5),
            },
            "market_context": {
                "server_time_offset_seconds": self.server_time_offset_seconds,
                "tick_time_raw": _iso(end + timedelta(seconds=self.server_time_offset_seconds)),
                "tick_time": _iso(end),
                "last_bar_timestamp_raw": _iso(end + timedelta(seconds=self.server_time_offset_seconds)),
                "last_bar_timestamp": _iso(end),
            },
        }

    def fetch_account_runtime(self, symbols: list[str]) -> dict[str, Any]:
        now = _iso(datetime.now(timezone.utc))
        return {
            "account_state": {
                "account_state_id": f"account_{self.account_login}",
                "account_login": self.account_login,
                "broker_server": self.broker_server,
                "broker_company": self.broker_company,
                "account_mode": "demo",
                "currency": "USD",
                "balance": 10000.0,
                "equity": 10025.0,
                "margin": 100.0,
                "free_margin": 9925.0,
                "margin_level": 100.25,
                "profit": 25.0,
                "drawdown_amount": 0.0,
                "drawdown_percent": 0.0,
                "leverage": 100,
                "open_position_count": 0,
                "pending_order_count": 0,
                "heartbeat_at": now,
                "updated_at": now,
                "account_flags": [f"watch:{symbol}" for symbol in symbols],
            },
            "exposure_state": {
                "exposure_state_id": f"exposure_{self.account_login}",
                "updated_at": now,
                "gross_exposure": 0.0,
                "net_exposure": 0.0,
                "floating_profit": 0.0,
                "open_position_count": 0,
                "symbols": [],
            },
            "positions": [],
            "orders": [],
            "recent_deals": [],
            "recent_orders": [],
        }


class ActiveSymbolConnector(FakeConnector):
    def fetch_account_runtime(self, symbols: list[str]) -> dict[str, Any]:
        payload = super().fetch_account_runtime(symbols)
        now = _iso(datetime.now(timezone.utc))
        payload["account_state"]["open_position_count"] = 1
        payload["exposure_state"]["open_position_count"] = 1
        payload["positions"] = [
            {
                "position_id": 991,
                "symbol": "USDJPY",
                "side": "buy",
                "volume": 0.10,
                "price_open": 150.10,
                "price_current": 150.25,
                "stop_loss": 149.90,
                "take_profit": 150.60,
                "opened_at": now,
                "comment": "",
            }
        ]
        return payload


class FakeSessionsService:
    def __init__(self, start_ok: bool = True) -> None:
        self.start_ok = start_ok
        self.running = False
        self.replace_calls: list[list[str]] = []

    def start(self) -> bool:
        self.running = self.start_ok
        return self.start_ok

    def stop(self) -> None:
        self.running = False

    def bootstrap_active_symbols(self, symbols: list[str]) -> None:
        self.replace_calls.append(list(symbols))

    def replace_active_symbols(self, symbols: list[str], *, reason: str = "") -> None:
        self.replace_calls.append(list(symbols))

    def snapshot(self) -> dict[str, Any]:
        return {
            "service": {
                "running": self.running,
                "host": "127.0.0.1",
                "port": 5561,
            },
            "session_groups": {},
            "symbol_to_session_group": {},
            "active_symbols": [],
            "registry_meta": {},
            "pending_symbols": [],
            "failed_symbols": [],
        }


class FakeIndicatorBridge:
    def __init__(self, status: str = "waiting_first_snapshot") -> None:
        self.status = status

    def poll(
        self,
        market_state: Any,
        subscribed_symbols: set[str] | None = None,
        subscribed_timeframes: set[str] | None = None,
    ) -> dict[str, Any]:
        _ = market_state
        _ = subscribed_symbols
        _ = subscribed_timeframes
        return {
            "enabled": True,
            "status": self.status,
            "responses_dir": "fake",
            "last_imported_at": "",
            "last_snapshot_at": "",
            "last_error": "",
            "imported_in_cycle": 0,
            "applied_in_cycle": 0,
            "total_imported": 0,
            "updated_at": _iso(datetime.now(timezone.utc)),
        }


def _build_config(
    storage_root: Path,
    *,
    watch_symbols: list[str] | None = None,
    watch_timeframes: list[str] | None = None,
    sessions_enabled: bool = True,
) -> CoreRuntimeConfig:
    return CoreRuntimeConfig(
        repo_root=storage_root.parent,
        storage_root=storage_root,
        runtime_db_path=storage_root / "runtime.db",
        terminal_path="",
        watch_symbols=watch_symbols or ["EURUSD"],
        watch_timeframes=watch_timeframes or ["M5", "H1"],
        poll_seconds=1.0,
        bars_per_pull=50,
        account_mode_guard="demo",
        magic_number=20260315,
        symbol_specs_refresh_seconds=30.0,
        symbol_catalog_refresh_seconds=60.0,
        account_refresh_seconds=5.0,
        indicator_refresh_seconds=5.0,
        market_state_checkpoint_seconds=5.0,
        risk_adopt_foreign_positions=True,
        ownership_history_retention_days=30,
        sessions_enabled=sessions_enabled,
        sessions_host="127.0.0.1",
        sessions_port=5561,
        sessions_recv_timeout_ms=15000,
        indicator_enabled=True,
        indicator_stale_after_seconds=180,
        indicator_common_files_root="",
        correlation_enabled=False,
        correlation_refresh_seconds=60.0,
        correlation_window_bars=50,
        correlation_min_coverage_bars=30,
        correlation_return_type="simple",
        correlation_stale_source_seconds=300.0,
        correlation_timeframes=["M5", "H1"],
    )


class CoreRuntimeServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_build_runtime_service_adds_fast_required_timeframes(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            (tmp_path / ".env").write_text(
                "MT5_WATCH_TIMEFRAMES=M1,M5,H1,H4,D1\nFAST_DESK_ENABLED=true\n",
                encoding="utf-8",
            )
            service = await build_runtime_service(tmp_path)
            self.assertEqual(service.config.watch_timeframes, ["M1", "M5", "H1", "H4", "D1", "M30"])
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_bootstrap_persists_runtime_and_uses_env_subscriptions(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD", "GBPUSD"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(status="waiting_first_snapshot"),
            )
            await service.bootstrap()

            self.assertEqual(service.broker_identity["account_login"], 123456)
            self.assertEqual(service.subscribed_universe, ["EURUSD", "GBPUSD"])
            self.assertEqual(service.chart_registry.worker_count(), 2)
            self.assertEqual(service.health["status"], "up")

            with sqlite3.connect(storage_root / "runtime.db") as conn:
                market_count = conn.execute("SELECT COUNT(*) FROM market_state_cache").fetchone()[0]
                catalog_count = conn.execute("SELECT COUNT(*) FROM symbol_catalog_cache").fetchone()[0]
            self.assertGreaterEqual(market_count, 1)
            self.assertGreaterEqual(catalog_count, 3)
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_broker_visible_but_unsubscribed_symbols_are_not_polled(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5", "H1"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.run_once()
            polled_symbols = {symbol for symbol, _, _ in connector.snapshot_calls}
            self.assertEqual(polled_symbols, {"EURUSD"})
            self.assertNotIn("USDJPY", polled_symbols)
            self.assertNotIn("GBPUSD", polled_symbols)
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_subscribe_and_unsubscribe_manage_worker_lifecycle(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()
            self.assertEqual(service.chart_registry.worker_count(), 1)
            self.assertEqual(service.subscribed_universe, ["EURUSD"])

            subscribed = await service.subscribe_symbol("GBPUSD", reason="test")
            self.assertTrue(subscribed)
            self.assertEqual(service.chart_registry.worker_count(), 2)
            self.assertEqual(service.subscribed_universe, ["EURUSD", "GBPUSD"])

            connector.snapshot_calls.clear()
            await service.run_once()
            polled_symbols = {symbol for symbol, _, _ in connector.snapshot_calls}
            self.assertIn("GBPUSD", polled_symbols)

            unsubscribed = await service.unsubscribe_symbol("GBPUSD", reason="test")
            self.assertTrue(unsubscribed)
            self.assertEqual(service.chart_registry.worker_count(), 1)
            self.assertEqual(service.subscribed_universe, ["EURUSD"])

            connector.snapshot_calls.clear()
            await service.run_once()
            polled_symbols_after_unsub = {symbol for symbol, _, _ in connector.snapshot_calls}
            self.assertNotIn("GBPUSD", polled_symbols_after_unsub)
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_manual_symbol_preferences_persist_across_restart(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()
            await service.subscribe_symbol("GBPUSD", reason="test")
            await service.unsubscribe_symbol("EURUSD", reason="test")
            await service.set_symbol_desks("GBPUSD", {"smc"})
            await service.shutdown()
            await asyncio.sleep(0.1)

            restarted = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"]),
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await restarted.bootstrap()
            self.assertEqual(restarted.subscribed_universe, ["GBPUSD"])
            self.assertEqual(restarted.get_symbol_desks("GBPUSD"), {"smc"})

            with sqlite3.connect(storage_root / "runtime.db") as conn:
                rows = conn.execute(
                    """
                    SELECT symbol, is_subscribed
                    FROM symbol_subscription_state
                    WHERE broker_server = ? AND account_login = ?
                    ORDER BY symbol
                    """,
                    ("Broker-1", 123456),
                ).fetchall()
            self.assertEqual(rows, [("EURUSD", 0), ("GBPUSD", 1)])
            await restarted.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_symbol_preferences_are_partitioned_by_broker(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            broker_one = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=FakeConnector(catalog_symbols=["EURUSD", "GBPUSD"], broker_server="Broker-1", account_login=123456),
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await broker_one.bootstrap()
            await broker_one.subscribe_symbol("GBPUSD", reason="test")
            await broker_one.shutdown()
            await asyncio.sleep(0.1)

            broker_two = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["USDJPY"], watch_timeframes=["M5"]),
                connector=FakeConnector(catalog_symbols=["EURUSD", "GBPUSD", "USDJPY"], broker_server="Broker-2", account_login=654321),
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await broker_two.bootstrap()
            self.assertEqual(broker_two.subscribed_universe, ["USDJPY"])

            with sqlite3.connect(storage_root / "runtime.db") as conn:
                broker_one_rows = conn.execute(
                    """
                    SELECT symbol, is_subscribed
                    FROM symbol_subscription_state
                    WHERE broker_server = ? AND account_login = ?
                    ORDER BY symbol
                    """,
                    ("Broker-1", 123456),
                ).fetchall()
                broker_two_rows = conn.execute(
                    """
                    SELECT symbol, is_subscribed
                    FROM symbol_subscription_state
                    WHERE broker_server = ? AND account_login = ?
                    ORDER BY symbol
                    """,
                    ("Broker-2", 654321),
                ).fetchall()
            self.assertEqual(broker_one_rows, [("EURUSD", 1), ("GBPUSD", 1)])
            self.assertEqual(broker_two_rows, [("USDJPY", 1)])
            await broker_two.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_chart_state_stays_in_ram_for_subscribed_symbols(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M5"]),
                connector=FakeConnector(catalog_symbols=["EURUSD", "GBPUSD"]),
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(status="waiting_first_snapshot"),
            )
            await service.run_once()
            candles = service.market_state.get_candles("EURUSD", "M5", bars=10)
            self.assertGreaterEqual(len(candles), 1)
            self.assertEqual(service.chart_registry.worker_count(), 1)
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_account_activity_symbols_are_auto_subscribed_without_restart(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            connector = ActiveSymbolConnector(catalog_symbols=["EURUSD", "USDJPY"])
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"], watch_timeframes=["M1", "M5", "H1"]),
                connector=connector,
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.run_once()
            self.assertEqual(service.subscribed_universe, ["EURUSD", "USDJPY"])
            self.assertEqual(service.chart_registry.worker_count(), 2)

            connector.snapshot_calls.clear()
            await service.run_once()
            polled_symbols = {symbol for symbol, _, _ in connector.snapshot_calls}
            self.assertIn("USDJPY", polled_symbols)
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_live_payload_is_status_oriented(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            service = CoreRuntimeService(
                config=_build_config(storage_root, watch_symbols=["EURUSD"]),
                connector=FakeConnector(catalog_symbols=["EURUSD", "USDJPY"]),
                sessions_service=FakeSessionsService(start_ok=True),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()
            live_payload = service.build_live_state()
            self.assertIn("universes", live_payload)
            self.assertIn("chart_workers", live_payload)
            self.assertIn("feed_status", live_payload)
            self.assertNotIn("chart_contexts", live_payload)
            self.assertNotIn("active_universe", live_payload)
            if live_payload["feed_status"]:
                self.assertNotIn("ohlc", live_payload["feed_status"][0])
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    async def test_sessions_failure_is_degraded_non_blocking(self) -> None:
        tmp_path = Path(tempfile.mkdtemp())
        try:
            storage_root = tmp_path / "storage"
            service = CoreRuntimeService(
                config=_build_config(storage_root, sessions_enabled=True),
                connector=FakeConnector(),
                sessions_service=FakeSessionsService(start_ok=False),
                indicator_bridge=FakeIndicatorBridge(),
            )
            await service.bootstrap()
            self.assertEqual(service.health["broker_sessions"], "degraded")
            live_payload = service.build_live_state()
            self.assertEqual(live_payload["status"], "up")
            await service.shutdown()
            await asyncio.sleep(0.1)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
