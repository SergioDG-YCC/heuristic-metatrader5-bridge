from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from heuristic_mt5_bridge.core.config.env import getenv, load_env_file
from heuristic_mt5_bridge.core.config.paths import resolve_storage_root
from heuristic_mt5_bridge.core.ownership import OwnershipRegistry
from heuristic_mt5_bridge.core.risk import RiskKernel
from heuristic_mt5_bridge.core.runtime.chart_registry import ChartRegistry
from heuristic_mt5_bridge.core.runtime.ingress import ConnectorIngress
from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.core.runtime.subscriptions import SubscriptionManager
from heuristic_mt5_bridge.infra.indicators.bridge import IndicatorBridge
from heuristic_mt5_bridge.infra.mt5.connector import MT5Connector
from heuristic_mt5_bridge.infra.sessions import registry as session_registry
from heuristic_mt5_bridge.infra.sessions.service import BrokerSessionsService
from heuristic_mt5_bridge.infra.storage.runtime_db import (
    batch_upsert_market_state_cache,
    batch_upsert_symbol_catalog_cache,
    ensure_runtime_db,
    get_symbol_catalog_count,
    load_symbol_catalog_cache,
    load_symbol_desk_assignment_states,
    load_symbol_subscription_states,
    purge_stale_broker_data,
    runtime_db_path,
    save_symbol_subscription_snapshot,
    upsert_account_state_cache,
    upsert_exposure_cache,
    upsert_symbol_desk_assignment_state,
    upsert_symbol_spec_cache,
    replace_order_cache,
    replace_position_cache,
)
from heuristic_mt5_bridge.core.correlation import CorrelationService
from heuristic_mt5_bridge.shared.symbols.universe import is_operable_symbol, normalize_symbol
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso


def _parse_bool(value: str, default: bool) -> bool:
    raw = str(value).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _csv_values(raw: str, *, upper: bool = False) -> list[str]:
    values: list[str] = []
    for item in str(raw).split(","):
        value = item.strip()
        if not value:
            continue
        values.append(value.upper() if upper else value)
    return values


