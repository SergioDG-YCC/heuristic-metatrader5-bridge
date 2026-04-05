"""SMC Symbol Worker — async loop per symbol for thesis monitoring + custody."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.smc_desk.state.thesis_store import load_recent_smc_thesis
from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig
from heuristic_mt5_bridge.smc_desk.trader.service import SmcTraderService

logger = logging.getLogger("smc_desk.trader.worker")


class SmcSymbolWorker:
    """Monitors a single symbol: reads thesis, manages pending orders, runs custody."""

    def __init__(self, *, trader: SmcTraderService, config: SmcTraderConfig) -> None:
        self._trader = trader
        self._config = config

    async def run(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        spec_registry: SymbolSpecRegistry,
        connector: Any,
        account_payload_ref: Callable[[], dict[str, Any]],
        db_path: Path,
        broker_server: str,
        account_login: int,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        logger.info("[%s] smc worker started", symbol)
        interval = max(5.0, self._config.custody_interval_seconds)

        while True:
            try:
                await self._tick(
                    symbol=symbol,
                    market_state=market_state,
                    spec_registry=spec_registry,
                    connector=connector,
                    account_payload_ref=account_payload_ref,
                    db_path=db_path,
                    broker_server=broker_server,
                    account_login=account_login,
                    risk_gate_ref=risk_gate_ref,
                    ownership_register_ref=ownership_register_ref,
                    ownership_open_ref=ownership_open_ref,
                    mt5_call_ref=mt5_call_ref,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[%s] worker tick error: %s", symbol, exc)

            await asyncio.sleep(interval)

    async def _tick(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        spec_registry: SymbolSpecRegistry,
        connector: Any,
        account_payload_ref: Callable[[], dict[str, Any]],
        db_path: Path,
        broker_server: str,
        account_login: int,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        pip_size = spec_registry.pip_size(symbol)
        if not pip_size:
            return
        symbol_spec = spec_registry.get(symbol) or {}

        thesis = await asyncio.to_thread(
            load_recent_smc_thesis,
            db_path,
            broker_server=broker_server,
            account_login=account_login,
            symbol=symbol,
        )

        payload = account_payload_ref()
        account_state = payload.get("account_state", {}) if isinstance(payload, dict) else {}
        all_positions = payload.get("positions", []) if isinstance(payload, dict) else []
        all_orders = payload.get("orders", []) if isinstance(payload, dict) else []

        smc_owned: list[dict[str, Any]] = []
        if ownership_open_ref is not None:
            smc_owned = ownership_open_ref()

        smc_position_ids = {
            int(op.get("mt5_position_id", 0) or 0)
            for op in smc_owned
            if str(op.get("operation_type", "")).lower() == "position"
            and str(op.get("lifecycle_status", "")).lower() == "active"
        }
        smc_order_ids = {
            int(op.get("mt5_order_id", 0) or 0)
            for op in smc_owned
            if str(op.get("operation_type", "")).lower() == "order"
            and str(op.get("lifecycle_status", "")).lower() == "active"
        }

        sym_upper = symbol.upper()
        my_positions = [
            p for p in all_positions
            if str(p.get("symbol", "")).upper() == sym_upper
            and int(p.get("position_id", 0) or 0) in smc_position_ids
        ]
        my_orders = [
            o for o in all_orders
            if str(o.get("symbol", "")).upper() == sym_upper
            and int(o.get("order_id", 0) or 0) in smc_order_ids
        ]

        candles = market_state.get_candles(symbol, "M5", 5)
        if candles:
            last = candles[-1]
            current_price = float(last.get("close", 0) or 0)
        else:
            current_price = 0.0

        # Try M1 for a more recent price if available
        m1 = market_state.get_candles(symbol, "M1", 1)
        if m1:
            current_price = float(m1[-1].get("close", 0) or current_price)

        if current_price <= 0:
            return

        # Capture the running event loop BEFORE entering thread pool workers,
        # so _mt5_sync can schedule coroutines back on it.
        _loop = asyncio.get_running_loop()

        def _mt5_sync(fn: Any, *args: Any, **kwargs: Any) -> Any:
            if mt5_call_ref is not None:
                future = asyncio.run_coroutine_threadsafe(
                    mt5_call_ref(fn, *args, **kwargs), _loop
                )
                return future.result(timeout=30)
            return fn(*args, **kwargs)

        if my_positions:
            await asyncio.to_thread(
                self._trader.run_custody,
                symbol=symbol,
                positions=my_positions,
                thesis=thesis,
                pip_size=float(pip_size),
                connector=connector,
                mt5_execute_sync=_mt5_sync,
            )

        if my_orders:
            await asyncio.to_thread(
                self._trader.reconcile_pending_orders,
                symbol=symbol,
                orders=my_orders,
                thesis=thesis,
                current_price=current_price,
                pip_size=float(pip_size),
                connector=connector,
                mt5_execute_sync=_mt5_sync,
            )

        if not my_positions and not my_orders and thesis:
            smc_owned_for_policy = [
                op for op in smc_owned
                if str(op.get("lifecycle_status", "")).lower() == "active"
            ]
            await asyncio.to_thread(
                self._trader.process_thesis,
                symbol=symbol,
                thesis=thesis,
                smc_owned_operations=smc_owned_for_policy,
                current_price=current_price,
                pip_size=float(pip_size),
                symbol_spec=symbol_spec,
                account_state=account_state,
                connector=connector,
                risk_gate_ref=risk_gate_ref,
                ownership_register_ref=ownership_register_ref,
                mt5_execute_sync=_mt5_sync,
            )
