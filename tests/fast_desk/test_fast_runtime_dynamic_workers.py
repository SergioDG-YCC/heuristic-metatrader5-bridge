from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from heuristic_mt5_bridge.fast_desk.runtime import FastDeskConfig, FastDeskService
from heuristic_mt5_bridge.fast_desk.workers.symbol_worker import FastSymbolWorker
from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.trader import FastTraderConfig


class FastDeskDynamicWorkersTest(unittest.IsolatedAsyncioTestCase):
    async def test_fast_desk_adds_new_worker_when_symbol_supplier_changes(self) -> None:
        service = FastDeskService(
            db_path=Path("runtime.db"),
            config=FastDeskConfig(scan_interval=0.05, guard_interval=0.05, allowed_sessions=("global",)),
        )
        active_symbols = ["EURUSD"]
        started: list[str] = []
        eurusd_started = asyncio.Event()
        gbpusd_started = asyncio.Event()

        async def fake_run(self, **kwargs):  # type: ignore[no-untyped-def]
            symbol = kwargs["symbol"]
            started.append(symbol)
            if symbol == "EURUSD":
                eurusd_started.set()
            if symbol == "GBPUSD":
                gbpusd_started.set()
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise

        with patch.object(FastSymbolWorker, "run", fake_run):
            task = asyncio.create_task(
                service.run_forever(
                    market_state=object(),
                    broker_server="Broker-1",
                    account_login=123456,
                    spec_registry=object(),
                    connector=object(),
                    account_payload_ref=lambda: {},
                    subscribed_symbols_ref=lambda: list(active_symbols),
                )
            )
            try:
                await asyncio.wait_for(eurusd_started.wait(), timeout=1.0)
                active_symbols.append("GBPUSD")
                await asyncio.wait_for(gbpusd_started.wait(), timeout=1.0)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        self.assertEqual(started.count("EURUSD"), 1)
        self.assertEqual(started.count("GBPUSD"), 1)

    def test_update_context_config_propagates_live_rr_and_trader_changes(self) -> None:
        service = FastDeskService(
            db_path=Path("runtime.db"),
            config=FastDeskConfig(),
        )
        service._setup_config = FastSetupConfig(rr_ratio=3.0)
        service._risk_config = FastRiskConfig(risk_per_trade_percent=1.0, max_positions_per_symbol=1, max_positions_total=4)
        service._trader_config = FastTraderConfig(signal_cooldown=60.0, enable_pending_orders=True, require_h1_alignment=True)

        updated = FastDeskConfig(rr_ratio=4.2, risk_per_trade_percent=1.5, signal_cooldown=15.0, max_positions_total=6)
        service.update_context_config(updated)

        self.assertEqual(service._setup_config.rr_ratio, 4.2)
        self.assertEqual(service._setup_config.min_rr, 3.0)
        self.assertEqual(service._risk_config.risk_per_trade_percent, 1.5)
        self.assertEqual(service._risk_config.max_positions_total, 6)
        self.assertEqual(service._trader_config.signal_cooldown, 15.0)