def _ensure_timeframes(timeframes: list[str], required: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in list(timeframes) + list(required):
        value = str(item).strip().upper()
        if not value or value in seen:
            continue
        ordered.append(value)
        seen.add(value)
    return ordered


@dataclass
class CoreRuntimeConfig:
    repo_root: Path
    storage_root: Path
    runtime_db_path: Path
    terminal_path: str
    watch_symbols: list[str]
    watch_timeframes: list[str]
    poll_seconds: float
    bars_per_pull: int
    account_mode_guard: str
    magic_number: int
    symbol_specs_refresh_seconds: float
    symbol_catalog_refresh_seconds: float
    account_refresh_seconds: float
    indicator_refresh_seconds: float
    market_state_checkpoint_seconds: float
    risk_adopt_foreign_positions: bool
    ownership_history_retention_days: int
    sessions_enabled: bool
    sessions_host: str
    sessions_port: int
    sessions_recv_timeout_ms: int
    indicator_enabled: bool
    indicator_stale_after_seconds: int
    indicator_common_files_root: str
    correlation_enabled: bool
    correlation_refresh_seconds: float
    correlation_window_bars: int
    correlation_min_coverage_bars: int
    correlation_return_type: str
    correlation_stale_source_seconds: float
    correlation_timeframes: list[str]

    @classmethod
    def load(cls, repo_root: Path) -> "CoreRuntimeConfig":
        env_values = load_env_file(repo_root / ".env")
        storage_root = resolve_storage_root(repo_root)
        return cls(
            repo_root=repo_root,
            storage_root=storage_root,
            runtime_db_path=runtime_db_path(
                storage_root,
                getenv("RUNTIME_DB_PATH", env_values, ""),
            ),
            terminal_path=getenv("MT5_TERMINAL_PATH", env_values, "").strip(),
            watch_symbols=_csv_values(getenv("MT5_WATCH_SYMBOLS", env_values, "EURUSD"), upper=True),
            watch_timeframes=_csv_values(getenv("MT5_WATCH_TIMEFRAMES", env_values, "M1,M5,M30,H1"), upper=True),
            poll_seconds=float(getenv("MT5_POLL_SECONDS", env_values, "5")),
            bars_per_pull=int(getenv("MT5_BARS_PER_PULL", env_values, "200")),
            account_mode_guard=getenv("ACCOUNT_MODE", env_values, "demo").strip().lower(),
            magic_number=int(getenv("MT5_MAGIC_NUMBER", env_values, "20260315")),
            symbol_specs_refresh_seconds=float(getenv("CORE_SYMBOL_SPECS_REFRESH_SECONDS", env_values, "60")),
            symbol_catalog_refresh_seconds=float(getenv("CORE_SYMBOL_CATALOG_REFRESH_SECONDS", env_values, "300")),
            account_refresh_seconds=float(getenv("CORE_ACCOUNT_REFRESH_SECONDS", env_values, "2")),
            indicator_refresh_seconds=float(getenv("CORE_INDICATOR_REFRESH_SECONDS", env_values, "2")),
            market_state_checkpoint_seconds=float(getenv("CORE_MARKET_STATE_CHECKPOINT_SECONDS", env_values, "30")),
            risk_adopt_foreign_positions=_parse_bool(
                # Canonical env var; OWNERSHIP_AUTO_ADOPT_FOREIGN is a legacy alias.
                getenv("RISK_ADOPT_FOREIGN_POSITIONS", env_values, "")
                or getenv("OWNERSHIP_AUTO_ADOPT_FOREIGN", env_values, "true"),
                True,
            ),
            ownership_history_retention_days=int(getenv("OWNERSHIP_HISTORY_RETENTION_DAYS", env_values, "30")),
            sessions_enabled=_parse_bool(getenv("BROKER_SESSIONS_ENABLED", env_values, "false"), False),
            sessions_host=getenv("BROKER_SESSIONS_HOST", env_values, "127.0.0.1").strip() or "127.0.0.1",
            sessions_port=int(getenv("BROKER_SESSIONS_PORT", env_values, "5561")),
            sessions_recv_timeout_ms=int(getenv("BROKER_SESSIONS_RECV_TIMEOUT_MS", env_values, "15000")),
            indicator_enabled=_parse_bool(getenv("INDICATOR_ENRICHMENT_ENABLED", env_values, "false"), False),
            indicator_stale_after_seconds=int(getenv("INDICATOR_ENRICHMENT_STALE_AFTER_SECONDS", env_values, "180")),
            indicator_common_files_root=getenv("MT5_COMMON_FILES_ROOT", env_values, "").strip(),
            correlation_enabled=_parse_bool(getenv("CORRELATION_ENABLED", env_values, "false"), False),
            correlation_refresh_seconds=float(getenv("CORRELATION_REFRESH_SECONDS", env_values, "60")),
            correlation_window_bars=int(getenv("CORRELATION_WINDOW_BARS", env_values, "50")),
            correlation_min_coverage_bars=int(getenv("CORRELATION_MIN_COVERAGE_BARS", env_values, "30")),
            correlation_return_type=getenv("CORRELATION_RETURN_TYPE", env_values, "simple").strip().lower(),
            correlation_stale_source_seconds=float(getenv("CORRELATION_STALE_SOURCE_SECONDS", env_values, "300")),
            correlation_timeframes=_csv_values(getenv("CORRELATION_TIMEFRAMES", env_values, "M5,H1"), upper=True),
        )


class CoreRuntimeService:
    def __init__(
        self,
        *,
        config: CoreRuntimeConfig,
        connector: MT5Connector | None = None,
        market_state: MarketStateService | None = None,
        sessions_service: BrokerSessionsService | None = None,
        indicator_bridge: IndicatorBridge | None = None,
    ) -> None:
        self.config = config
        self.connector = connector or MT5Connector(
            terminal_path=config.terminal_path,
            watch_symbols=config.watch_symbols,
            magic_number=config.magic_number,
            account_mode_guard=config.account_mode_guard,
        )
        self.spec_registry = SymbolSpecRegistry()
        self.market_state = market_state or MarketStateService(
            max_bars=max(config.bars_per_pull + 50, 300),
            spec_registry=self.spec_registry,
        )
        self.sessions_service = sessions_service or BrokerSessionsService(
            host=config.sessions_host,
            port=config.sessions_port,
            recv_timeout_ms=config.sessions_recv_timeout_ms,
        )
        self.indicator_bridge = indicator_bridge or IndicatorBridge(
            storage_root=config.storage_root,
            enabled=config.indicator_enabled,
            common_files_root=config.indicator_common_files_root,
            stale_after_seconds=config.indicator_stale_after_seconds,
        )

        self.subscription_manager = SubscriptionManager(bootstrap_symbols=config.watch_symbols)
        self.chart_registry = ChartRegistry(
            market_state=self.market_state,
            watch_timeframes=config.watch_timeframes,
        )
        self.ingress = ConnectorIngress(
            connector=self.connector,
            mt5_call=self._mt5_call,
            subscription_manager=self.subscription_manager,
            chart_registry=self.chart_registry,
            watch_timeframes=config.watch_timeframes,
            bars_per_pull=config.bars_per_pull,
            poll_seconds=config.poll_seconds,
        )

        self._mt5_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._bootstrapped = False
        self._next_market_state_checkpoint_at = 0.0

        self.broker_identity: dict[str, Any] = {}
        self.catalog_universe: list[str] = []
        self.bootstrap_universe: list[str] = []
        self.subscribed_universe: list[str] = []
        self.active_chart_workers: list[str] = []
        self.bootstrap_rejected_symbols: list[str] = []

        self._smc_desk: Any = None   # Optional[SmcDeskService] — set via attach_smc_desk()
        self._fast_desk: Any = None   # Optional[FastDeskService] — set via attach_fast_desk()

        self.correlation_service: CorrelationService | None = None
        if config.correlation_enabled:
            self.correlation_service = CorrelationService(
                market_state=self.market_state,
                subscription_manager=self.subscription_manager,
                window_bars=config.correlation_window_bars,
                min_coverage_bars=config.correlation_min_coverage_bars,
                return_type=config.correlation_return_type,
                refresh_seconds=config.correlation_refresh_seconds,
                stale_source_seconds=config.correlation_stale_source_seconds,
                timeframes=config.correlation_timeframes,
            )

        # Per-symbol desk assignments: symbol -> set of desks ("fast", "smc")
        # Default: subscribed symbols get both desks enabled when both desks are attached.
        self.symbol_desk_assignments: dict[str, set[str]] = {}

        self.feed_status_rows: list[dict[str, Any]] = []
        self.summaries: list[dict[str, Any]] = []
        self.symbol_specifications: list[dict[str, Any]] = []
        self.symbol_catalog: list[dict[str, Any]] = []
        self.symbol_catalog_status: dict[str, Any] = {"status": "pending", "symbol_count": 0, "updated_at": ""}
        self.account_payload: dict[str, Any] = {}
        self.indicator_status: dict[str, Any] = {"enabled": config.indicator_enabled, "status": "inactive"}
        self.runtime_metrics: dict[str, Any] = {}
        self.ownership_registry: OwnershipRegistry | None = None
        self.risk_kernel: RiskKernel | None = None
        self.ownership_status: dict[str, Any] = {"status": "inactive", "summary": {}}
        self.risk_status: dict[str, Any] = {"status": "inactive"}
        self.health: dict[str, Any] = {
            "status": "starting",
            "mt5_connector": "starting",
            "market_state": "starting",
            "broker_sessions": "starting" if config.sessions_enabled else "disabled",
            "indicator_bridge": "inactive" if not config.indicator_enabled else "waiting_first_snapshot",
            "correlation": "enabled" if config.correlation_enabled else "disabled",
            "updated_at": utc_now_iso(),
        }

    async def _mt5_call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._mt5_lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

    def _sync_universe_views(self) -> None:
        snapshot = self.subscription_manager.snapshot()
        self.catalog_universe = snapshot["catalog_universe"]
        self.bootstrap_universe = snapshot["bootstrap_universe"]
        self.subscribed_universe = snapshot["subscribed_universe"]
        self.active_chart_workers = self.chart_registry.active_symbols()

    def _broker_partition(self) -> tuple[str, int]:
        return (
            str(self.broker_identity.get("broker_server", "")).strip(),
            int(self.broker_identity.get("account_login", 0) or 0),
        )

    def _refresh_cached_worker_views(self) -> None:
        self.feed_status_rows = self.chart_registry.feed_status_rows()
        self.summaries = self.chart_registry.state_summaries()
        self.active_chart_workers = self.chart_registry.active_symbols()

    async def _persist_subscription_snapshot(self, *, source: str) -> None:
        broker_server, account_login = self._broker_partition()
        if not broker_server or account_login <= 0:
            return
        await asyncio.to_thread(
            save_symbol_subscription_snapshot,
            self.config.runtime_db_path,
            broker_server=broker_server,
            account_login=account_login,
            subscribed_symbols=list(self.subscribed_universe),
            source=source,
        )

    async def _persist_desk_assignment(self, *, symbol: str, desks: set[str]) -> None:
        broker_server, account_login = self._broker_partition()
        if not broker_server or account_login <= 0:
            return
        await asyncio.to_thread(
            upsert_symbol_desk_assignment_state,
            self.config.runtime_db_path,
            broker_server=broker_server,
            account_login=account_login,
            symbol=symbol,
            desks=sorted(desks),
        )

    async def _restore_symbol_preferences(self) -> None:
        broker_server, account_login = self._broker_partition()
        if not broker_server or account_login <= 0:
            self._initialize_bootstrap_universe(self.config.watch_symbols)
            return

        subscription_rows = await asyncio.to_thread(
            load_symbol_subscription_states,
            self.config.runtime_db_path,
            broker_server=broker_server,
            account_login=account_login,
        )
        assignment_rows = await asyncio.to_thread(
            load_symbol_desk_assignment_states,
            self.config.runtime_db_path,
            broker_server=broker_server,
            account_login=account_login,
        )

        bootstrap_symbols = (
            [row["symbol"] for row in subscription_rows if row.get("is_subscribed")]
            if subscription_rows
            else list(self.config.watch_symbols)
        )
        self._initialize_bootstrap_universe(bootstrap_symbols)

        valid_desks = {"fast", "smc"}
        self.symbol_desk_assignments = {}
        for row in assignment_rows:
            symbol = normalize_symbol(str(row.get("symbol", "")))
            desks = {
                str(desk).strip().lower()
                for desk in row.get("desks", [])
                if str(desk).strip().lower() in valid_desks
            }
            if symbol and desks:
                self.symbol_desk_assignments[symbol] = desks

        if not subscription_rows:
            await self._persist_subscription_snapshot(source="bootstrap_env")

    def _extract_account_activity_symbols(
        self,
        *,
        positions: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        for row in list(positions) + list(orders):
            if not isinstance(row, dict):
                continue
            symbol = normalize_symbol(str(row.get("symbol", "")))
            if not symbol or symbol in seen or not is_operable_symbol(symbol):
                continue
            symbols.append(symbol)
            seen.add(symbol)
        return symbols

    async def _ensure_account_activity_symbols_subscribed(
        self,
        *,
        positions: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> list[str]:
        activity_symbols = self._extract_account_activity_symbols(positions=positions, orders=orders)
        if not activity_symbols:
            return []

        changed: list[str] = []
        current = set(self.subscription_manager.subscribed_universe())
        for symbol in activity_symbols:
            if symbol in current:
                continue
            subscribed = self.subscription_manager.subscribe(symbol)
            if not subscribed:
                subscribed = self.subscription_manager.force_subscribe(symbol)
            if not subscribed:
                continue
            changed.append(symbol)
            current.add(symbol)

        if not changed:
            return []

        self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
        self._sync_universe_views()
        self._refresh_cached_worker_views()
        await self._persist_subscription_snapshot(source="account_activity")
        await self._sync_sessions_active_symbols(reason="account_activity")
        await self._refresh_symbol_specs()
        self.health["updated_at"] = utc_now_iso()
        return changed

    async def _persist_market_state_checkpoint(self, *, force: bool = False) -> None:
        now_monotonic = time.monotonic()
        if not force and now_monotonic < self._next_market_state_checkpoint_at:
            return
        checkpoint_rows = self.chart_registry.checkpoint_rows()
        updated_at = utc_now_iso()
        broker_server = str(self.broker_identity.get("broker_server", "")).strip()
        account_login = int(self.broker_identity.get("account_login", 0) or 0)
        batch_rows: list[dict[str, Any]] = []
        for row in checkpoint_rows:
            state_summary = row["state_summary"] if isinstance(row.get("state_summary"), dict) else {}
            indicator_summary = state_summary.get("indicator_summary")
            batch_rows.append({
                "broker_server": broker_server,
                "account_login": account_login,
                "symbol": str(row.get("symbol", "")).upper(),
                "timeframe": str(row.get("timeframe", "")).upper(),
                "updated_at": updated_at,
                "state_summary": state_summary,
                "chart_context": None,
                "indicator_summary": indicator_summary if isinstance(indicator_summary, dict) else None,
                "source": "core_runtime_checkpoint",
            })
        if batch_rows:
            await asyncio.to_thread(batch_upsert_market_state_cache, self.config.runtime_db_path, batch_rows)
        self._next_market_state_checkpoint_at = now_monotonic + max(self.config.market_state_checkpoint_seconds, 1.0)

    async def _refresh_symbol_catalog_with_validation(self) -> None:
        """Validate symbol catalog count before full refresh.
        
        If MT5 symbol count matches cached count, load from DB instead of
        full refetch. This avoids expensive MT5 API call on every startup
        when catalog hasn't changed.
        
        Falls back to full _refresh_symbol_catalog() if count differs.
        """
        broker_server = str(self.broker_identity.get("broker_server", "")).strip()
        account_login = int(self.broker_identity.get("account_login", 0) or 0)
        
        # Fast validation: count only (< 1 sec)
        mt5_count = await self._mt5_call(self.connector.fetch_available_symbol_count)
        cached_count = await asyncio.to_thread(
            get_symbol_catalog_count,
            self.config.runtime_db_path,
            broker_server,
            account_login,
        )
        
        # If count matches, use cached catalog
        if mt5_count > 0 and mt5_count == cached_count and cached_count > 0:
            cached_catalog = await asyncio.to_thread(
                load_symbol_catalog_cache,
                self.config.runtime_db_path,
                broker_server,
                account_login,
            )
            if cached_catalog:
                self.symbol_catalog = cached_catalog
                self.symbol_catalog_status = {
                    "status": "cached",
                    "symbol_count": len(cached_catalog),
                    "updated_at": utc_now_iso(),
                    "validation": f"count_match({mt5_count}={cached_count})",
                }
                self.health["symbol_catalog"] = "up"
                # Still need to update catalog universe and subscriptions
                catalog_universe: list[str] = []
                seen: set[str] = set()
                for item in self.symbol_catalog:
                    symbol = normalize_symbol(str(item.get("symbol", "")))
                    if not symbol or symbol in seen or not is_operable_symbol(symbol):
                        continue
                    catalog_universe.append(symbol)
                    seen.add(symbol)
                self.subscription_manager.set_catalog_universe(catalog_universe)
                self.subscription_manager.reconcile_subscriptions_with_catalog()
                self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
                self._sync_universe_views()
                return
        
        # Count mismatch or cache miss: full refresh
        await self._refresh_symbol_catalog()

    async def _refresh_symbol_catalog(self) -> None:
        catalog = await self._mt5_call(self.connector.fetch_available_symbol_catalog)
        self.symbol_catalog = [item for item in catalog if isinstance(item, dict)]
        await asyncio.to_thread(batch_upsert_symbol_catalog_cache, self.config.runtime_db_path, self.symbol_catalog)

        catalog_universe: list[str] = []
        seen: set[str] = set()
        for item in self.symbol_catalog:
            symbol = normalize_symbol(str(item.get("symbol", "")))
            if not symbol or symbol in seen or not is_operable_symbol(symbol):
                continue
            catalog_universe.append(symbol)
            seen.add(symbol)

        self.subscription_manager.set_catalog_universe(catalog_universe)
        removed_symbols = self.subscription_manager.reconcile_subscriptions_with_catalog()
        self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
        self._sync_universe_views()

        self.symbol_catalog_status = {
            "status": "ready",
            "symbol_count": len(self.symbol_catalog),
            "updated_at": utc_now_iso(),
        }
        self.health["symbol_catalog"] = "up"
        if removed_symbols and self._bootstrapped:
            await self._sync_sessions_active_symbols(reason="catalog_reconcile")

    def _initialize_bootstrap_universe(self, symbols: list[str]) -> None:
        bootstrap_result = self.subscription_manager.bootstrap_from_env(symbols)
        self.bootstrap_rejected_symbols = bootstrap_result.rejected_symbols
        self.chart_registry.sync_workers(bootstrap_result.subscribed_universe)
        self._sync_universe_views()

    async def _refresh_symbol_specs(self) -> None:
        specs: list[dict[str, Any]] = []
        for symbol in self.subscribed_universe:
            try:
                specification = await self._mt5_call(self.connector.fetch_symbol_specification, symbol)
            except Exception:
                continue
            specs.append(specification)
            await asyncio.to_thread(upsert_symbol_spec_cache, self.config.runtime_db_path, specification)
        self.symbol_specifications = specs
        self.spec_registry.update(specs)

    async def _refresh_market_state(self, *, force_checkpoint: bool = False) -> None:
        cycle = await self.ingress.poll_subscribed_once()
        self.feed_status_rows = cycle.feed_rows
        self.summaries = cycle.state_summaries

        if cycle.errors:
            self.health["market_state"] = "degraded"
            self.health["market_state_error"] = cycle.errors[-1]
        else:
            self.health["market_state"] = "up"
            self.health.pop("market_state_error", None)

        self.runtime_metrics = {
            "poll_duration_ms_avg": round(sum(cycle.poll_durations_ms) / len(cycle.poll_durations_ms), 1)
            if cycle.poll_durations_ms
            else 0.0,
            "poll_duration_ms_max": max(cycle.poll_durations_ms) if cycle.poll_durations_ms else 0.0,
            "local_clock_drift_ms_avg": round(sum(cycle.clock_drifts_ms) / len(cycle.clock_drifts_ms), 1)
            if cycle.clock_drifts_ms
            else 0.0,
            "local_clock_warning": any(abs(item) > 1500 for item in cycle.clock_drifts_ms),
            "ingress_errors": cycle.errors[-20:],
            "updated_at": utc_now_iso(),
        }
        await self._persist_market_state_checkpoint(force=force_checkpoint)

    async def _refresh_account_state(self) -> None:
        payload = await self._mt5_call(self.connector.fetch_account_runtime, self.subscribed_universe)
        account_state = payload.get("account_state", {}) if isinstance(payload, dict) else {}
        exposure_state = payload.get("exposure_state", {}) if isinstance(payload, dict) else {}
        positions = payload.get("positions", []) if isinstance(payload, dict) else []
        orders = payload.get("orders", []) if isinstance(payload, dict) else []
        if isinstance(account_state, dict):
            await asyncio.to_thread(upsert_account_state_cache, self.config.runtime_db_path, account_state)
        if isinstance(exposure_state, dict):
            await asyncio.to_thread(upsert_exposure_cache, self.config.runtime_db_path, exposure_state)
        if isinstance(positions, list):
            await asyncio.to_thread(replace_position_cache, self.config.runtime_db_path, positions)
        if isinstance(orders, list):
            await asyncio.to_thread(replace_order_cache, self.config.runtime_db_path, orders)
        self.account_payload = payload if isinstance(payload, dict) else {}
        await self._ensure_account_activity_symbols_subscribed(
            positions=positions if isinstance(positions, list) else [],
            orders=orders if isinstance(orders, list) else [],
        )
        await self._reconcile_ownership_and_risk()

    async def _reconcile_ownership_and_risk(self) -> None:
        if not isinstance(self.account_payload, dict):
            return
        positions = self.account_payload.get("positions", [])
        orders = self.account_payload.get("orders", [])
        recent_deals = self.account_payload.get("recent_deals", [])
        recent_orders = self.account_payload.get("recent_orders", [])

        if self.ownership_registry is not None:
            result = await asyncio.to_thread(
                self.ownership_registry.reconcile_from_caches,
                positions=positions if isinstance(positions, list) else [],
                orders=orders if isinstance(orders, list) else [],
                recent_deals=recent_deals if isinstance(recent_deals, list) else [],
                recent_orders=recent_orders if isinstance(recent_orders, list) else [],
            )
            self.ownership_status = {
                "status": "up",
                "summary": self.ownership_registry.summary(),
                "last_reconcile": result,
            }
            self.health["ownership_registry"] = "up"

        if self.risk_kernel is not None:
            ownership_open = self.ownership_registry.list_open() if self.ownership_registry is not None else []
            usage = await asyncio.to_thread(
                self.risk_kernel.update_usage,
                account_payload=self.account_payload,
                ownership_open=ownership_open,
            )
            self.risk_status = {
                "status": "up",
                "usage": usage,
                "snapshot": self.risk_kernel.status(),
            }
            self.health["risk_kernel"] = "up"

    async def _refresh_indicator_state(self) -> None:
        try:
            self.indicator_status = await asyncio.to_thread(
                self.indicator_bridge.poll,
                self.market_state,
                set(self.subscribed_universe),
                set(self.config.watch_timeframes),
                ["ema_20", "ema_50", "rsi_14", "atr_14", "macd_main"],  # requested_indicators
            )
        except TypeError:
            self.indicator_status = await asyncio.to_thread(self.indicator_bridge.poll, self.market_state)
        self.health["indicator_bridge"] = str(self.indicator_status.get("status", "inactive"))

    async def _sync_sessions_active_symbols(self, *, reason: str) -> None:
        if not self.config.sessions_enabled or not self._bootstrapped:
            return
        await asyncio.to_thread(
            self.sessions_service.replace_active_symbols,
            self.subscribed_universe,
            reason=reason,
        )

    async def subscribe_symbol(self, symbol: str, *, reason: str = "control_plane") -> bool:
        changed = self.subscription_manager.subscribe(symbol)
        if not changed:
            return False
        self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
        self._sync_universe_views()
        self._refresh_cached_worker_views()
        await self._persist_subscription_snapshot(source=f"subscribe:{reason}")
        await self._sync_sessions_active_symbols(reason=f"subscribe:{reason}")
        await self._refresh_symbol_specs()
        self.health["updated_at"] = utc_now_iso()
        return True

    async def unsubscribe_symbol(self, symbol: str, *, reason: str = "control_plane") -> bool:
        changed = self.subscription_manager.unsubscribe(symbol)
        if not changed:
            return False
        self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
        self._sync_universe_views()
        self._refresh_cached_worker_views()
        await self._persist_subscription_snapshot(source=f"unsubscribe:{reason}")
        await self._sync_sessions_active_symbols(reason=f"unsubscribe:{reason}")
        await self._refresh_symbol_specs()
        self.health["updated_at"] = utc_now_iso()
        return True

    async def replace_subscribed_universe(self, symbols: list[str], *, reason: str = "control_plane") -> list[str]:
        self.subscription_manager.replace_subscribed_universe(symbols)
        self.chart_registry.sync_workers(self.subscription_manager.subscribed_universe())
        self._sync_universe_views()
        self._refresh_cached_worker_views()
        await self._persist_subscription_snapshot(source=f"replace:{reason}")
        await self._sync_sessions_active_symbols(reason=f"replace:{reason}")
        await self._refresh_symbol_specs()
        self.health["updated_at"] = utc_now_iso()
        return list(self.subscribed_universe)

    def subscription_snapshot(self) -> dict[str, list[str]]:
        return self.subscription_manager.snapshot()

    async def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        await asyncio.to_thread(ensure_runtime_db, self.config.runtime_db_path)
        await self._mt5_call(self.connector.connect)
        self.health["mt5_connector"] = "up"
        self.broker_identity = await self._mt5_call(self.connector.broker_identity)
        session_registry.set_server_time_offset(self.connector.server_time_offset_seconds)
        self.ownership_registry = OwnershipRegistry(
            db_path=self.config.runtime_db_path,
            broker_server=str(self.broker_identity.get("broker_server", "")).strip(),
            account_login=int(self.broker_identity.get("account_login", 0) or 0),
            auto_adopt_foreign=self.config.risk_adopt_foreign_positions,
            history_retention_days=max(0, self.config.ownership_history_retention_days),
        )
        self.risk_kernel = await asyncio.to_thread(
            RiskKernel.from_env,
            db_path=self.config.runtime_db_path,
            broker_server=str(self.broker_identity.get("broker_server", "")).strip(),
            account_login=int(self.broker_identity.get("account_login", 0) or 0),
        )
        self.health["ownership_registry"] = "up"
        self.health["risk_kernel"] = "up"

        await asyncio.to_thread(
            purge_stale_broker_data,
            self.config.runtime_db_path,
            str(self.broker_identity.get("broker_server", "")),
            int(self.broker_identity.get("account_login", 0) or 0),
        )

        await self._refresh_symbol_catalog_with_validation()
        await self._restore_symbol_preferences()
        await self._refresh_symbol_specs()
        # Load market state to RAM only (do NOT checkpoint to DB in bootstrap)
        # Charts are loaded for analysis, checkpoint happens later in loop if configured
        await self._refresh_market_state(force_checkpoint=False)
        await self._refresh_account_state()
        await self._refresh_indicator_state()

        if self.config.sessions_enabled:
            started = await asyncio.to_thread(self.sessions_service.start)
            if started:
                self.health["broker_sessions"] = "up"
                await asyncio.to_thread(self.sessions_service.bootstrap_active_symbols, self.subscribed_universe)
            else:
                self.health["broker_sessions"] = "degraded"
        else:
            self.health["broker_sessions"] = "disabled"

        self.health["status"] = "up"
        self.health["updated_at"] = utc_now_iso()
        self._bootstrapped = True

    def attach_smc_desk(self, desk: Any) -> None:
        """Attach an SmcDeskService to be launched alongside core tasks in run_forever()."""
        self._smc_desk = desk

    def attach_fast_desk(self, desk: Any) -> None:
        """Attach a FastDeskService to be launched alongside core tasks in run_forever()."""
        self._fast_desk = desk

    @property
    def fast_desk_service(self) -> Any:
        """Return the attached FastDeskService, or None if not active."""
        return self._fast_desk

    @property
    def fast_desk_config(self) -> Any:
        """Return FastDeskConfig from the attached desk, or None if not active."""
        if self._fast_desk is not None:
            return getattr(self._fast_desk, "_config", None)
        return None

    @property
    def smc_desk_config(self) -> Any:
        """Return SmcAnalystConfig from the attached desk, or None if not active."""
        if self._smc_desk is not None:
            return getattr(self._smc_desk, "_analyst_config", None)
        return None

    @property
    def smc_trader_config(self) -> Any:
        """Return SmcTraderConfig from the attached desk, or None."""
        if self._smc_desk is not None:
            return getattr(self._smc_desk, "_trader_config", None)
        return None

    # ── Per-symbol desk assignments ────────────────────────────────────────────
    def _default_desks(self) -> set[str]:
        """Return the set of desks that are attached (used as default for new subscriptions)."""
        desks: set[str] = set()
        if self._fast_desk is not None:
            desks.add("fast")
        if self._smc_desk is not None:
            desks.add("smc")
        return desks or {"fast", "smc"}

    def get_symbol_desks(self, symbol: str) -> set[str]:
        """Return the desk set for a symbol, defaulting to all attached desks."""
        return self.symbol_desk_assignments.get(symbol.upper(), self._default_desks())

    async def set_symbol_desks(self, symbol: str, desks: set[str]) -> None:
        """Set the desk assignment for a symbol."""
        normalized_symbol = symbol.upper()
        normalized_desks = {desk for desk in desks if desk in {"fast", "smc"}}
        self.symbol_desk_assignments[normalized_symbol] = normalized_desks
        await self._persist_desk_assignment(symbol=normalized_symbol, desks=normalized_desks)

    def get_all_symbol_desk_assignments(self) -> dict[str, list[str]]:
        """Return current desk assignments dict (symbol → sorted desk list)."""
        result: dict[str, list[str]] = {}
        defaults = self._default_desks()
        for sym in self.subscribed_universe:
            assigned = self.symbol_desk_assignments.get(sym, defaults)
            result[sym] = sorted(assigned)
        return result

    def subscribed_symbols_for_desk(self, desk: str) -> list[str]:
        """Return only subscribed symbols that have the given desk enabled."""
        defaults = self._default_desks()
        return [
            sym for sym in self.subscribed_universe
            if desk in self.symbol_desk_assignments.get(sym, defaults)
        ]

    def evaluate_entry_for_desk(self, *, desk: str, symbol: str) -> dict[str, Any]:
        if self.risk_kernel is None:
            return {"allowed": True, "reasons": [], "risk_per_trade_pct": 0.0, "limits": {}}
        return self.risk_kernel.evaluate_entry(desk=desk, symbol=symbol)

    def evaluate_action_for_desk(self, *, desk: str, action_type: str) -> dict[str, Any]:
        if self.risk_kernel is None:
            return {"allowed": True, "reason": "risk_kernel_inactive", "desk": desk}
        payload = self.risk_kernel.evaluate_action(action_type=action_type)
        payload["desk"] = desk
        return payload

    def ownership_open_for_desk(self, *, desk: str) -> list[dict[str, Any]]:
        if self.ownership_registry is None:
            return []
        rows = self.ownership_registry.list_open()
        desk_norm = str(desk or "").strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            owner = str(row.get("desk_owner", "")).strip().lower()
            status = str(row.get("ownership_status", "")).strip().lower()
            if owner == desk_norm:
                filtered.append(row)
                continue
            if desk_norm == "fast" and status == "inherited_fast":
                filtered.append(row)
        return filtered

    def register_fast_execution_ownership(
        self,
        *,
        result: dict[str, Any],
        symbol: str,
        side: str,
        signal_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.ownership_registry is None:
            return []
        return self.ownership_registry.register_from_execution_result(
            owner="fast",
            result=result,
            symbol=symbol,
            reason="fast_execution_result",
            metadata={"side": side, "signal_id": signal_id},
        )

    def ownership_all(self) -> dict[str, Any]:
        if self.ownership_registry is None:
            return {"items": [], "summary": {"total": 0, "open": 0, "history": 0}}
        rows = self.ownership_registry.list_all()
        return {
            "items": [self.ownership_registry.to_operation_view(item) for item in rows],
            "summary": self.ownership_registry.summary(),
        }

    def ownership_open(self) -> dict[str, Any]:
        if self.ownership_registry is None:
            return {"items": [], "summary": {"open": 0}}
        rows = self.ownership_registry.list_open()
        return {
            "items": [self.ownership_registry.to_operation_view(item) for item in rows],
            "summary": self.ownership_registry.summary(),
        }

    def ownership_history(self) -> dict[str, Any]:
        if self.ownership_registry is None:
            return {"items": [], "summary": {"history": 0}}
        rows = self.ownership_registry.list_history()
        return {
            "items": [self.ownership_registry.to_operation_view(item) for item in rows],
            "summary": self.ownership_registry.summary(),
        }

    def ownership_reassign(
        self,
        *,
        target_owner: str,
        position_id: int | None = None,
        order_id: int | None = None,
        reevaluation_required: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.ownership_registry is None:
            raise RuntimeError("Ownership registry is not initialized")
        row = self.ownership_registry.reassign(
            target_owner=target_owner,
            position_id=position_id,
            order_id=order_id,
            reevaluation_required=reevaluation_required,
            reason=reason,
        )
        return {"item": self.ownership_registry.to_operation_view(row), "summary": self.ownership_registry.summary()}

    def risk_status_payload(self) -> dict[str, Any]:
        if self.risk_kernel is None:
            return {"status": "inactive"}
        return self.risk_kernel.status()

    def risk_limits_payload(self) -> dict[str, Any]:
        if self.risk_kernel is None:
            return {"global": {}, "desks": {}}
        return self.risk_kernel.effective_limits()

    def risk_profile_payload(self) -> dict[str, Any]:
        if self.risk_kernel is None:
            return {"global": 0, "fast": 0, "smc": 0}
        return self.risk_kernel.profile_state()

    def update_risk_profile(
        self,
        *,
        profile_global: int | None = None,
        profile_fast: int | None = None,
        profile_smc: int | None = None,
        overrides: dict[str, Any] | None = None,
        reason: str = "api_profile_update",
    ) -> dict[str, Any]:
        if self.risk_kernel is None:
            raise RuntimeError("Risk kernel is not initialized")
        return self.risk_kernel.set_profiles(
            profile_global=profile_global,
            profile_fast=profile_fast,
            profile_smc=profile_smc,
            overrides=overrides,
            reason=reason,
        )

    def trip_risk_kill_switch(self, *, reason: str, manual_override: bool = False) -> dict[str, Any]:
        if self.risk_kernel is None:
            raise RuntimeError("Risk kernel is not initialized")
        return self.risk_kernel.trip_kill_switch(reason=reason, manual_override=manual_override)

    def reset_risk_kill_switch(self, *, reason: str | None = None, manual_override: bool = False) -> dict[str, Any]:
        if self.risk_kernel is None:
            raise RuntimeError("Risk kernel is not initialized")
        return self.risk_kernel.reset_kill_switch(reason=reason, manual_override=manual_override)

    # ── Desk-scoped account payload ────────────────────────────────────────────

    def ownership_visible_ids_for_desk(self, *, desk: str) -> dict[str, set[int]]:
        """Return position_ids and order_ids visible for *desk* based on ownership.

        For desk="fast": visible are rows with desk_owner=="fast" or
            ownership_status in {"fast_owned", "inherited_fast"}.
            ``inherited_fast`` means tickets external to the stack (e.g. manual
            human trades) — SMC tickets are never reclassified as inherited_fast.
        For desk="smc": visible are rows with desk_owner=="smc" or
            ownership_status=="smc_owned".

        If the ownership registry is not yet initialised, returns empty sets.
        Callers that need a safe fallback should check whether both sets are empty.
        """
        position_ids: set[int] = set()
        order_ids: set[int] = set()
        if self.ownership_registry is None:
            return {"position_ids": position_ids, "order_ids": order_ids}

        desk_norm = str(desk or "").strip().lower()
        rows = self.ownership_registry.list_open()
        for row in rows:
            if not isinstance(row, dict):
                continue
            owner = str(row.get("desk_owner", "")).strip().lower()
            status = str(row.get("ownership_status", "")).strip().lower()

            if desk_norm == "fast":
                visible = (owner == "fast") or (status in {"fast_owned", "inherited_fast"})
            elif desk_norm == "smc":
                visible = (owner == "smc") or (status == "smc_owned")
            else:
                visible = False

            if not visible:
                continue

            pos_id = int(row.get("mt5_position_id", 0) or 0)
            ord_id = int(row.get("mt5_order_id", 0) or 0)
            if pos_id > 0:
                position_ids.add(pos_id)
            if ord_id > 0:
                order_ids.add(ord_id)

        return {"position_ids": position_ids, "order_ids": order_ids}

    def account_payload_for_desk(self, *, desk: str) -> dict[str, Any]:
        """Return account_payload filtered to only include positions and orders
        visible for *desk*.

        Positions and orders are filtered by ownership_visible_ids_for_desk.
        account_state, exposure_state, recent_deals, and recent_orders remain
        global (they do not contain per-ticket information that would contaminate
        desk isolation).

        If the ownership registry is not yet initialised, the global
        account_payload is returned unchanged as a safe bootstrap fallback.
        This fallback is intentionally conservative: desks should not be running
        before bootstrap completes, so the window is effectively zero.
        """
        if not isinstance(self.account_payload, dict):
            return {}
        if self.ownership_registry is None:
            # Registry not yet initialised — return global payload unchanged.
            return self.account_payload

        visible = self.ownership_visible_ids_for_desk(desk=desk)
        visible_position_ids = visible["position_ids"]
        visible_order_ids = visible["order_ids"]

        all_positions: list[dict[str, Any]] = self.account_payload.get("positions") or []
        all_orders: list[dict[str, Any]] = self.account_payload.get("orders") or []

        desk_positions = [
            p for p in all_positions
            if isinstance(p, dict) and int(p.get("position_id", 0) or 0) in visible_position_ids
        ]
        desk_orders = [
            o for o in all_orders
            if isinstance(o, dict) and int(o.get("order_id", 0) or 0) in visible_order_ids
        ]

        return {
            **self.account_payload,
            "positions": desk_positions,
            "orders": desk_orders,
        }

    async def run_once(self) -> None:
        if not self._bootstrapped:
            await self.bootstrap()
        await self._refresh_market_state()
        await self._refresh_account_state()
        await self._refresh_indicator_state()

    async def _loop_wrapper(self, name: str, interval: float, coro: Any) -> None:
        while not self._stop_event.is_set():
            try:
                await coro()
            except Exception as exc:
                self.health["status"] = "degraded"
                self.health[name] = "degraded"
                self.health[f"{name}_error"] = str(exc)
                self.health["updated_at"] = utc_now_iso()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(interval, 0.2))
            except TimeoutError:
                continue

    async def run_forever(self) -> None:
        if not self._bootstrapped:
            await self.bootstrap()
        self._stop_event.clear()
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._loop_wrapper("market_state", self.config.poll_seconds, self._refresh_market_state))
                tg.create_task(
                    self._loop_wrapper("account_state", self.config.account_refresh_seconds, self._refresh_account_state)
                )
                tg.create_task(
                    self._loop_wrapper("symbol_specs", self.config.symbol_specs_refresh_seconds, self._refresh_symbol_specs)
                )
                tg.create_task(
                    self._loop_wrapper(
                        "symbol_catalog",
                        self.config.symbol_catalog_refresh_seconds,
                        self._refresh_symbol_catalog,
                    )
                )
                tg.create_task(
                    self._loop_wrapper(
                        "indicator_bridge",
                        self.config.indicator_refresh_seconds,
                        self._refresh_indicator_state,
                    )
                )
                if self._smc_desk is not None:
                    tg.create_task(
                        self._smc_desk.run_forever(
                            self.market_state,
                            str(self.broker_identity.get("broker_server", "")),
                            int(self.broker_identity.get("account_login", 0) or 0),
                            self.spec_registry,
                            symbols_ref=lambda: self.subscribed_symbols_for_desk("smc"),
                            risk_gate_ref=lambda symbol: self.evaluate_entry_for_desk(desk="smc", symbol=symbol),
                            ownership_register_ref=lambda result, symbol, side, signal_id=None: (
                                self.ownership_registry.register_from_execution_result(
                                    owner="smc",
                                    result=result,
                                    symbol=symbol,
                                    reason="smc_execution_result",
                                    metadata={"side": side, "signal_id": signal_id},
                                ) if self.ownership_registry is not None else []
                            ),
                            connector=self.connector,
                            # SMC receives only smc_owned positions and orders.
                            account_payload_ref=lambda: self.account_payload_for_desk(desk="smc"),
                            ownership_open_ref=lambda: self.ownership_open_for_desk(desk="smc"),
                            mt5_call_ref=self._mt5_call,
                        ),
                        name="smc_desk",
                    )
                if self._fast_desk is not None:
                    tg.create_task(
                        self._fast_desk.run_forever(
                            self.market_state,
                            str(self.broker_identity.get("broker_server", "")),
                            int(self.broker_identity.get("account_login", 0) or 0),
                            self.spec_registry,
                            self.connector,
                            # FAST receives only fast_owned and inherited_fast positions/orders.
                            lambda: self.account_payload_for_desk(desk="fast"),
                            lambda symbol: self.evaluate_entry_for_desk(desk="fast", symbol=symbol),
                            lambda result, symbol, side, signal_id=None: self.register_fast_execution_ownership(
                                result=result,
                                symbol=symbol,
                                side=side,
                                signal_id=signal_id,
                            ),
                            lambda action_type: self.evaluate_action_for_desk(desk="fast", action_type=action_type),
                            lambda: self.ownership_open_for_desk(desk="fast"),
                            lambda: self.subscribed_symbols_for_desk("fast"),
                            mt5_call_ref=self._mt5_call,
                        ),
                        name="fast_desk",
                    )
                if self.correlation_service is not None:
                    tg.create_task(
                        self.correlation_service.refresh_loop(),
                        name="correlation",
                    )
                await self._stop_event.wait()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._stop_event.set()
        if not self._bootstrapped:
            return
        if self.config.sessions_enabled:
            await asyncio.to_thread(self.sessions_service.stop)
        with contextlib.suppress(Exception):
            await self._mt5_call(self.connector.shutdown)
        self.health["updated_at"] = utc_now_iso()

    def build_live_state(self) -> dict[str, Any]:
        account_state = self.account_payload.get("account_state") if isinstance(self.account_payload, dict) else {}
        exposure_state = self.account_payload.get("exposure_state") if isinstance(self.account_payload, dict) else {}
        open_positions = self.account_payload.get("positions") if isinstance(self.account_payload, dict) else []
        open_orders = self.account_payload.get("orders") if isinstance(self.account_payload, dict) else []
        broker_sessions = self.sessions_service.snapshot() if self.config.sessions_enabled else {
            "service": {"running": False, "host": self.config.sessions_host, "port": self.config.sessions_port}
        }
        workers_status = self.chart_registry.workers_status()
        
        # Get terminal info for trade_allowed status
        try:
            terminal_info = self.connector.terminal_info()
            trade_allowed = terminal_info.get("trade_allowed", False)
        except Exception:
            trade_allowed = False
        
        return {
            "status": self.health.get("status", "starting"),
            "health": self.health,
            "broker_identity": self.broker_identity,
            "server_time_offset_seconds": int(getattr(self.connector, "server_time_offset_seconds", 0) or 0),
            "broker_gmt_offset": session_registry.get_broker_gmt_offset(),
            "broker_clock_available": session_registry.is_broker_clock_available(),
            "trade_allowed": trade_allowed,  # NEW: Trade permission status
            "universes": {
                "catalog_universe_count": len(self.catalog_universe),
                "bootstrap_universe": self.bootstrap_universe,
                "subscribed_universe": self.subscribed_universe,
                "bootstrap_rejected_symbols": self.bootstrap_rejected_symbols,
            },
            "watched_timeframes": self.config.watch_timeframes,
            "chart_workers": {
                "count": len(workers_status),
                "symbols": [row["symbol"] for row in workers_status],
                "workers": workers_status,
            },
            "feed_status": self.feed_status_rows,
            "broker_session_registry": broker_sessions,
            "account_summary": account_state,
            "exposure_state": exposure_state,
            "open_positions": open_positions or [],
            "open_orders": open_orders or [],
            "indicator_enrichment": self.indicator_status,
            "runtime_metrics": self.runtime_metrics,
            "symbol_catalog": self.symbol_catalog_status,
            "symbol_specifications_count": len(self.symbol_specifications),
            "ownership": self.ownership_status,
            "risk": self.risk_status_payload() if self.risk_kernel is not None else {"status": "inactive"},
            "symbol_desk_assignments": self.get_all_symbol_desk_assignments(),
            "updated_at": utc_now_iso(),
        }


async def build_runtime_service(repo_root: Path) -> CoreRuntimeService:
    config = CoreRuntimeConfig.load(repo_root)
    # Use load_env_file + getenv so values from .env are honoured even when
    # they have not been injected into os.environ by the caller.
    env_values = load_env_file(repo_root / ".env")

    smc_enabled = _parse_bool(getenv("SMC_SCANNER_ENABLED", env_values, "false"), False)
    fast_enabled = _parse_bool(
        getenv("FAST_DESK_ENABLED", env_values, getenv("FAST_TRADER_ENABLED", env_values, "false")),
        False,
    )
    if fast_enabled:
        # Fast Desk evaluates M1/M5/M30 on every scan cycle, so those feeds must
        # be present even when the env file was configured for other desks first.
        config.watch_timeframes = _ensure_timeframes(config.watch_timeframes, ["M1", "M5", "M30"])

    service = CoreRuntimeService(config=config)
    if smc_enabled:
        from heuristic_mt5_bridge.smc_desk.runtime import create_smc_desk_service  # noqa: PLC0415

        smc_desk = create_smc_desk_service(config.runtime_db_path, correlation_service=service.correlation_service)
        service.attach_smc_desk(smc_desk)
    if fast_enabled:
        from heuristic_mt5_bridge.fast_desk.runtime import create_fast_desk_service  # noqa: PLC0415

        fast_desk = create_fast_desk_service(config.runtime_db_path, correlation_service=service.correlation_service)
        service.attach_fast_desk(fast_desk)

    return service
