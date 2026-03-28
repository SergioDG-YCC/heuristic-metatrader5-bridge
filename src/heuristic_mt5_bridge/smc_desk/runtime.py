"""
SmcDeskService — orchestrates scanner + analyst for SMC desk.

Wires the scanner's event callbacks to async analyst trigger dispatch.
Designed to run as a single asyncio task inside CoreRuntimeService.run_forever().

Trigger flow:
    SmcScannerService → _on_scanner_event() → asyncio.Queue → _dispatch_loop()
    → run_smc_heuristic_analyst() (one call per event, throttled per symbol)
"""
from __future__ import annotations

import asyncio
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
    ) -> None:
        self._scanner = scanner
        self._analyst_config = analyst_config
        self._db_path = db_path
        self._analyst_cooldown = analyst_cooldown

        # Queue receives (event_type, symbol, payload)
        self._event_queue: asyncio.Queue[tuple[str, str, dict[str, Any]]] = asyncio.Queue(maxsize=256)
        # Tracks last analyst run time per symbol (monotonic)
        self._last_analyst_run: dict[str, float] = {}

        # Will be populated on run_forever()
        self._service: MarketStateService | None = None
        self._broker_server: str = ""
        self._account_login: int = 0
        self._spec_registry: SymbolSpecRegistry | None = None
        # Authority hooks — populated when SMC trader is enabled (Step 4)
        self._risk_gate_ref: Callable[[str], dict[str, Any]] | None = None
        self._ownership_register_ref: Callable | None = None

    # -----------------------------------------------------------------------
    # Scanner event bridge (called synchronously from scanner thread)
    # -----------------------------------------------------------------------

    def _on_scanner_event(self, event_type: str, symbol: str, payload: dict[str, Any]) -> None:
        """Receive scanner events and enqueue analyst trigger if applicable."""
        if event_type not in _ANALYST_TRIGGER_EVENTS:
            return
        try:
            self._event_queue.put_nowait((event_type, symbol, payload))
        except asyncio.QueueFull:
            print(f"[smc-desk] event queue full — dropping {event_type}/{symbol}")

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
            asyncio.create_task(
                self._run_analyst_safe(
                    symbol=symbol,
                    trigger_reason=event_type,
                    trigger_payload=payload,
                )
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
    ) -> None:
        """Start SMC desk: register callback, launch scanner + dispatch loop.

        Parameters
        ----------
        risk_gate_ref          : Delegates to ``RiskKernel.evaluate_entry(desk='smc', ...)``.
                                 Required when ``SMC_TRADER_ENABLED=true`` (Step 4).
        ownership_register_ref : Registers executed orders via ``OwnershipRegistry``.
                                 Required when ``SMC_TRADER_ENABLED=true`` (Step 4).

        This coroutine runs indefinitely and should be launched as an asyncio task.
        Cancellation propagates cleanly to sub-tasks.
        """
        self._service = service
        self._broker_server = broker_server
        self._account_login = account_login
        self._spec_registry = spec_registry
        self._risk_gate_ref = risk_gate_ref
        self._ownership_register_ref = ownership_register_ref

        # Register scanner event callback (module-level list in scanner.py)
        register_smc_event_callback(self._on_scanner_event)

        print(
            f"[smc-desk] starting — "
            f"broker={broker_server} account={account_login} "
            f"llm_enabled={self._analyst_config.llm_enabled}"
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


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_smc_desk_service(db_path: Path) -> SmcDeskService:
    """Build SmcDeskService from environment variables."""
    scanner_config = SmcScannerConfig.from_env()
    analyst_config = SmcAnalystConfig.from_env()
    scanner = SmcScannerService(config=scanner_config, db_path=db_path)
    analyst_cooldown = float(os.getenv("SMC_ANALYST_COOLDOWN_SECONDS", "300"))
    return SmcDeskService(
        scanner=scanner,
        analyst_config=analyst_config,
        db_path=db_path,
        analyst_cooldown=analyst_cooldown,
    )
