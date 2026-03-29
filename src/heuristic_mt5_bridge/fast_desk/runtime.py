"""Fast Desk runtime orchestrator - creates per-symbol workers and manages lifecycle."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService, session_name_from_timestamp
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.fast_desk.context import FastContextConfig
from heuristic_mt5_bridge.fast_desk.context.service import DEFAULT_SPREAD_THRESHOLDS
from heuristic_mt5_bridge.fast_desk.custody import FastCustodyPolicyConfig
from heuristic_mt5_bridge.fast_desk.pending import FastPendingPolicyConfig
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig
from heuristic_mt5_bridge.fast_desk.signals.scanner import FastScannerConfig
from heuristic_mt5_bridge.fast_desk.trader import FastTraderConfig
from heuristic_mt5_bridge.fast_desk.trigger import FastTriggerConfig
from heuristic_mt5_bridge.fast_desk.workers.symbol_worker import FastSymbolWorker, FastWorkerConfig
from heuristic_mt5_bridge.infra.sessions import registry as session_registry
from heuristic_mt5_bridge.infra.sessions.gate import is_trade_open_from_registry
from heuristic_mt5_bridge.shared.symbols.universe import is_operable_symbol, normalize_symbol

logger = logging.getLogger("fast_desk.runtime")


def _getenv_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _getenv_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _getenv_alias_float(primary: str, legacy: str, default: float) -> float:
    if os.getenv(primary, "").strip():
        return _getenv_float(primary, default)
    return _getenv_float(legacy, default)


def _getenv_alias_int(primary: str, legacy: str, default: int) -> int:
    if os.getenv(primary, "").strip():
        return _getenv_int(primary, default)
    return _getenv_int(legacy, default)


def _getenv_alias_bool(primary: str, legacy: str, default: bool) -> bool:
    if os.getenv(primary, "").strip():
        return _getenv_bool(primary, default)
    return _getenv_bool(legacy, default)


_VALID_SESSIONS = {"tokyo", "london", "overlap", "new_york", "all_markets", "global"}
_VALID_SPREAD_LEVELS = {"low", "medium", "high"}


def _parse_allowed_sessions() -> tuple[str, ...]:
    raw = os.getenv("FAST_TRADER_ALLOWED_SESSIONS", "").strip()
    if not raw:
        return ("london", "overlap", "new_york")
    parts = tuple(s.strip().lower() for s in raw.split(",") if s.strip())
    valid = tuple(s for s in parts if s in _VALID_SESSIONS)
    return valid if valid else ("london", "overlap", "new_york")


def _parse_spread_tolerance() -> str:
    raw = os.getenv("FAST_TRADER_SPREAD_TOLERANCE", "").strip().lower()
    if raw in _VALID_SPREAD_LEVELS:
        return raw
    # Legacy fallback: if old env var is set, default to "medium"
    if os.getenv("FAST_TRADER_SPREAD_MAX_PIPS", "").strip():
        import logging
        logging.getLogger("fast_desk.runtime").warning(
            "FAST_TRADER_SPREAD_MAX_PIPS is deprecated. Use FAST_TRADER_SPREAD_TOLERANCE=low|medium|high"
        )
    return "medium"


@dataclass
class FastDeskConfig:
    scan_interval: float = 5.0
    guard_interval: float = 2.0
    signal_cooldown: float = 60.0
    risk_per_trade_percent: float = 1.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 4
    max_lot_size: float = 10.0
    min_signal_confidence: float = 0.60
    atr_multiplier_sl: float = 1.5
    rr_ratio: float = 3.0
    min_rr: float = 3.0

    spread_tolerance: str = "medium"  # "low" | "medium" | "high"
    max_slippage_pct: float = 0.05     # context gate: max tick-vs-candle % divergence
    require_h1_alignment: bool = True
    enable_pending_orders: bool = True
    enable_structural_trailing: bool = True
    enable_atr_trailing: bool = True
    enable_scale_out: bool = False
    pending_ttl_seconds: int = 900
    adoption_grace_seconds: float = 120.0
    allowed_sessions: tuple[str, ...] = ("london", "overlap", "new_york")
    spread_thresholds: dict[str, dict[str, float]] = field(default_factory=lambda: {
        level: dict(values) for level, values in DEFAULT_SPREAD_THRESHOLDS.items()
    })

    @classmethod
    def from_env(cls) -> "FastDeskConfig":
        return cls(
            scan_interval=_getenv_alias_float("FAST_TRADER_SCAN_INTERVAL", "FAST_DESK_SCAN_INTERVAL", 5.0),
            guard_interval=_getenv_alias_float("FAST_TRADER_GUARD_INTERVAL", "FAST_DESK_CUSTODY_INTERVAL", 2.0),
            signal_cooldown=_getenv_alias_float("FAST_TRADER_SIGNAL_COOLDOWN", "FAST_DESK_SIGNAL_COOLDOWN", 60.0),
            risk_per_trade_percent=_getenv_alias_float("FAST_TRADER_RISK_PERCENT", "FAST_DESK_RISK_PERCENT", 1.0),
            max_positions_per_symbol=_getenv_alias_int(
                "FAST_TRADER_MAX_POSITIONS_PER_SYMBOL", "FAST_DESK_MAX_POSITIONS_PER_SYMBOL", 1
            ),
            max_positions_total=_getenv_alias_int("FAST_TRADER_MAX_POSITIONS_TOTAL", "FAST_DESK_MAX_POSITIONS_TOTAL", 4),
            max_lot_size=_getenv_alias_float("FAST_TRADER_MAX_LOT_SIZE", "FAST_DESK_MAX_LOT_SIZE", 10.0),
            min_signal_confidence=_getenv_alias_float("FAST_TRADER_MIN_CONFIDENCE", "FAST_DESK_MIN_CONFIDENCE", 0.60),
            atr_multiplier_sl=_getenv_alias_float("FAST_TRADER_ATR_MULTIPLIER_SL", "FAST_DESK_ATR_MULTIPLIER_SL", 1.5),
            rr_ratio=_getenv_alias_float("FAST_TRADER_RR_RATIO", "FAST_DESK_RR_RATIO", 3.0),
            min_rr=_getenv_alias_float("FAST_TRADER_MIN_RR", "FAST_DESK_MIN_RR", 3.0),
            spread_tolerance=_parse_spread_tolerance(),
            max_slippage_pct=_getenv_float("FAST_TRADER_MAX_SLIPPAGE_PCT", 0.05),
            require_h1_alignment=_getenv_bool("FAST_TRADER_REQUIRE_H1_ALIGNMENT", True),
            enable_pending_orders=_getenv_bool("FAST_TRADER_ENABLE_PENDING_ORDERS", True),
            enable_structural_trailing=_getenv_bool("FAST_TRADER_ENABLE_STRUCTURAL_TRAILING", True),
            enable_atr_trailing=_getenv_bool("FAST_TRADER_ENABLE_ATR_TRAILING", True),
            enable_scale_out=_getenv_bool("FAST_TRADER_ENABLE_SCALE_OUT", False),
            pending_ttl_seconds=_getenv_int("FAST_TRADER_PENDING_TTL_SECONDS", 900),
            adoption_grace_seconds=_getenv_float("FAST_TRADER_ADOPTION_GRACE_SECONDS", 120.0),
            allowed_sessions=_parse_allowed_sessions(),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize config to dict for API response."""
        return {
            "scan_interval": self.scan_interval,
            "guard_interval": self.guard_interval,
            "signal_cooldown": self.signal_cooldown,
            "risk_per_trade_percent": self.risk_per_trade_percent,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "max_positions_total": self.max_positions_total,
            "max_lot_size": self.max_lot_size,
            "min_signal_confidence": self.min_signal_confidence,
            "atr_multiplier_sl": self.atr_multiplier_sl,
            "rr_ratio": self.rr_ratio,
            "min_rr": self.min_rr,
            "spread_tolerance": self.spread_tolerance,
            "max_slippage_pct": self.max_slippage_pct,
            "require_h1_alignment": self.require_h1_alignment,
            "enable_pending_orders": self.enable_pending_orders,
            "enable_structural_trailing": self.enable_structural_trailing,
            "enable_atr_trailing": self.enable_atr_trailing,
            "enable_scale_out": self.enable_scale_out,
            "pending_ttl_seconds": self.pending_ttl_seconds,
            "adoption_grace_seconds": self.adoption_grace_seconds,
            "allowed_sessions": list(self.allowed_sessions),
            "spread_thresholds": self.spread_thresholds,
        }


