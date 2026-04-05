"""
SmcDeskService — orchestrates scanner + analyst + trader for SMC desk.

Wires the scanner's event callbacks to async analyst trigger dispatch.
Optionally launches per-symbol trader workers when SMC_TRADER_ENABLED=true.
Designed to run as a single asyncio task inside CoreRuntimeService.run_forever().

Trigger flow:
    SmcScannerService → _on_scanner_event() → asyncio.Queue → _dispatch_loop()
    → run_smc_heuristic_analyst() (one call per event, throttled per symbol)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import (
    SmcAnalystConfig,
    run_smc_heuristic_analyst,
)
from heuristic_mt5_bridge.smc_desk.scanner.scanner import (
    SmcScannerConfig,
    SmcScannerService,
    register_smc_event_callback,
)
from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig
from heuristic_mt5_bridge.smc_desk.trader.service import SmcTraderService
from heuristic_mt5_bridge.smc_desk.trader.worker import SmcSymbolWorker

logger = logging.getLogger("smc_desk.runtime")

# Events that warrant an immediate analyst trigger
_ANALYST_TRIGGER_EVENTS = frozenset({
    "zone_approaching",
    "sweep_detected",
    "zone_invalidated",
    "new_zone_detected",
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SmcDeskService:
    """Lightweight orchestrator for the SMC desk.

    Parameters
    ----------
    scanner          : Configured SmcScannerService.
    analyst_config   : Config for heuristic analyst + LLM validator.
    db_path          : Runtime SQLite database path.
    analyst_cooldown : Minimum seconds between analyst runs per symbol.
    """

    def __init__(
        self,
        *,
        scanner: SmcScannerService,
        analyst_config: SmcAnalystConfig,
        db_path: Path,
        analyst_cooldown: float = 300.0,
        trader_config: SmcTraderConfig | None = None,
        correlation_formatter: Any | None = None,
    ) -> None:
        self._scanner = scanner
        self._analyst_config = analyst_config
        self._db_path = db_path
        self._analyst_cooldown = analyst_cooldown
        self._trader_config = trader_config or SmcTraderConfig()
        self._correlation_formatter = correlation_formatter

        # Queue receives (event_type, symbol, payload)
        self._event_queue: asyncio.Queue[tuple[str, str, dict[str, Any]]] = asyncio.Queue(maxsize=256)
        # Tracks last analyst run time per symbol (monotonic)
        self._last_analyst_run: dict[str, float] = {}

        # Will be populated on run_forever()
        self._service: MarketStateService | None = None
        self._broker_server: str = ""
        self._account_login: int = 0
        self._spec_registry: SymbolSpecRegistry | None = None
        # Authority hooks
        self._risk_gate_ref: Callable[[str], dict[str, Any]] | None = None
        self._ownership_register_ref: Callable | None = None
        self._ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None
        self._connector: Any = None
        self._account_payload_ref: Callable[[], dict[str, Any]] | None = None
        self._mt5_call_ref: Callable | None = None

        # Trader service (created lazily — may be enabled at runtime via WebUI)
        self._trader: SmcTraderService | None = None
        if self._trader_config.enabled:
            self._trader = SmcTraderService(config=self._trader_config)

        # Dedup set: track symbols already enqueued but not yet consumed
        self._enqueued_symbols: set[str] = set()

    # -----------------------------------------------------------------------
    # Scanner event bridge (called synchronously from scanner thread)
    # -----------------------------------------------------------------------

    def _on_scanner_event(self, event_type: str, symbol: str, payload: dict[str, Any]) -> None:
        """Receive scanner events and enqueue analyst trigger if applicable."""
        if event_type not in _ANALYST_TRIGGER_EVENTS:
            return
        # Deduplicate: if this symbol already has a pending event, skip
        if symbol in self._enqueued_symbols:
            return
        try:
            self._event_queue.put_nowait((event_type, symbol, payload))
            self._enqueued_symbols.add(symbol)
        except asyncio.QueueFull:
            logger.warning("event queue full — dropping %s/%s", event_type, symbol)

    # -----------------------------------------------------------------------
    # Analyst dispatch loop
    # -----------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """Consume events from the queue and trigger analyst runs."""
        while True:
            try:
                event_type, symbol, payload = await asyncio.wait_for(
                    self._event_queue.get(), timeout=60.0
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            # Release dedup slot so new events for this symbol can enqueue
            self._enqueued_symbols.discard(symbol)

            # Throttle: skip if analyst ran recently for this symbol
            now = asyncio.get_event_loop().time()
            last = self._last_analyst_run.get(symbol, 0.0)
            if now - last < self._analyst_cooldown:
                self._event_queue.task_done()
                continue

            if not self._service or not self._spec_registry:
                self._event_queue.task_done()
                continue

            self._last_analyst_run[symbol] = now
            await self._run_analyst_safe(
                symbol=symbol,
                trigger_reason=event_type,
                trigger_payload=payload,
            )
            self._event_queue.task_done()

    async def _run_analyst_safe(
        self,
        *,
        symbol: str,
        trigger_reason: str,
        trigger_payload: dict[str, Any],
    ) -> None:
        """Run analyst and log any errors without crashing the dispatch loop."""
        try:
            result = await run_smc_heuristic_analyst(
                symbol=symbol,
                trigger_reason=trigger_reason,
                trigger_payload=trigger_payload,
                service=self._service,
                db_path=self._db_path,
                broker_server=self._broker_server,
                account_login=self._account_login,
                spec_registry=self._spec_registry,
                config=self._analyst_config,
                correlation_formatter=self._correlation_formatter,
            )
            thesis = result.get("thesis", {})
            print(
                f"[smc-desk] analyst done {symbol} "
                f"bias={thesis.get('bias', '?')} "
                f"status={thesis.get('status', '?')} "
                f"candidates={len(thesis.get('operation_candidates', []))}"
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[smc-desk] analyst error ({symbol}/{trigger_reason}): {exc}")

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    async def run_forever(
        self,
        service: MarketStateService,
        broker_server: str,
        account_login: int,
        spec_registry: SymbolSpecRegistry,
        symbols_ref: Callable[[], list[str]] | None = None,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable | None = None,
        connector: Any = None,
        account_payload_ref: Callable[[], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        """Start SMC desk: register callback, launch scanner + dispatch loop + trader.

        Parameters
        ----------
        risk_gate_ref          : Delegates to ``RiskKernel.evaluate_entry(desk='smc', ...)``.
        ownership_register_ref : Registers executed orders via ``OwnershipRegistry``.
        connector              : MT5Connector for order execution (required when trader enabled).
        account_payload_ref    : Returns current account state dict.
        ownership_open_ref     : Returns list of SMC-owned open operations.
        mt5_call_ref           : Thread-safe MT5 call wrapper.
        """
        self._service = service
        self._broker_server = broker_server
        self._account_login = account_login
        self._spec_registry = spec_registry
        self._risk_gate_ref = risk_gate_ref
        self._ownership_register_ref = ownership_register_ref
        self._connector = connector
        self._account_payload_ref = account_payload_ref
        self._ownership_open_ref = ownership_open_ref
        self._mt5_call_ref = mt5_call_ref

        # Register scanner event callback (module-level list in scanner.py)
        register_smc_event_callback(self._on_scanner_event)

        trader_label = "ENABLED" if self._trader is not None else "disabled (can be enabled at runtime)"
        print(
            f"[smc-desk] starting — "
            f"broker={broker_server} account={account_login} "
            f"llm_enabled={self._analyst_config.llm_enabled} "
            f"trader={trader_label}"
        )

        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                self._scanner.run_forever(
                    service,
                    broker_server,
                    account_login,
                    symbols_ref=symbols_ref,
                ),
                name="smc_scanner",
            )
            tg.create_task(self._dispatch_loop(), name="smc_analyst_dispatch")

            # Always launch reconciliation loop — it checks trader_config.enabled
            # dynamically so the trader can be activated via WebUI without restart.
            if connector is not None:
                tg.create_task(
                    self._trader_reconciliation_loop(symbols_ref=symbols_ref),
                    name="smc_trader_reconciliation",
                )

    # -----------------------------------------------------------------------
    # Trader worker management
    # -----------------------------------------------------------------------

    def _ensure_trader(self) -> SmcTraderService:
        """Create SmcTraderService on-demand (first call or config change)."""
        if self._trader is None:
            self._trader = SmcTraderService(config=self._trader_config)
            logger.info("smc trader service created (enabled at runtime)")
        else:
            # Keep config in sync if updated via WebUI
            self._trader.config = self._trader_config
            self._trader.entry_policy._config = self._trader_config
        return self._trader

    async def _trader_reconciliation_loop(
        self,
        *,
        symbols_ref: Callable[[], list[str]] | None = None,
    ) -> None:
        """Periodically check subscribed symbols and spawn/despawn trader workers."""
        worker_tasks: dict[str, asyncio.Task[None]] = {}
        reconcile_interval = 15.0

        while True:
            try:
                # Check if trader is enabled (can change at runtime via WebUI)
                if not self._trader_config.enabled:
                    # Cancel all workers if trader was disabled
                    for sym in list(worker_tasks):
                        task = worker_tasks.pop(sym)
                        task.cancel()
                        logger.info("cancelled smc trader worker for %s (trader disabled)", sym)
                    await asyncio.sleep(reconcile_interval)
                    continue

                trader = self._ensure_trader()

                desired = set()
                if symbols_ref is not None:
                    desired = {s.upper() for s in symbols_ref()}
                else:
                    desired = set()

                # Spawn new workers
                for sym in desired:
                    if sym not in worker_tasks or worker_tasks[sym].done():
                        worker = SmcSymbolWorker(trader=trader, config=self._trader_config)
                        worker_tasks[sym] = asyncio.create_task(
                            worker.run(
                                symbol=sym,
                                market_state=self._service,
                                spec_registry=self._spec_registry,
                                connector=self._connector,
                                account_payload_ref=self._account_payload_ref or (lambda: {}),
                                db_path=self._db_path,
                                broker_server=self._broker_server,
                                account_login=self._account_login,
                                risk_gate_ref=self._risk_gate_ref,
                                ownership_register_ref=self._ownership_register_ref,
                                ownership_open_ref=self._ownership_open_ref,
                                mt5_call_ref=self._mt5_call_ref,
                            ),
                            name=f"smc_trader_{sym}",
                        )
                        logger.info("spawned smc trader worker for %s", sym)

                # Cancel workers for removed symbols
                for sym in list(worker_tasks):
                    if sym not in desired:
                        task = worker_tasks.pop(sym)
                        task.cancel()
                        logger.info("cancelled smc trader worker for %s", sym)

            except asyncio.CancelledError:
                for task in worker_tasks.values():
                    task.cancel()
                raise
            except Exception as exc:
                logger.error("smc trader reconciliation error: %s", exc)

            await asyncio.sleep(reconcile_interval)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_smc_desk_service(
    db_path: Path,
    correlation_service: Any | None = None,
) -> SmcDeskService:
    """Build SmcDeskService from environment variables."""
    scanner_config = SmcScannerConfig.from_env()
    analyst_config = SmcAnalystConfig.from_env()
    scanner = SmcScannerService(config=scanner_config, db_path=db_path)
    analyst_cooldown = float(os.getenv("SMC_ANALYST_COOLDOWN_SECONDS", "300"))
    trader_config = SmcTraderConfig.from_env()
    formatter = None
    if correlation_service is not None:
        from heuristic_mt5_bridge.smc_desk.correlation.formatter import SmcCorrelationFormatter  # noqa: PLC0415
        formatter = SmcCorrelationFormatter(correlation_service, timeframe="H1", top_n=5)
    return SmcDeskService(
        scanner=scanner,
        analyst_config=analyst_config,
        db_path=db_path,
        analyst_cooldown=analyst_cooldown,
        trader_config=trader_config,
        correlation_formatter=formatter,
    )
