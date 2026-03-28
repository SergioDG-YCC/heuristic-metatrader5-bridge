"""Fast Desk per-symbol async worker - one instance per subscribed symbol."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.fast_desk.context import FastContextConfig
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyPolicyConfig
from heuristic_mt5_bridge.fast_desk.pending import FastPendingPolicyConfig
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig
from heuristic_mt5_bridge.fast_desk.state.desk_state import SymbolDeskState
from heuristic_mt5_bridge.fast_desk.trader import FastTraderConfig, FastTraderService
from heuristic_mt5_bridge.fast_desk.trigger import FastTriggerConfig


@dataclass
class FastWorkerConfig:
    scan_interval: float = 5.0
    custody_interval: float = 2.0
    signal_cooldown: float = 60.0


def _make_mt5_execute_sync(mt5_call_ref: Callable, loop: asyncio.AbstractEventLoop) -> Callable:
    """Return a *synchronous* callable that serialises through ``mt5_call_ref``.

    Safe to call from inside ``asyncio.to_thread`` workers because it submits
    the coroutine to the running event loop via ``run_coroutine_threadsafe``
    rather than trying to run a new loop.
    """
    def _execute(fn: Callable, *args: Any, **kwargs: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(mt5_call_ref(fn, *args, **kwargs), loop)
        return future.result(timeout=30)
    return _execute


class FastSymbolWorker:
    """Per-symbol async worker. Each symbol gets its own independent custody cycle."""

    def __init__(self) -> None:
        self._trader: FastTraderService | None = None

    async def run(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        config: FastWorkerConfig,
        risk_config: FastRiskConfig,
        scanner_config: Any,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable[[dict[str, Any], str, str, str | None], list[dict[str, Any]]] | None = None,
        risk_action_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        context_config: FastContextConfig | None = None,
        setup_config: FastSetupConfig | None = None,
        trigger_config: FastTriggerConfig | None = None,
        pending_config: FastPendingPolicyConfig | None = None,
        custody_config: FastCustodyPolicyConfig | None = None,
        trader_config: FastTraderConfig | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        effective_setup_config = setup_config or FastSetupConfig(
            rr_ratio=float(getattr(scanner_config, "rr_ratio", 3.0) or 3.0),
            min_confidence=float(getattr(scanner_config, "min_confidence", 0.55) or 0.55),
        )
        trader_cfg = trader_config or FastTraderConfig(
            signal_cooldown=float(config.signal_cooldown),
            enable_pending_orders=True,
            require_h1_alignment=True,
        )
        self._trader = FastTraderService(
            trader_config=trader_cfg,
            context_config=context_config or FastContextConfig(),
            setup_config=effective_setup_config,
            trigger_config=trigger_config or FastTriggerConfig(),
            pending_config=pending_config or FastPendingPolicyConfig(),
            custody_config=custody_config or FastCustodyPolicyConfig(),
        )

        state = SymbolDeskState()

        print(f"[fast-desk] worker started: {symbol}")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                self._scan_loop(
                    symbol=symbol,
                    market_state=market_state,
                    account_payload_ref=account_payload_ref,
                    connector=connector,
                    spec_registry=spec_registry,
                    db_path=db_path,
                    broker_server=broker_server,
                    account_login=account_login,
                    config=config,
                    risk_config=risk_config,
                    state=state,
                    risk_gate_ref=risk_gate_ref,
                    ownership_register_ref=ownership_register_ref,
                    ownership_open_ref=ownership_open_ref,
                    mt5_call_ref=mt5_call_ref,
                ),
                name=f"fast_scan_{symbol}",
            )
            tg.create_task(
                self._custody_loop(
                    symbol=symbol,
                    market_state=market_state,
                    account_payload_ref=account_payload_ref,
                    connector=connector,
                    spec_registry=spec_registry,
                    db_path=db_path,
                    broker_server=broker_server,
                    account_login=account_login,
                    config=config,
                    state=state,
                    risk_action_ref=risk_action_ref,
                    ownership_open_ref=ownership_open_ref,
                    mt5_call_ref=mt5_call_ref,
                ),
                name=f"fast_custody_{symbol}",
            )

    async def _scan_loop(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        config: FastWorkerConfig,
        risk_config: FastRiskConfig,
        state: SymbolDeskState,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable[[dict[str, Any], str, str, str | None], list[dict[str, Any]]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        while True:
            await self._run_scan(
                symbol=symbol,
                market_state=market_state,
                account_payload_ref=account_payload_ref,
                connector=connector,
                spec_registry=spec_registry,
                db_path=db_path,
                broker_server=broker_server,
                account_login=account_login,
                risk_config=risk_config,
                state=state,
                risk_gate_ref=risk_gate_ref,
                ownership_register_ref=ownership_register_ref,
                ownership_open_ref=ownership_open_ref,
                mt5_call_ref=mt5_call_ref,
            )
            await asyncio.sleep(config.scan_interval)

    async def _custody_loop(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        config: FastWorkerConfig,
        state: SymbolDeskState,
        risk_action_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        while True:
            await self._run_custody(
                symbol=symbol,
                market_state=market_state,
                account_payload_ref=account_payload_ref,
                connector=connector,
                spec_registry=spec_registry,
                db_path=db_path,
                broker_server=broker_server,
                account_login=account_login,
                state=state,
                risk_action_ref=risk_action_ref,
                ownership_open_ref=ownership_open_ref,
                mt5_call_ref=mt5_call_ref,
            )
            await asyncio.sleep(config.custody_interval)

    async def _run_scan(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        config: FastWorkerConfig | None = None,
        risk_config: FastRiskConfig,
        state: SymbolDeskState,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable[[dict[str, Any], str, str, str | None], list[dict[str, Any]]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        _ = config
        if self._trader is None:
            return
        # Pre-fetch tick via _mt5_lock before entering the thread so the read
        # is serialised with CoreRuntime market-state refreshes.
        prefetched_tick: dict[str, Any] | None = None
        mt5_execute_sync: Callable | None = None
        if mt5_call_ref is not None:
            loop = asyncio.get_running_loop()
            mt5_execute_sync = _make_mt5_execute_sync(mt5_call_ref, loop)
            try:
                prefetched_tick = await mt5_call_ref(connector.symbol_tick, symbol)
            except Exception:
                prefetched_tick = None
        try:
            await asyncio.to_thread(
                self._trader.scan_and_execute,
                symbol=symbol,
                market_state=market_state,
                spec_registry=spec_registry,
                account_payload_ref=account_payload_ref,
                connector=connector,
                db_path=db_path,
                broker_server=broker_server,
                account_login=account_login,
                state=state,
                risk_config=risk_config,
                risk_gate_ref=risk_gate_ref,
                ownership_register_ref=ownership_register_ref,
                ownership_open_ref=ownership_open_ref,
                prefetched_tick=prefetched_tick,
                mt5_execute_sync=mt5_execute_sync,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[fast-desk] scan error ({symbol}): {exc}")

    async def _run_custody(
        self,
        *,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        state: SymbolDeskState,
        risk_action_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        if self._trader is None:
            return
        # Pre-fetch tick via _mt5_lock; also build sync executor for write calls.
        prefetched_tick: dict[str, Any] | None = None
        mt5_execute_sync: Callable | None = None
        if mt5_call_ref is not None:
            loop = asyncio.get_running_loop()
            mt5_execute_sync = _make_mt5_execute_sync(mt5_call_ref, loop)
            try:
                prefetched_tick = await mt5_call_ref(connector.symbol_tick, symbol)
            except Exception:
                prefetched_tick = None
        try:
            await asyncio.to_thread(
                self._trader.run_custody,
                symbol=symbol,
                market_state=market_state,
                spec_registry=spec_registry,
                account_payload_ref=account_payload_ref,
                connector=connector,
                db_path=db_path,
                broker_server=broker_server,
                account_login=account_login,
                state=state,
                risk_action_ref=risk_action_ref,
                ownership_open_ref=ownership_open_ref,
                prefetched_tick=prefetched_tick,
                mt5_execute_sync=mt5_execute_sync,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[fast-desk] custody error ({symbol}): {exc}")
