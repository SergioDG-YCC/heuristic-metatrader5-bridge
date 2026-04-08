from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from heuristic_mt5_bridge.core.config.paths import resolve_runtime_db_path


SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = int(SQLITE_TIMEOUT_SECONDS * 1000)


def runtime_db_path(storage_root: Path, configured_path: str | None = None) -> Path:
    return resolve_runtime_db_path(storage_root, configured_path)


@contextmanager
def runtime_db_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def json_text(payload: Any) -> str:
    return json.dumps(payload if payload is not None else {}, ensure_ascii=True, separators=(",", ":"))


def decode_json_text(value: str | None, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nil"}:
        return None
    return text


def ensure_runtime_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with runtime_db_connection(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_state_cache (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_summary_json TEXT NOT NULL,
                chart_context_json TEXT,
                indicator_summary_json TEXT,
                source TEXT,
                PRIMARY KEY (broker_server, account_login, symbol, timeframe)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_spec_cache (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                digits INTEGER,
                point REAL,
                tick_size REAL,
                tick_value REAL,
                contract_size REAL,
                spread_float INTEGER,
                spread_points INTEGER,
                stops_level_points INTEGER,
                freeze_level_points INTEGER,
                volume_min REAL,
                volume_max REAL,
                volume_step REAL,
                volume_limit REAL,
                currency_base TEXT,
                currency_profit TEXT,
                currency_margin TEXT,
                trade_mode INTEGER,
                filling_mode INTEGER,
                order_mode INTEGER,
                expiration_mode INTEGER,
                trade_calc_mode INTEGER,
                margin_initial REAL,
                margin_maintenance REAL,
                margin_hedged REAL,
                swap_long REAL,
                swap_short REAL,
                specification_payload_json TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login, symbol)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_catalog_cache (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                description TEXT,
                path TEXT,
                asset_class TEXT,
                path_group TEXT,
                path_subgroup TEXT,
                visible INTEGER,
                selected INTEGER,
                custom INTEGER,
                trade_mode INTEGER,
                digits INTEGER,
                currency_base TEXT,
                currency_profit TEXT,
                currency_margin TEXT,
                catalog_payload_json TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login, symbol)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS account_state_cache (
                account_state_id TEXT PRIMARY KEY,
                account_login INTEGER NOT NULL,
                broker_server TEXT NOT NULL,
                broker_company TEXT,
                account_mode TEXT NOT NULL,
                currency TEXT NOT NULL,
                balance REAL NOT NULL,
                equity REAL NOT NULL,
                margin REAL NOT NULL,
                free_margin REAL NOT NULL,
                margin_level REAL NOT NULL,
                profit REAL NOT NULL,
                drawdown_amount REAL,
                drawdown_percent REAL NOT NULL,
                leverage INTEGER,
                open_position_count INTEGER NOT NULL,
                pending_order_count INTEGER NOT NULL,
                heartbeat_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                account_flags_json TEXT,
                account_payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS position_cache (
                position_id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                volume REAL NOT NULL,
                price_open REAL NOT NULL,
                price_current REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                profit REAL NOT NULL,
                swap REAL,
                commission REAL,
                magic INTEGER,
                comment TEXT,
                linked_trader_intent_id TEXT,
                linked_execution_id TEXT,
                opened_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                position_payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_cache (
                order_id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                volume_initial REAL NOT NULL,
                volume_current REAL,
                price_open REAL,
                stop_loss REAL,
                take_profit REAL,
                comment TEXT,
                linked_trader_intent_id TEXT,
                linked_execution_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                order_payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exposure_cache (
                exposure_state_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                gross_exposure REAL NOT NULL,
                net_exposure REAL NOT NULL,
                floating_profit REAL NOT NULL,
                open_position_count INTEGER NOT NULL,
                symbols_json TEXT NOT NULL,
                exposure_payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_event_cache (
                execution_event_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                linked_trader_intent_id TEXT,
                linked_risk_review_id TEXT,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT,
                mt5_order_id INTEGER,
                mt5_deal_id INTEGER,
                mt5_position_id INTEGER,
                price REAL,
                volume REAL,
                reason TEXT,
                created_at TEXT NOT NULL,
                execution_event_payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_state_cache_updated_at ON market_state_cache(updated_at DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_market_state_cache_symbol ON market_state_cache(symbol, timeframe)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_spec_cache_updated_at ON symbol_spec_cache(updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_catalog_cache_updated_at ON symbol_catalog_cache(updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_account_state_cache_updated_at ON account_state_cache(updated_at DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_position_cache_symbol ON position_cache(symbol, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_order_cache_symbol ON order_cache(symbol, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exposure_cache_updated_at ON exposure_cache(updated_at DESC)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_event_cache_execution_id ON execution_event_cache(execution_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_event_cache_symbol_created_at "
            "ON execution_event_cache(symbol, created_at DESC)"
        )
        # ------------------------------------------------------------------ SMC desk
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smc_zones (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                zone_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                zone_type TEXT NOT NULL,
                price_high REAL NOT NULL,
                price_low REAL NOT NULL,
                origin_candle_time TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                quality_score REAL NOT NULL DEFAULT 0.0,
                confluences_json TEXT NOT NULL DEFAULT '[]',
                detected_at TEXT NOT NULL,
                invalidated_at TEXT,
                distance_pct REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login, zone_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_zones_symbol ON smc_zones(broker_server, account_login, symbol, timeframe, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_zones_quality ON smc_zones(broker_server, account_login, quality_score DESC, updated_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smc_thesis_cache (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                thesis_id TEXT NOT NULL,
                strategy_type TEXT NOT NULL DEFAULT 'smc_prepared',
                bias TEXT NOT NULL,
                base_scenario TEXT,
                alternate_scenarios_json TEXT NOT NULL DEFAULT '[]',
                prepared_zones_json TEXT NOT NULL DEFAULT '[]',
                primary_zone_id TEXT,
                elliott_count_json TEXT,
                fibo_levels_json TEXT,
                multi_tf_alignment_json TEXT,
                validation_summary_json TEXT,
                validator_result_json TEXT,
                validator_decision TEXT,
                watch_conditions_json TEXT NOT NULL DEFAULT '[]',
                invalidations_json TEXT NOT NULL DEFAULT '[]',
                operation_candidates_json TEXT NOT NULL DEFAULT '[]',
                watch_levels_json TEXT NOT NULL DEFAULT '[]',
                analyst_notes TEXT,
                status TEXT NOT NULL DEFAULT 'watching',
                created_at TEXT NOT NULL,
                last_review_at TEXT NOT NULL,
                next_review_not_before TEXT,
                review_deadline TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login, symbol)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_thesis_status ON smc_thesis_cache(broker_server, account_login, status, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smc_events_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_events_log_symbol ON smc_events_log(broker_server, account_login, symbol, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_events_log_event_type ON smc_events_log(broker_server, account_login, event_type, created_at DESC)"
        )
        # ------------------------------------------------------------------ Fast desk
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fast_desk_signals (
                broker_server   TEXT NOT NULL,
                account_login   INTEGER NOT NULL,
                symbol          TEXT NOT NULL,
                signal_id       TEXT NOT NULL,
                side            TEXT NOT NULL,
                trigger         TEXT NOT NULL,
                confidence      REAL NOT NULL,
                entry_price     REAL NOT NULL,
                stop_loss       REAL NOT NULL,
                take_profit     REAL NOT NULL,
                stop_loss_pips  REAL NOT NULL,
                evidence_json   TEXT NOT NULL DEFAULT '{}',
                generated_at    TEXT NOT NULL,
                processed_at    TEXT,
                outcome         TEXT,
                PRIMARY KEY (broker_server, account_login, signal_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fast_signals_symbol "
            "ON fast_desk_signals(broker_server, account_login, symbol, generated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fast_desk_trade_log (
                broker_server   TEXT NOT NULL,
                account_login   INTEGER NOT NULL,
                log_id          TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                action          TEXT NOT NULL,
                position_id     INTEGER,
                signal_id       TEXT,
                details_json    TEXT NOT NULL DEFAULT '{}',
                logged_at       TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login, log_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fast_trade_log_symbol "
            "ON fast_desk_trade_log(broker_server, account_login, symbol, logged_at DESC)"
        )
        # ------------------------------------------------------------------ Ownership
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_ownership (
                operation_uid TEXT PRIMARY KEY,
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                operation_type TEXT NOT NULL,
                mt5_position_id INTEGER,
                mt5_order_id INTEGER,
                desk_owner TEXT NOT NULL,
                ownership_status TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                origin_type TEXT,
                reevaluation_required INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                adopted_at TEXT,
                reassigned_at TEXT,
                opened_at TEXT,
                closed_at TEXT,
                cancelled_at TEXT,
                last_seen_open_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_operation_ownership_position_unique "
            "ON operation_ownership(broker_server, account_login, mt5_position_id) "
            "WHERE mt5_position_id IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_operation_ownership_order_unique "
            "ON operation_ownership(broker_server, account_login, mt5_order_id) "
            "WHERE mt5_order_id IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_ownership_lifecycle "
            "ON operation_ownership(broker_server, account_login, lifecycle_status, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_ownership_owner "
            "ON operation_ownership(broker_server, account_login, desk_owner, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_ownership_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                operation_uid TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_owner TEXT,
                to_owner TEXT,
                from_status TEXT,
                to_status TEXT,
                reevaluation_required INTEGER,
                reason TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_ownership_events_uid "
            "ON operation_ownership_events(operation_uid, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_ownership_events_partition "
            "ON operation_ownership_events(broker_server, account_login, created_at DESC)"
        )
        # ------------------------------------------------------------------ Risk kernel
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_profile_state (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                profile_global INTEGER NOT NULL,
                profile_fast INTEGER NOT NULL,
                profile_smc INTEGER NOT NULL,
                overrides_json TEXT NOT NULL DEFAULT '{}',
                fast_budget_weight REAL NOT NULL,
                smc_budget_weight REAL NOT NULL,
                kill_switch_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_budget_state (
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                limits_json TEXT NOT NULL DEFAULT '{}',
                allocator_json TEXT NOT NULL DEFAULT '{}',
                usage_json TEXT NOT NULL DEFAULT '{}',
                kill_switch_state_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (broker_server, account_login)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_events_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_risk_events_partition "
            "ON risk_events_log(broker_server, account_login, created_at DESC)"
        )
        conn.commit()


def upsert_market_state_cache(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
    timeframe: str,
    updated_at: str,
    state_summary: dict[str, Any],
    chart_context: dict[str, Any] | None,
    indicator_summary: dict[str, Any] | None,
    source: str,
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_state_cache (
                broker_server,
                account_login,
                symbol,
                timeframe,
                updated_at,
                state_summary_json,
                chart_context_json,
                indicator_summary_json,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, symbol, timeframe) DO UPDATE SET
                updated_at=excluded.updated_at,
                state_summary_json=excluded.state_summary_json,
                chart_context_json=excluded.chart_context_json,
                indicator_summary_json=excluded.indicator_summary_json,
                source=excluded.source
            """,
            (
                str(broker_server).strip(),
                int(account_login),
                str(symbol).upper(),
                str(timeframe).upper(),
                updated_at,
                json_text(state_summary),
                json_text(chart_context) if chart_context is not None else None,
                json_text(indicator_summary) if indicator_summary is not None else None,
                source,
            ),
        )
        conn.commit()


def upsert_symbol_spec_cache(db_path: Path, specification: dict[str, Any]) -> None:
    ensure_runtime_db(db_path)
    broker_server = normalize_optional_text(specification.get("broker_server")) or ""
    account_login = int(specification.get("account_login") or 0)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO symbol_spec_cache (
                broker_server,
                account_login,
                symbol,
                updated_at,
                digits,
                point,
                tick_size,
                tick_value,
                contract_size,
                spread_float,
                spread_points,
                stops_level_points,
                freeze_level_points,
                volume_min,
                volume_max,
                volume_step,
                volume_limit,
                currency_base,
                currency_profit,
                currency_margin,
                trade_mode,
                filling_mode,
                order_mode,
                expiration_mode,
                trade_calc_mode,
                margin_initial,
                margin_maintenance,
                margin_hedged,
                swap_long,
                swap_short,
                specification_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, symbol) DO UPDATE SET
                updated_at=excluded.updated_at,
                digits=excluded.digits,
                point=excluded.point,
                tick_size=excluded.tick_size,
                tick_value=excluded.tick_value,
                contract_size=excluded.contract_size,
                spread_float=excluded.spread_float,
                spread_points=excluded.spread_points,
                stops_level_points=excluded.stops_level_points,
                freeze_level_points=excluded.freeze_level_points,
                volume_min=excluded.volume_min,
                volume_max=excluded.volume_max,
                volume_step=excluded.volume_step,
                volume_limit=excluded.volume_limit,
                currency_base=excluded.currency_base,
                currency_profit=excluded.currency_profit,
                currency_margin=excluded.currency_margin,
                trade_mode=excluded.trade_mode,
                filling_mode=excluded.filling_mode,
                order_mode=excluded.order_mode,
                expiration_mode=excluded.expiration_mode,
                trade_calc_mode=excluded.trade_calc_mode,
                margin_initial=excluded.margin_initial,
                margin_maintenance=excluded.margin_maintenance,
                margin_hedged=excluded.margin_hedged,
                swap_long=excluded.swap_long,
                swap_short=excluded.swap_short,
                specification_payload_json=excluded.specification_payload_json
            """,
            (
                broker_server,
                account_login,
                str(specification.get("symbol", "")).strip().upper(),
                str(specification.get("updated_at", "")).strip(),
                specification.get("digits"),
                specification.get("point"),
                specification.get("tick_size"),
                specification.get("tick_value"),
                specification.get("contract_size"),
                1 if bool(specification.get("spread_float", False)) else 0,
                specification.get("spread_points"),
                specification.get("stops_level_points"),
                specification.get("freeze_level_points"),
                specification.get("volume_min"),
                specification.get("volume_max"),
                specification.get("volume_step"),
                specification.get("volume_limit"),
                normalize_optional_text(specification.get("currency_base")),
                normalize_optional_text(specification.get("currency_profit")),
                normalize_optional_text(specification.get("currency_margin")),
                specification.get("trade_mode"),
                specification.get("filling_mode"),
                specification.get("order_mode"),
                specification.get("expiration_mode"),
                specification.get("trade_calc_mode"),
                specification.get("margin_initial"),
                specification.get("margin_maintenance"),
                specification.get("margin_hedged"),
                specification.get("swap_long"),
                specification.get("swap_short"),
                json_text(specification),
            ),
        )
        conn.commit()


def upsert_symbol_catalog_cache(db_path: Path, entry: dict[str, Any]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO symbol_catalog_cache (
                broker_server,
                account_login,
                symbol,
                updated_at,
                description,
                path,
                asset_class,
                path_group,
                path_subgroup,
                visible,
                selected,
                custom,
                trade_mode,
                digits,
                currency_base,
                currency_profit,
                currency_margin,
                catalog_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, symbol) DO UPDATE SET
                updated_at=excluded.updated_at,
                description=excluded.description,
                path=excluded.path,
                asset_class=excluded.asset_class,
                path_group=excluded.path_group,
                path_subgroup=excluded.path_subgroup,
                visible=excluded.visible,
                selected=excluded.selected,
                custom=excluded.custom,
                trade_mode=excluded.trade_mode,
                digits=excluded.digits,
                currency_base=excluded.currency_base,
                currency_profit=excluded.currency_profit,
                currency_margin=excluded.currency_margin,
                catalog_payload_json=excluded.catalog_payload_json
            """,
            (
                normalize_optional_text(entry.get("broker_server")) or "",
                int(entry.get("account_login", 0) or 0),
                str(entry.get("symbol", "")).strip().upper(),
                str(entry.get("updated_at", "")).strip(),
                normalize_optional_text(entry.get("description")),
                normalize_optional_text(entry.get("path")),
                normalize_optional_text(entry.get("asset_class")),
                normalize_optional_text(entry.get("path_group")),
                normalize_optional_text(entry.get("path_subgroup")),
                1 if bool(entry.get("visible")) else 0,
                1 if bool(entry.get("selected")) else 0,
                1 if bool(entry.get("custom")) else 0,
                entry.get("trade_mode"),
                entry.get("digits"),
                normalize_optional_text(entry.get("currency_base")),
                normalize_optional_text(entry.get("currency_profit")),
                normalize_optional_text(entry.get("currency_margin")),
                json_text(entry),
            ),
        )
        conn.commit()


def upsert_account_state_cache(db_path: Path, account_state: dict[str, Any]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_state_cache (
                account_state_id,
                account_login,
                broker_server,
                broker_company,
                account_mode,
                currency,
                balance,
                equity,
                margin,
                free_margin,
                margin_level,
                profit,
                drawdown_amount,
                drawdown_percent,
                leverage,
                open_position_count,
                pending_order_count,
                heartbeat_at,
                updated_at,
                account_flags_json,
                account_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_state_id) DO UPDATE SET
                account_login=excluded.account_login,
                broker_server=excluded.broker_server,
                broker_company=excluded.broker_company,
                account_mode=excluded.account_mode,
                currency=excluded.currency,
                balance=excluded.balance,
                equity=excluded.equity,
                margin=excluded.margin,
                free_margin=excluded.free_margin,
                margin_level=excluded.margin_level,
                profit=excluded.profit,
                drawdown_amount=excluded.drawdown_amount,
                drawdown_percent=excluded.drawdown_percent,
                leverage=excluded.leverage,
                open_position_count=excluded.open_position_count,
                pending_order_count=excluded.pending_order_count,
                heartbeat_at=excluded.heartbeat_at,
                updated_at=excluded.updated_at,
                account_flags_json=excluded.account_flags_json,
                account_payload_json=excluded.account_payload_json
            """,
            (
                str(account_state.get("account_state_id", "")).strip(),
                int(account_state.get("account_login", 0) or 0),
                str(account_state.get("broker_server", "")).strip(),
                normalize_optional_text(account_state.get("broker_company")),
                str(account_state.get("account_mode", "")).strip(),
                str(account_state.get("currency", "")).strip(),
                float(account_state.get("balance", 0.0) or 0.0),
                float(account_state.get("equity", 0.0) or 0.0),
                float(account_state.get("margin", 0.0) or 0.0),
                float(account_state.get("free_margin", 0.0) or 0.0),
                float(account_state.get("margin_level", 0.0) or 0.0),
                float(account_state.get("profit", 0.0) or 0.0),
                float(account_state.get("drawdown_amount", 0.0) or 0.0),
                float(account_state.get("drawdown_percent", 0.0) or 0.0),
                int(account_state.get("leverage", 0) or 0),
                int(account_state.get("open_position_count", 0) or 0),
                int(account_state.get("pending_order_count", 0) or 0),
                str(account_state.get("heartbeat_at", "")).strip(),
                str(account_state.get("updated_at", "")).strip(),
                json_text(account_state.get("account_flags", [])),
                json_text(account_state),
            ),
        )
        conn.commit()


def replace_position_cache(db_path: Path, positions: list[dict[str, Any]]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute("DELETE FROM position_cache")
        for payload in positions:
            conn.execute(
                """
                INSERT INTO position_cache (
                    position_id,
                    symbol,
                    side,
                    volume,
                    price_open,
                    price_current,
                    stop_loss,
                    take_profit,
                    profit,
                    swap,
                    commission,
                    magic,
                    comment,
                    linked_trader_intent_id,
                    linked_execution_id,
                    opened_at,
                    updated_at,
                    status,
                    position_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(payload.get("position_id", 0) or 0),
                    str(payload.get("symbol", "")).upper(),
                    str(payload.get("side", "")).strip(),
                    float(payload.get("volume", 0.0) or 0.0),
                    float(payload.get("price_open", 0.0) or 0.0),
                    float(payload.get("price_current", 0.0) or 0.0),
                    payload.get("stop_loss"),
                    payload.get("take_profit"),
                    float(payload.get("profit", 0.0) or 0.0),
                    float(payload.get("swap", 0.0) or 0.0),
                    float(payload.get("commission", 0.0) or 0.0),
                    int(payload.get("magic", 0) or 0),
                    normalize_optional_text(payload.get("comment")),
                    normalize_optional_text(payload.get("linked_trader_intent_id")),
                    normalize_optional_text(payload.get("linked_execution_id")),
                    str(payload.get("opened_at", "")).strip(),
                    str(payload.get("updated_at", "")).strip(),
                    str(payload.get("status", "")).strip(),
                    json_text(payload),
                ),
            )
        conn.commit()


def replace_order_cache(db_path: Path, orders: list[dict[str, Any]]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute("DELETE FROM order_cache")
        for payload in orders:
            conn.execute(
                """
                INSERT INTO order_cache (
                    order_id,
                    symbol,
                    order_type,
                    volume_initial,
                    volume_current,
                    price_open,
                    stop_loss,
                    take_profit,
                    comment,
                    linked_trader_intent_id,
                    linked_execution_id,
                    status,
                    created_at,
                    updated_at,
                    order_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(payload.get("order_id", 0) or 0),
                    str(payload.get("symbol", "")).upper(),
                    str(payload.get("order_type", "")).strip(),
                    float(payload.get("volume_initial", 0.0) or 0.0),
                    float(payload.get("volume_current", 0.0) or 0.0),
                    payload.get("price_open"),
                    payload.get("stop_loss"),
                    payload.get("take_profit"),
                    normalize_optional_text(payload.get("comment")),
                    normalize_optional_text(payload.get("linked_trader_intent_id")),
                    normalize_optional_text(payload.get("linked_execution_id")),
                    str(payload.get("status", "")).strip(),
                    str(payload.get("created_at", "")).strip(),
                    str(payload.get("updated_at", "")).strip(),
                    json_text(payload),
                ),
            )
        conn.commit()


def upsert_exposure_cache(db_path: Path, exposure_state: dict[str, Any]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO exposure_cache (
                exposure_state_id,
                updated_at,
                gross_exposure,
                net_exposure,
                floating_profit,
                open_position_count,
                symbols_json,
                exposure_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exposure_state_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                gross_exposure=excluded.gross_exposure,
                net_exposure=excluded.net_exposure,
                floating_profit=excluded.floating_profit,
                open_position_count=excluded.open_position_count,
                symbols_json=excluded.symbols_json,
                exposure_payload_json=excluded.exposure_payload_json
            """,
            (
                str(exposure_state.get("exposure_state_id", "")).strip(),
                str(exposure_state.get("updated_at", "")).strip(),
                float(exposure_state.get("gross_exposure", 0.0) or 0.0),
                float(exposure_state.get("net_exposure", 0.0) or 0.0),
                float(exposure_state.get("floating_profit", 0.0) or 0.0),
                int(exposure_state.get("open_position_count", 0) or 0),
                json_text(exposure_state.get("symbols", [])),
                json_text(exposure_state),
            ),
        )
        conn.commit()


def upsert_execution_event_cache(db_path: Path, execution_event: dict[str, Any]) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO execution_event_cache (
                execution_event_id,
                execution_id,
                linked_trader_intent_id,
                linked_risk_review_id,
                symbol,
                event_type,
                status,
                mt5_order_id,
                mt5_deal_id,
                mt5_position_id,
                price,
                volume,
                reason,
                created_at,
                execution_event_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(execution_event_id) DO UPDATE SET
                execution_id=excluded.execution_id,
                linked_trader_intent_id=excluded.linked_trader_intent_id,
                linked_risk_review_id=excluded.linked_risk_review_id,
                symbol=excluded.symbol,
                event_type=excluded.event_type,
                status=excluded.status,
                mt5_order_id=excluded.mt5_order_id,
                mt5_deal_id=excluded.mt5_deal_id,
                mt5_position_id=excluded.mt5_position_id,
                price=excluded.price,
                volume=excluded.volume,
                reason=excluded.reason,
                created_at=excluded.created_at,
                execution_event_payload_json=excluded.execution_event_payload_json
            """,
            (
                str(execution_event.get("execution_event_id", "")).strip(),
                str(execution_event.get("execution_id", "")).strip(),
                normalize_optional_text(execution_event.get("linked_trader_intent_id")),
                normalize_optional_text(execution_event.get("linked_risk_review_id")),
                str(execution_event.get("symbol", "")).upper(),
                str(execution_event.get("event_type", "")).strip(),
                normalize_optional_text(execution_event.get("status")),
                execution_event.get("mt5_order_id"),
                execution_event.get("mt5_deal_id"),
                execution_event.get("mt5_position_id"),
                execution_event.get("price"),
                execution_event.get("volume"),
                normalize_optional_text(execution_event.get("reason")),
                str(execution_event.get("created_at", "")).strip(),
                json_text(execution_event),
            ),
        )
        conn.commit()


def upsert_fast_signal(
    db_path: Path,
    broker_server: str,
    account_login: int,
    signal: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fast_desk_signals (
                broker_server,
                account_login,
                symbol,
                signal_id,
                side,
                trigger,
                confidence,
                entry_price,
                stop_loss,
                take_profit,
                stop_loss_pips,
                evidence_json,
                generated_at,
                processed_at,
                outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, signal_id) DO UPDATE SET
                symbol=excluded.symbol,
                side=excluded.side,
                trigger=excluded.trigger,
                confidence=excluded.confidence,
                entry_price=excluded.entry_price,
                stop_loss=excluded.stop_loss,
                take_profit=excluded.take_profit,
                stop_loss_pips=excluded.stop_loss_pips,
                evidence_json=excluded.evidence_json,
                generated_at=excluded.generated_at,
                processed_at=excluded.processed_at,
                outcome=excluded.outcome
            """,
            (
                str(broker_server).strip(),
                int(account_login),
                str(signal.get("symbol", "")).upper(),
                str(signal.get("signal_id", "")).strip(),
                str(signal.get("side", "")).strip(),
                str(signal.get("trigger", "")).strip(),
                float(signal.get("confidence", 0.0) or 0.0),
                float(signal.get("entry_price", 0.0) or 0.0),
                float(signal.get("stop_loss", 0.0) or 0.0),
                float(signal.get("take_profit", 0.0) or 0.0),
                float(signal.get("stop_loss_pips", 0.0) or 0.0),
                json_text(signal.get("evidence_json", {})),
                str(signal.get("generated_at", "")).strip(),
                normalize_optional_text(signal.get("processed_at")),
                normalize_optional_text(signal.get("outcome")),
            ),
        )
        conn.commit()


def append_fast_trade_log(
    db_path: Path,
    broker_server: str,
    account_login: int,
    event: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fast_desk_trade_log (
                broker_server,
                account_login,
                log_id,
                symbol,
                action,
                position_id,
                signal_id,
                details_json,
                logged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, log_id) DO UPDATE SET
                symbol=excluded.symbol,
                action=excluded.action,
                position_id=excluded.position_id,
                signal_id=excluded.signal_id,
                details_json=excluded.details_json,
                logged_at=excluded.logged_at
            """,
            (
                str(broker_server).strip(),
                int(account_login),
                str(event.get("log_id", "")).strip(),
                str(event.get("symbol", "")).upper(),
                str(event.get("action", "")).strip(),
                int(event.get("position_id", 0) or 0) if event.get("position_id") is not None else None,
                normalize_optional_text(event.get("signal_id")),
                json_text(event.get("details_json", {})),
                str(event.get("logged_at", "")).strip(),
            ),
        )
        conn.commit()


def get_operation_ownership_by_position_id(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    position_id: int,
) -> dict[str, Any] | None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM operation_ownership
            WHERE broker_server = ? AND account_login = ? AND mt5_position_id = ?
            LIMIT 1
            """,
            (str(broker_server).strip(), int(account_login), int(position_id)),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = decode_json_text(item.get("metadata_json"), {})
    item["reevaluation_required"] = bool(int(item.get("reevaluation_required", 0) or 0))
    return item


def get_operation_ownership_by_order_id(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    order_id: int,
) -> dict[str, Any] | None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM operation_ownership
            WHERE broker_server = ? AND account_login = ? AND mt5_order_id = ?
            LIMIT 1
            """,
            (str(broker_server).strip(), int(account_login), int(order_id)),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = decode_json_text(item.get("metadata_json"), {})
    item["reevaluation_required"] = bool(int(item.get("reevaluation_required", 0) or 0))
    return item


def upsert_operation_ownership(
    db_path: Path,
    row: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO operation_ownership (
                operation_uid,
                broker_server,
                account_login,
                operation_type,
                mt5_position_id,
                mt5_order_id,
                desk_owner,
                ownership_status,
                lifecycle_status,
                origin_type,
                reevaluation_required,
                reason,
                adopted_at,
                reassigned_at,
                opened_at,
                closed_at,
                cancelled_at,
                last_seen_open_at,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_uid) DO UPDATE SET
                broker_server=excluded.broker_server,
                account_login=excluded.account_login,
                operation_type=excluded.operation_type,
                mt5_position_id=excluded.mt5_position_id,
                mt5_order_id=excluded.mt5_order_id,
                desk_owner=excluded.desk_owner,
                ownership_status=excluded.ownership_status,
                lifecycle_status=excluded.lifecycle_status,
                origin_type=excluded.origin_type,
                reevaluation_required=excluded.reevaluation_required,
                reason=excluded.reason,
                adopted_at=excluded.adopted_at,
                reassigned_at=excluded.reassigned_at,
                opened_at=excluded.opened_at,
                closed_at=excluded.closed_at,
                cancelled_at=excluded.cancelled_at,
                last_seen_open_at=excluded.last_seen_open_at,
                metadata_json=excluded.metadata_json,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                str(row.get("operation_uid", "")).strip(),
                str(row.get("broker_server", "")).strip(),
                int(row.get("account_login", 0) or 0),
                str(row.get("operation_type", "")).strip(),
                int(row.get("mt5_position_id", 0) or 0) if row.get("mt5_position_id") is not None else None,
                int(row.get("mt5_order_id", 0) or 0) if row.get("mt5_order_id") is not None else None,
                str(row.get("desk_owner", "unassigned")).strip(),
                str(row.get("ownership_status", "unassigned")).strip(),
                str(row.get("lifecycle_status", "active")).strip(),
                normalize_optional_text(row.get("origin_type")),
                1 if bool(row.get("reevaluation_required")) else 0,
                normalize_optional_text(row.get("reason")),
                normalize_optional_text(row.get("adopted_at")),
                normalize_optional_text(row.get("reassigned_at")),
                normalize_optional_text(row.get("opened_at")),
                normalize_optional_text(row.get("closed_at")),
                normalize_optional_text(row.get("cancelled_at")),
                normalize_optional_text(row.get("last_seen_open_at")),
                json_text(row.get("metadata", {})),
                str(row.get("created_at", "")).strip(),
                str(row.get("updated_at", "")).strip(),
            ),
        )
        conn.commit()


def append_operation_ownership_event(
    db_path: Path,
    event: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO operation_ownership_events (
                broker_server,
                account_login,
                operation_uid,
                event_type,
                from_owner,
                to_owner,
                from_status,
                to_status,
                reevaluation_required,
                reason,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("broker_server", "")).strip(),
                int(event.get("account_login", 0) or 0),
                str(event.get("operation_uid", "")).strip(),
                str(event.get("event_type", "")).strip(),
                normalize_optional_text(event.get("from_owner")),
                normalize_optional_text(event.get("to_owner")),
                normalize_optional_text(event.get("from_status")),
                normalize_optional_text(event.get("to_status")),
                int(event.get("reevaluation_required", 0) or 0) if event.get("reevaluation_required") is not None else None,
                normalize_optional_text(event.get("reason")),
                json_text(event.get("payload", {})),
                str(event.get("created_at", "")).strip(),
            ),
        )
        conn.commit()


def list_operation_ownership(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    lifecycle_statuses: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    ensure_runtime_db(db_path)
    params: list[Any] = [str(broker_server).strip(), int(account_login)]
    where_extra = ""
    if lifecycle_statuses:
        placeholders = ",".join("?" for _ in lifecycle_statuses)
        where_extra = f" AND lifecycle_status IN ({placeholders})"
        params.extend(lifecycle_statuses)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM operation_ownership "
            "WHERE broker_server = ? AND account_login = ?"
            f"{where_extra} "
            "ORDER BY updated_at DESC",
            params,
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = decode_json_text(item.get("metadata_json"), {})
        item["reevaluation_required"] = bool(int(item.get("reevaluation_required", 0) or 0))
        items.append(item)
    return items


def purge_operation_ownership_history(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    cutoff_iso: str,
) -> int:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        deleted = conn.execute(
            """
            DELETE FROM operation_ownership
            WHERE broker_server = ?
              AND account_login = ?
              AND lifecycle_status IN ('closed', 'cancelled', 'filled')
              AND updated_at < ?
            """,
            (str(broker_server).strip(), int(account_login), str(cutoff_iso).strip()),
        ).rowcount
        conn.commit()
    return int(deleted or 0)


def upsert_risk_profile_state(
    db_path: Path,
    row: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO risk_profile_state (
                broker_server,
                account_login,
                profile_global,
                profile_fast,
                profile_smc,
                overrides_json,
                fast_budget_weight,
                smc_budget_weight,
                kill_switch_enabled,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login) DO UPDATE SET
                profile_global=excluded.profile_global,
                profile_fast=excluded.profile_fast,
                profile_smc=excluded.profile_smc,
                overrides_json=excluded.overrides_json,
                fast_budget_weight=excluded.fast_budget_weight,
                smc_budget_weight=excluded.smc_budget_weight,
                kill_switch_enabled=excluded.kill_switch_enabled,
                updated_at=excluded.updated_at
            """,
            (
                str(row.get("broker_server", "")).strip(),
                int(row.get("account_login", 0) or 0),
                int(row.get("profile_global", 2) or 2),
                int(row.get("profile_fast", 2) or 2),
                int(row.get("profile_smc", 2) or 2),
                json_text(row.get("overrides", {})),
                float(row.get("fast_budget_weight", 1.0) or 1.0),
                float(row.get("smc_budget_weight", 1.0) or 1.0),
                1 if bool(row.get("kill_switch_enabled", True)) else 0,
                str(row.get("updated_at", "")).strip(),
            ),
        )
        conn.commit()


def load_risk_profile_state(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
) -> dict[str, Any] | None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM risk_profile_state
            WHERE broker_server = ? AND account_login = ?
            LIMIT 1
            """,
            (str(broker_server).strip(), int(account_login)),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["overrides"] = decode_json_text(item.get("overrides_json"), {})
    item["kill_switch_enabled"] = bool(int(item.get("kill_switch_enabled", 0) or 0))
    return item


def upsert_risk_budget_state(
    db_path: Path,
    row: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO risk_budget_state (
                broker_server,
                account_login,
                limits_json,
                allocator_json,
                usage_json,
                kill_switch_state_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login) DO UPDATE SET
                limits_json=excluded.limits_json,
                allocator_json=excluded.allocator_json,
                usage_json=excluded.usage_json,
                kill_switch_state_json=excluded.kill_switch_state_json,
                updated_at=excluded.updated_at
            """,
            (
                str(row.get("broker_server", "")).strip(),
                int(row.get("account_login", 0) or 0),
                json_text(row.get("limits", {})),
                json_text(row.get("allocator", {})),
                json_text(row.get("usage", {})),
                json_text(row.get("kill_switch_state", {})),
                str(row.get("updated_at", "")).strip(),
            ),
        )
        conn.commit()


def load_risk_budget_state(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
) -> dict[str, Any] | None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM risk_budget_state
            WHERE broker_server = ? AND account_login = ?
            LIMIT 1
            """,
            (str(broker_server).strip(), int(account_login)),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["limits"] = decode_json_text(item.get("limits_json"), {})
    item["allocator"] = decode_json_text(item.get("allocator_json"), {})
    item["usage"] = decode_json_text(item.get("usage_json"), {})
    item["kill_switch_state"] = decode_json_text(item.get("kill_switch_state_json"), {})
    return item


def append_risk_event(
    db_path: Path,
    event: dict[str, Any],
) -> None:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO risk_events_log (
                broker_server,
                account_login,
                event_type,
                reason,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("broker_server", "")).strip(),
                int(event.get("account_login", 0) or 0),
                str(event.get("event_type", "")).strip(),
                normalize_optional_text(event.get("reason")),
                json_text(event.get("payload", {})),
                str(event.get("created_at", "")).strip(),
            ),
        )
        conn.commit()


def list_recent_risk_events(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_runtime_db(db_path)
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM risk_events_log
            WHERE broker_server = ? AND account_login = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(broker_server).strip(), int(account_login), int(limit)),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["payload"] = decode_json_text(item.get("payload_json"), {})
        items.append(item)
    return items


def purge_stale_broker_data(db_path: Path, broker_server: str, account_login: int) -> None:
    if not db_path.exists():
        return
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM symbol_spec_cache WHERE NOT (broker_server = ? AND account_login = ?)",
            (str(broker_server).strip(), int(account_login)),
        )
        conn.execute(
            "DELETE FROM market_state_cache WHERE NOT (broker_server = ? AND account_login = ?)",
            (str(broker_server).strip(), int(account_login)),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# SMC desk — zone CRUD
# ---------------------------------------------------------------------------

def upsert_smc_zone(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    zone: dict[str, Any],
) -> None:
    """Insert or update a zone in smc_zones (broker-partitioned)."""
    from datetime import datetime, timezone

    ensure_runtime_db(db_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO smc_zones (
                broker_server, account_login, zone_id, symbol, timeframe, zone_type,
                price_high, price_low, origin_candle_time,
                status, quality_score, confluences_json,
                detected_at, invalidated_at, distance_pct, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, zone_id) DO UPDATE SET
                status=excluded.status,
                quality_score=excluded.quality_score,
                confluences_json=excluded.confluences_json,
                invalidated_at=excluded.invalidated_at,
                distance_pct=excluded.distance_pct,
                updated_at=excluded.updated_at
            """,
            (
                str(broker_server).strip(),
                int(account_login),
                str(zone["zone_id"]),
                str(zone.get("symbol", "")).upper(),
                str(zone.get("timeframe", "")).upper(),
                str(zone.get("zone_type", "")),
                float(zone.get("price_high", 0.0) or 0.0),
                float(zone.get("price_low", 0.0) or 0.0),
                str(zone.get("origin_candle_time", "")) or None,
                str(zone.get("status", "active")),
                float(zone.get("quality_score", 0.0) or 0.0),
                json_text(zone.get("confluences", [])),
                str(zone.get("detected_at", now)),
                str(zone.get("invalidated_at", "")) or None,
                float(zone["distance_pct"]) if zone.get("distance_pct") is not None else None,
                now,
            ),
        )
        conn.commit()


def load_active_smc_zones(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str | None = None,
    timeframe: str | None = None,
    status_filter: tuple[str, ...] = ("active", "approaching"),
) -> list[dict[str, Any]]:
    """Load SMC zones for a broker partition, optionally filtered by symbol/timeframe/status."""
    ensure_runtime_db(db_path)
    placeholders = ",".join("?" for _ in status_filter)
    params: list[Any] = [str(broker_server).strip(), int(account_login)]
    params += list(status_filter)
    where_extra = ""
    if symbol:
        where_extra += " AND symbol = ?"
        params.append(str(symbol).upper())
    if timeframe:
        where_extra += " AND timeframe = ?"
        params.append(str(timeframe).upper())
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM smc_zones WHERE broker_server=? AND account_login=? "
            f"AND status IN ({placeholders}){where_extra} "
            f"ORDER BY quality_score DESC, updated_at DESC",
            params,
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["confluences"] = decode_json_text(d.get("confluences_json"), [])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# SMC desk — thesis CRUD
# ---------------------------------------------------------------------------

def upsert_smc_thesis(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    thesis: dict[str, Any],
) -> None:
    """Upsert an SMC thesis (one row per broker+symbol)."""
    from datetime import datetime, timezone

    ensure_runtime_db(db_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO smc_thesis_cache (
                broker_server, account_login, symbol,
                thesis_id, strategy_type, bias,
                base_scenario, alternate_scenarios_json, prepared_zones_json,
                primary_zone_id,
                elliott_count_json, fibo_levels_json, multi_tf_alignment_json,
                validation_summary_json, validator_result_json, validator_decision,
                watch_conditions_json, invalidations_json, operation_candidates_json,
                watch_levels_json, analyst_notes,
                status, created_at, last_review_at,
                next_review_not_before, review_deadline, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_server, account_login, symbol) DO UPDATE SET
                thesis_id=excluded.thesis_id,
                bias=excluded.bias,
                base_scenario=excluded.base_scenario,
                alternate_scenarios_json=excluded.alternate_scenarios_json,
                prepared_zones_json=excluded.prepared_zones_json,
                primary_zone_id=excluded.primary_zone_id,
                elliott_count_json=excluded.elliott_count_json,
                fibo_levels_json=excluded.fibo_levels_json,
                multi_tf_alignment_json=excluded.multi_tf_alignment_json,
                validation_summary_json=excluded.validation_summary_json,
                validator_result_json=excluded.validator_result_json,
                validator_decision=excluded.validator_decision,
                watch_conditions_json=excluded.watch_conditions_json,
                invalidations_json=excluded.invalidations_json,
                operation_candidates_json=excluded.operation_candidates_json,
                watch_levels_json=excluded.watch_levels_json,
                analyst_notes=excluded.analyst_notes,
                status=excluded.status,
                last_review_at=excluded.last_review_at,
                next_review_not_before=excluded.next_review_not_before,
                review_deadline=excluded.review_deadline,
                updated_at=excluded.updated_at
            """,
            (
                str(broker_server).strip(),
                int(account_login),
                str(thesis.get("symbol", "")).upper(),
                str(thesis.get("thesis_id", "")),
                str(thesis.get("strategy_type", "smc_prepared")),
                str(thesis.get("bias", "unclear")),
                str(thesis.get("base_scenario", "")) or None,
                json_text(thesis.get("alternate_scenarios", [])),
                json_text(thesis.get("prepared_zones", [])),
                str(thesis.get("primary_zone_id", "")).strip() or None,
                json_text(thesis.get("elliott_count")) if thesis.get("elliott_count") else None,
                json_text(thesis.get("fibo_levels")) if thesis.get("fibo_levels") else None,
                json_text(thesis.get("multi_timeframe_alignment")) if thesis.get("multi_timeframe_alignment") else None,
                json_text(thesis.get("validation_summary")) if thesis.get("validation_summary") else None,
                json_text(thesis.get("validator_result")) if thesis.get("validator_result") else None,
                str(thesis.get("validator_decision", "")).strip() or None,
                json_text(thesis.get("watch_conditions", [])),
                json_text(thesis.get("invalidations", [])),
                json_text(thesis.get("operation_candidates", [])),
                json_text(thesis.get("watch_levels", [])),
                str(thesis.get("analyst_notes", "")) or None,
                str(thesis.get("status", "watching")),
                str(thesis.get("created_at", now)),
                str(thesis.get("last_review_at", now)),
                str(thesis.get("next_review_not_before", "")) or None,
                str(thesis.get("review_deadline", "")) or None,
                now,
            ),
        )
        conn.commit()


def load_active_smc_thesis(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Load active/watching SMC theses for a broker partition."""
    ensure_runtime_db(db_path)
    params: list[Any] = [str(broker_server).strip(), int(account_login), "active", "watching"]
    where_extra = ""
    if symbol:
        where_extra = " AND symbol = ?"
        params.append(str(symbol).upper())
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM smc_thesis_cache WHERE broker_server=? AND account_login=? "
            f"AND status IN (?, ?){where_extra} ORDER BY updated_at DESC",
            params,
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        for field in ("alternate_scenarios", "prepared_zones", "watch_conditions",
                      "invalidations", "operation_candidates", "watch_levels"):
            d[field] = decode_json_text(d.get(f"{field}_json"), [])
        for field in ("elliott_count", "fibo_levels", "multi_tf_alignment"):
            raw = d.get(f"{field}_json")
            d[field] = decode_json_text(raw, None) if raw else None
        for field in ("validation_summary", "validator_result"):
            raw = d.get(f"{field}_json")
            d[field] = decode_json_text(raw, None) if raw else None
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# SMC desk — event log
# ---------------------------------------------------------------------------

def log_smc_event(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Append an entry to smc_events_log."""
    from datetime import datetime, timezone

    ensure_runtime_db(db_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO smc_events_log (broker_server, account_login, symbol, event_type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(broker_server).strip(),
                int(account_login),
                str(symbol).upper(),
                str(event_type),
                json_text(payload),
                now,
            ),
        )
        conn.commit()


def load_recent_smc_events(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
    event_type: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return recent smc_events_log rows for a given symbol and event_type."""
    import json as _json

    if not Path(db_path).exists():
        return []
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT payload_json, created_at
                FROM smc_events_log
                WHERE broker_server = ? AND account_login = ?
                  AND symbol = ? AND event_type = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (
                    str(broker_server).strip(),
                    int(account_login),
                    str(symbol).upper(),
                    str(event_type),
                    int(limit),
                ),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = _json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            payload["created_at"] = row["created_at"]
            results.append(payload)
    return results


def load_symbol_volume_options(
    db_path: Path,
    *,
    broker_server: str,
    account_login: int,
    symbol: str,
) -> list[float]:
    """Return sensible trade volume choices based on the symbol spec cache."""
    if not Path(db_path).exists():
        return [0.01, 0.02, 0.05]
    with runtime_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT volume_min, volume_max, volume_step
                FROM symbol_spec_cache
                WHERE broker_server = ? AND account_login = ? AND UPPER(symbol) = UPPER(?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(broker_server).strip(), int(account_login), str(symbol).upper()),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None

    if row:
        vmin = float(row["volume_min"] or 0.0)
        vmax = float(row["volume_max"] or 0.0)
        step = float(row["volume_step"] or 0.0)
        if vmin > 0 and step > 0:
            options = [
                round(vmin, 8),
                round(vmin + step * 2, 8),
                round(vmin + step * 5, 8),
            ]
            if vmax > 0:
                options = [v for v in options if v <= vmax]
            valid = sorted(set(v for v in options if v > 0))
            if valid:
                return valid[:5]
    return [0.01, 0.02, 0.05]