class FastDeskService:
    """Orchestrates per-symbol workers for the FastTraderService."""

    def __init__(self, *, db_path: Path, config: FastDeskConfig) -> None:
        self._db_path = db_path
        self._config = config
        self._context_config: FastContextConfig | None = None
        self._risk_config: FastRiskConfig | None = None
        self._setup_config: Any | None = None
        self._pending_config: FastPendingPolicyConfig | None = None
        self._custody_config: FastCustodyPolicyConfig | None = None
        self._trader_config: FastTraderConfig | None = None

    def update_context_config(self, cfg: FastDeskConfig) -> None:
        """Hot-reload live config from updated FastDeskConfig (called by API)."""
        if self._context_config is not None:
            self._context_config.spread_tolerance = cfg.spread_tolerance
            self._context_config.allowed_sessions = cfg.allowed_sessions
            self._context_config.max_slippage_pct = cfg.max_slippage_pct
            self._context_config.require_h1_alignment = cfg.require_h1_alignment
            self._context_config.spread_thresholds = cfg.spread_thresholds
        if self._risk_config is not None:
            self._risk_config.risk_per_trade_percent = cfg.risk_per_trade_percent
            self._risk_config.max_positions_per_symbol = cfg.max_positions_per_symbol
            self._risk_config.max_positions_total = cfg.max_positions_total
            self._risk_config.max_lot_size = cfg.max_lot_size
        if self._setup_config is not None:
            self._setup_config.rr_ratio = cfg.rr_ratio
            self._setup_config.min_rr = cfg.min_rr
            self._setup_config.min_confidence = cfg.min_signal_confidence
        if self._pending_config is not None:
            self._pending_config.pending_ttl_seconds = cfg.pending_ttl_seconds
        if self._custody_config is not None:
            self._custody_config.enable_atr_trailing = cfg.enable_atr_trailing
            self._custody_config.enable_structural_trailing = cfg.enable_structural_trailing
            self._custody_config.enable_scale_out = cfg.enable_scale_out
        if self._trader_config is not None:
            self._trader_config.signal_cooldown = cfg.signal_cooldown
            self._trader_config.enable_pending_orders = cfg.enable_pending_orders
            self._trader_config.require_h1_alignment = cfg.require_h1_alignment
            self._trader_config.adoption_grace_seconds = cfg.adoption_grace_seconds

    # ------------------------------------------------------------------
    # Market-gate event emitter (consumed by activity_log ring buffer)
    # ------------------------------------------------------------------
    _market_gate_ring: dict[str, dict[str, Any]] = {}  # symbol → last gate event

    @classmethod
    def _emit_market_gate(cls, symbol: str, reason: str) -> None:
        """Record a market-gate state change for *symbol*.

        Stored in a class-level dict so WebUI / SMC / any consumer can query
        ``FastDeskService.get_market_gates()`` without coupling to a specific
        instance.  The dict is intentionally small (one entry per symbol).
        """
        cls._market_gate_ring[symbol.upper()] = {
            "symbol": symbol.upper(),
            "gate": reason,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    @classmethod
    def get_market_gates(cls) -> dict[str, dict[str, Any]]:
        """Return current market-gate state per symbol (snapshot)."""
        return dict(cls._market_gate_ring)

    async def run_forever(
        self,
        market_state: MarketStateService,
        broker_server: str,
        account_login: int,
        spec_registry: SymbolSpecRegistry,
        connector: Any,
        account_payload_ref: Callable[[], dict],
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable[[dict[str, Any], str, str, str | None], list[dict[str, Any]]] | None = None,
        risk_action_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_open_ref: Callable[[], list[dict[str, Any]]] | None = None,
        subscribed_symbols_ref: Callable[[], list[str]] | None = None,
        mt5_call_ref: Callable | None = None,
    ) -> None:
        cfg = self._config
        worker_config = FastWorkerConfig(
            scan_interval=cfg.scan_interval,
            custody_interval=cfg.guard_interval,
            signal_cooldown=cfg.signal_cooldown,
        )
        risk_config = FastRiskConfig(
            risk_per_trade_percent=cfg.risk_per_trade_percent,
            max_positions_per_symbol=cfg.max_positions_per_symbol,
            max_positions_total=cfg.max_positions_total,
            max_lot_size=cfg.max_lot_size,
        )
        scanner_config = FastScannerConfig(
            min_confidence=cfg.min_signal_confidence,
            atr_multiplier_sl=cfg.atr_multiplier_sl,
            rr_ratio=cfg.rr_ratio,
        )
        from heuristic_mt5_bridge.fast_desk.setup import FastSetupConfig
        setup_config = FastSetupConfig(
            rr_ratio=cfg.rr_ratio,
            min_confidence=cfg.min_signal_confidence,
            min_rr=cfg.min_rr,
        )
        context_config = FastContextConfig(
            spread_tolerance=cfg.spread_tolerance,
            max_slippage_pct=cfg.max_slippage_pct,
            stale_feed_seconds=180,
            require_h1_alignment=cfg.require_h1_alignment,
            allowed_sessions=cfg.allowed_sessions,
            spread_thresholds=cfg.spread_thresholds,
        )
        self._context_config = context_config
        trigger_config = FastTriggerConfig(displacement_body_factor=1.8)
        pending_config = FastPendingPolicyConfig(
            pending_ttl_seconds=cfg.pending_ttl_seconds,
            reprice_threshold_pips=8.0,
            reprice_buffer_pips=1.0,
        )
        custody_config = FastCustodyPolicyConfig(
            enable_atr_trailing=cfg.enable_atr_trailing,
            enable_structural_trailing=cfg.enable_structural_trailing,
            enable_scale_out=cfg.enable_scale_out,
        )
        trader_config = FastTraderConfig(
            signal_cooldown=cfg.signal_cooldown,
            enable_pending_orders=cfg.enable_pending_orders,
            require_h1_alignment=cfg.require_h1_alignment,
            adoption_grace_seconds=cfg.adoption_grace_seconds,
        )
        self._risk_config = risk_config
        self._setup_config = setup_config
        self._pending_config = pending_config
        self._custody_config = custody_config
        self._trader_config = trader_config

        print(
            f"[fast-desk] starting - broker={broker_server} account={account_login} tf=M1,M5,M30"
        )

        worker_tasks: dict[str, asyncio.Task[None]] = {}
        reconcile_sleep = max(0.5, min(cfg.scan_interval, cfg.guard_interval, 2.0))
        # Track previous rejected reasons to only log/emit on state changes
        _prev_rejected: dict[str, str] = {}

        try:
            while True:
                desired_symbols, rejected = self._desired_symbols(
                    subscribed_symbols_ref,
                    allowed_sessions=cfg.allowed_sessions,
                )
                desired_set = set(desired_symbols)

                # --- Emit market state changes for rejected symbols ---
                for sym, reason in rejected.items():
                    prev = _prev_rejected.get(sym)
                    if prev != reason:
                        logger.info("[%s] worker NOT started: %s", sym, reason)
                        self._emit_market_gate(sym, reason)
                # Symbols that were rejected but are now desired → log recovery
                for sym in list(_prev_rejected):
                    if sym in desired_set and sym in _prev_rejected:
                        logger.info("[%s] market gate cleared → starting worker", sym)
                        self._emit_market_gate(sym, "market_open")
                _prev_rejected = dict(rejected)

                removed: list[asyncio.Task[None]] = []
                for symbol, task in list(worker_tasks.items()):
                    if symbol in desired_set:
                        continue
                    task.cancel()
                    removed.append(task)
                    worker_tasks.pop(symbol, None)
                    print(f"[fast-desk] worker stopped: {symbol}")
                if removed:
                    await asyncio.gather(*removed, return_exceptions=True)

                for symbol in desired_symbols:
                    if symbol in worker_tasks:
                        continue
                    worker = FastSymbolWorker()
                    worker_tasks[symbol] = asyncio.create_task(
                        worker.run(
                            symbol=symbol,
                            market_state=market_state,
                            account_payload_ref=account_payload_ref,
                            connector=connector,
                            spec_registry=spec_registry,
                            db_path=self._db_path,
                            broker_server=broker_server,
                            account_login=account_login,
                            config=worker_config,
                            risk_config=risk_config,
                            scanner_config=scanner_config,
                            risk_gate_ref=risk_gate_ref,
                            ownership_register_ref=ownership_register_ref,
                            risk_action_ref=risk_action_ref,
                            ownership_open_ref=ownership_open_ref,
                            context_config=context_config,
                            setup_config=setup_config,
                            trigger_config=trigger_config,
                            pending_config=pending_config,
                            custody_config=custody_config,
                            trader_config=trader_config,
                            mt5_call_ref=mt5_call_ref,
                        ),
                        name=f"fast_desk_worker_{symbol}",
                    )
                await asyncio.sleep(reconcile_sleep)
        except asyncio.CancelledError:
            raise
        finally:
            for task in worker_tasks.values():
                task.cancel()
            if worker_tasks:
                await asyncio.gather(*worker_tasks.values(), return_exceptions=True)

    @staticmethod
    def _desired_symbols(
        subscribed_symbols_ref: Callable[[], list[str]] | None,
        allowed_sessions: tuple[str, ...] = ("london", "overlap", "new_york"),
    ) -> tuple[list[str], dict[str, str]]:
        """Return (operable_symbols, rejected_reasons).

        *rejected_reasons* maps symbol → reason string for every subscribed
        symbol that was excluded.  Reasons:
        - ``"market_closed"`` – broker trade session is closed (from EA schedule)
        - ``"session_not_enabled"`` – current trading session (tokyo/london/…) is
          not in the configured ``allowed_sessions``
        - ``"no_session_data"`` – broker sessions EA has not reported schedule yet
        """
        raw_symbols = subscribed_symbols_ref() if subscribed_symbols_ref is not None else []

        # Snapshot from the broker-sessions registry (thread-safe copy)
        reg = session_registry.get_session_registry()
        session_groups = reg.get("session_groups", {})
        symbol_to_group = reg.get("symbol_to_session_group", {})
        gmt_offset = session_registry.get_broker_gmt_offset()

        # Current trading session name
        now = datetime.now(timezone.utc)
        current_session = session_name_from_timestamp(now)
        session_enabled = (
            "global" in allowed_sessions
            or "all_markets" in allowed_sessions
            or current_session in allowed_sessions
        )

        ordered: list[str] = []
        rejected: dict[str, str] = {}
        seen: set[str] = set()

        for raw in raw_symbols:
            symbol = normalize_symbol(raw)
            if not symbol or symbol in seen or not is_operable_symbol(symbol):
                continue
            seen.add(symbol)

            # 1) Check broker trade-session schedule (from EA)
            if symbol.upper() in symbol_to_group:
                trade_open = is_trade_open_from_registry(
                    session_groups, symbol_to_group, symbol,
                    broker_gmt_offset=gmt_offset, now_utc=now,
                )
                if not trade_open:
                    rejected[symbol] = "market_closed"
                    continue
            else:
                # EA hasn't reported schedule yet — allow (fail-open) but log
                if session_groups:
                    # Registry has data for other symbols, just not this one
                    rejected[symbol] = "no_session_data"
                    continue
                # Registry completely empty (EA not connected yet) → fail-open
                pass

            # 2) Check configured session filter (London/NY/etc)
            if not session_enabled:
                rejected[symbol] = "session_not_enabled"
                continue

            ordered.append(symbol)
        return ordered, rejected


def create_fast_desk_service(db_path: Path) -> FastDeskService:
    config = FastDeskConfig.from_env()
    return FastDeskService(db_path=db_path, config=config)
