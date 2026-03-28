"""
Integration Probe — heuristic-mt5-bridge
=========================================
Connects to the real MT5 terminal, runs bootstrap + one poll cycle,
then verifies every architectural invariant against live data.

Usage:
    .venv\\Scripts\\python.exe scripts/integration_probe.py

Requirements:
    - MT5 terminal running and logged in
    - .env present with MT5_WATCH_SYMBOLS, MT5_WATCH_TIMEFRAMES, etc.
    - .venv activated

Exit codes:
    0 — all CRITICAL checks passed
    1 — one or more CRITICAL checks failed
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap (scripts/ lives outside src/, add src/ to sys.path)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from heuristic_mt5_bridge.core.config.env import repo_root_from
from heuristic_mt5_bridge.core.runtime.service import build_runtime_service
from heuristic_mt5_bridge.infra.mt5.connector import MT5ConnectorError
from heuristic_mt5_bridge.shared.time.utc import utc_now_iso

# ---------------------------------------------------------------------------
# Report primitives
# ---------------------------------------------------------------------------

_results: list[tuple[str, str, str]] = []  # (level, tag, message)


def _pass(tag: str, msg: str) -> None:
    _results.append(("PASS", tag, msg))
    print(f"  \033[32m[PASS]\033[0m {tag}: {msg}")


def _fail(tag: str, msg: str) -> None:
    _results.append(("FAIL", tag, msg))
    print(f"  \033[31m[FAIL]\033[0m {tag}: {msg}")


def _info(tag: str, msg: str) -> None:
    _results.append(("INFO", tag, msg))
    print(f"  \033[33m[INFO]\033[0m {tag}: {msg}")


def _section(title: str) -> None:
    print(f"\n\033[1m--- {title} ---\033[0m")


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------


def check_broker_identity(service: Any) -> None:
    _section("MT5 CONNECTION")
    ident = service.broker_identity
    broker_server = str(ident.get("broker_server", "")).strip()
    account_login = int(ident.get("account_login", 0) or 0)
    if broker_server and account_login:
        _pass("broker_identity", f"broker_server={broker_server!r}, account_login={account_login}")
    else:
        _fail("broker_identity", f"incomplete — got: {ident}")

    offset = int(getattr(service.connector, "server_time_offset_seconds", 0) or 0)
    hours = offset // 3600
    sign = "+" if hours >= 0 else ""
    _pass("server_time_offset", f"{offset}s (UTC{sign}{hours})")

    catalog_count = len(service.catalog_universe)
    if catalog_count > 0:
        _pass("catalog_universe", f"{catalog_count} symbols loaded from broker")
    else:
        _fail("catalog_universe", "empty — broker returned no symbols")


def check_ram_state(service: Any) -> None:
    _section("RAM STATE")
    subscribed = service.subscribed_universe
    if subscribed:
        _pass("subscribed_universe", f"{subscribed}")
    else:
        _fail("subscribed_universe", "empty — no symbols subscribed after bootstrap")

    worker_count = service.chart_registry.worker_count()
    if worker_count == len(subscribed):
        _pass("chart_workers", f"{worker_count} workers == {len(subscribed)} subscribed symbols")
    else:
        _fail(
            "chart_workers",
            f"{worker_count} workers != {len(subscribed)} subscribed symbols",
        )

    # Per-symbol/timeframe bar counts via build_chart_context (returns window_bars)
    timeframes = service.config.watch_timeframes
    all_have_bars = True
    bar_lines: list[str] = []
    ctx_ok: list[str] = []
    ctx_fail: list[str] = []
    distance_is_none = True
    for symbol in subscribed:
        for tf in timeframes:
            ctx = service.market_state.build_chart_context(symbol, tf)
            label = f"{symbol}/{tf}"
            bar_count = int(ctx.get("window_bars", 0)) if ctx else 0
            bar_lines.append(f"{label}:{bar_count}")
            if bar_count == 0:
                all_have_bars = False
            if ctx is not None:
                ctx_ok.append(label)
                if ctx.get("distance_to_session_high_pips") is not None:
                    distance_is_none = False
            else:
                ctx_fail.append(label)
    if all_have_bars and bar_lines:
        _pass("chart_bars_in_RAM", "  ".join(bar_lines))
    elif not bar_lines:
        _fail("chart_bars_in_RAM", "no (symbol, timeframe) combinations to check")
    else:
        empty = [item for item in bar_lines if item.endswith(":0")]
        _fail("chart_bars_in_RAM", f"some (symbol, timeframe) have 0 bars: {empty}")

    # Symbol specs — no bid/ask
    specs = service.symbol_specifications
    if specs:
        specs_with_bid_ask = [
            str(s.get("symbol")) for s in specs if "bid" in s or "ask" in s
        ]
        if specs_with_bid_ask:
            _fail("symbol_specs_no_bid_ask", f"bid/ask found in specs for: {specs_with_bid_ask}")
        else:
            _pass("symbol_specs_no_bid_ask", f"no bid/ask in any of the {len(specs)} specs")

        # Static fields present
        missing_static: list[str] = []
        for s in specs:
            sym = str(s.get("symbol", "?"))
            if not s.get("point") and not s.get("digits"):
                missing_static.append(sym)
        if missing_static:
            _fail("symbol_specs_have_static_fields", f"missing point/digits for: {missing_static}")
        else:
            _pass("symbol_specs_have_static_fields", f"point/digits present for all {len(specs)} specs")
    else:
        _fail("symbol_specs", "empty — no specs loaded after bootstrap")

    # build_chart_context summary (computed above together with bar counts)
    total = len(ctx_ok) + len(ctx_fail)
    if not ctx_fail:
        _pass("build_chart_context", f"{len(ctx_ok)}/{total} returned non-null")
    else:
        _fail("build_chart_context", f"{len(ctx_fail)} returned null: {ctx_fail}")

    if distance_is_none:
        _info(
            "distance_fields",
            "all distance_to_* are None — pip_size not yet wired (expected, Fase 3 pending)",
        )
    else:
        _pass("distance_fields", "pip_size wired, distance values computed")


def check_sqlite_integrity(service: Any) -> None:
    _section("SQLITE INTEGRITY")
    db_path = service.config.runtime_db_path
    broker_server = str(service.broker_identity.get("broker_server", "")).strip()
    account_login = int(service.broker_identity.get("account_login", 0) or 0)
    subscribed = service.subscribed_universe
    timeframes = service.config.watch_timeframes
    expected_market_rows = len(subscribed) * len(timeframes)

    if not db_path.exists():
        _fail("runtime_db_exists", f"db not found at {db_path}")
        return
    _pass("runtime_db_exists", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # --- market_state_cache ---
        market_rows = conn.execute("SELECT * FROM market_state_cache").fetchall()
        stale_market = [
            dict(r) for r in market_rows
            if r["broker_server"] != broker_server or int(r["account_login"]) != account_login
        ]
        if stale_market:
            _fail(
                "market_state_cache_partitioned",
                f"{len(stale_market)} rows with wrong broker identity",
            )
        else:
            _pass(
                "market_state_cache_partitioned",
                f"{len(market_rows)} rows, all broker_server={broker_server!r}, account_login={account_login}",
            )
        if len(market_rows) >= expected_market_rows:
            _pass(
                "market_state_cache_row_count",
                f"{len(market_rows)} rows >= {expected_market_rows} expected ({len(subscribed)} symbols × {len(timeframes)} timeframes)",
            )
        else:
            _fail(
                "market_state_cache_row_count",
                f"{len(market_rows)} rows < {expected_market_rows} expected",
            )

        # Check schema has no bid/ask columns
        market_cols = {row[1] for row in conn.execute("PRAGMA table_info(market_state_cache)")}
        forbidden_market = market_cols & {"bid", "ask", "last_price", "tick_age_seconds", "bar_age_seconds", "feed_status"}
        if forbidden_market:
            _fail("market_state_cache_no_live_cols", f"forbidden columns present: {forbidden_market}")
        else:
            _pass("market_state_cache_no_live_cols", "no bid/ask/feed_status columns in market_state_cache")

        # --- symbol_spec_cache ---
        spec_rows = conn.execute("SELECT * FROM symbol_spec_cache").fetchall()
        stale_specs = [
            dict(r) for r in spec_rows
            if r["broker_server"] != broker_server or int(r["account_login"]) != account_login
        ]
        if stale_specs:
            _fail(
                "symbol_spec_cache_partitioned",
                f"{len(stale_specs)} rows with wrong broker identity",
            )
        else:
            _pass(
                "symbol_spec_cache_partitioned",
                f"{len(spec_rows)} rows, all broker_server={broker_server!r}, account_login={account_login}",
            )

        spec_cols = {row[1] for row in conn.execute("PRAGMA table_info(symbol_spec_cache)")}
        forbidden_spec = spec_cols & {"bid", "ask"}
        if forbidden_spec:
            _fail("symbol_spec_cache_no_bid_ask", f"forbidden columns present: {forbidden_spec}")
        else:
            _pass("symbol_spec_cache_no_bid_ask", "no bid/ask columns in symbol_spec_cache")

        # --- symbol_catalog_cache ---
        catalog_count = conn.execute("SELECT COUNT(*) FROM symbol_catalog_cache").fetchone()[0]
        if catalog_count > 0:
            _pass("symbol_catalog_cache", f"{catalog_count} rows in catalog")
        else:
            _fail("symbol_catalog_cache", "empty")

        # Verify PK uniqueness per broker (no duplicate symbol for same broker identity)
        dup_check = conn.execute(
            """
            SELECT broker_server, account_login, symbol, COUNT(*) AS cnt
            FROM symbol_spec_cache
            GROUP BY broker_server, account_login, symbol
            HAVING cnt > 1
            """
        ).fetchall()
        if dup_check:
            _fail("symbol_spec_cache_no_pk_duplicates", f"{len(dup_check)} duplicate PKs: {[dict(r) for r in dup_check]}")
        else:
            _pass("symbol_spec_cache_no_pk_duplicates", "no duplicate (broker_server, account_login, symbol) rows")


def check_physical_invariants(service: Any) -> None:
    _section("PHYSICAL INVARIANTS")
    storage_root = service.config.storage_root

    live_dir = storage_root / "live"
    if live_dir.exists():
        files = list(live_dir.iterdir())
        _fail("no_live_dir", f"storage/live/ EXISTS with {len(files)} files: {[f.name for f in files[:5]]}")
    else:
        _pass("no_live_dir", "storage/live/ does not exist")

    snapshots_dir = storage_root / "indicator_snapshots"
    if snapshots_dir.exists():
        json_files = list(snapshots_dir.glob("*.json"))
        if json_files:
            _fail(
                "no_indicator_snapshot_files",
                f"{len(json_files)} .json files in storage/indicator_snapshots/: {[f.name for f in json_files[:5]]}",
            )
        else:
            _pass("no_indicator_snapshot_files", "storage/indicator_snapshots/ exists but is empty")
    else:
        _pass("no_indicator_snapshot_files", "storage/indicator_snapshots/ does not exist")


def check_sessions(service: Any) -> None:
    _section("BROKER SESSIONS")
    if not service.config.sessions_enabled:
        _info("broker_sessions", "disabled in config (BROKER_SESSIONS_ENABLED=false)")
        return
    snap = service.sessions_service.snapshot()
    svc_info = snap.get("service", {}) if isinstance(snap, dict) else {}
    running = bool(svc_info.get("running", False))
    if running:
        registry_info = snap.get("registry", {}) if isinstance(snap, dict) else {}
        symbol_count = len(registry_info) if isinstance(registry_info, dict) else 0
        _pass("broker_sessions_running", f"TCP receiver active, {symbol_count} symbols in registry")
        # Check that subscribed symbols have session data
        subscribed = service.subscribed_universe
        missing_sessions = [s for s in subscribed if s not in registry_info]
        if missing_sessions:
            _info(
                "broker_sessions_coverage",
                f"{len(missing_sessions)} subscribed symbols not yet in session registry: {missing_sessions}",
            )
        else:
            _pass("broker_sessions_coverage", "all subscribed symbols have session data")
    else:
        _info(
            "broker_sessions_not_running",
            "BrokerSessionsService TCP receiver not active — attach LLMBrokerSessionsService.mq5 EA to MT5",
        )


def check_indicator_bridge(service: Any) -> None:
    _section("INDICATOR BRIDGE")
    status_info = service.indicator_status
    status = str(status_info.get("status", "inactive"))
    enabled = bool(status_info.get("enabled", False))

    if not enabled:
        _info("indicator_bridge", "disabled in config (INDICATOR_ENRICHMENT_ENABLED=false)")
        return

    valid_statuses = {"inactive", "waiting_first_snapshot", "healthy", "stale"}
    if status in valid_statuses:
        if status == "healthy":
            total = int(status_info.get("total_imported", 0))
            _pass("indicator_bridge_status", f"status=healthy, {total} snapshots imported total")
        else:
            _info(
                "indicator_bridge_status",
                f"status={status!r} — attach LLMIndicatorServiceEA.mq5 to MT5 to enable enrichment",
            )
    else:
        _fail("indicator_bridge_status", f"unexpected status: {status!r}")

    # Verify no local copies written
    storage_root = service.config.storage_root
    snapshots_dir = storage_root / "indicator_snapshots"
    if snapshots_dir.exists() and list(snapshots_dir.glob("*.json")):
        _fail(
            "indicator_bridge_no_local_copy",
            "IndicatorBridge wrote local copies to storage/indicator_snapshots/ — bug!",
        )
    else:
        _pass("indicator_bridge_no_local_copy", "no local disk copies written by IndicatorBridge")


def check_utc_normalization(service: Any) -> None:
    _section("UTC0 NORMALIZATION")
    offset = int(getattr(service.connector, "server_time_offset_seconds", 0) or 0)

    # Check all chart context timestamps are UTC (end with 'Z' or '+00:00')
    subscribed = service.subscribed_universe
    timeframes = service.config.watch_timeframes
    bad_timestamps: list[str] = []

    for symbol in subscribed:
        for tf in timeframes:
            ctx = service.market_state.build_chart_context(symbol, tf)
            if ctx is None:
                continue
            for candle in (ctx.get("candles") or [])[:3]:
                ts = str(candle.get("time", "") if isinstance(candle, dict) else "")
                if ts and not ts.endswith("Z") and "+00:00" not in ts:
                    bad_timestamps.append(f"{symbol}/{tf}: {ts!r}")

    if bad_timestamps:
        _fail(
            "candle_timestamps_utc",
            f"{len(bad_timestamps)} non-UTC timestamps found: {bad_timestamps[:5]}",
        )
    else:
        _pass(
            "candle_timestamps_utc",
            f"all sampled candle timestamps are UTC0 (server offset was {offset}s)",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run_probe() -> int:
    print("\n\033[1m=== INTEGRATION PROBE — heuristic-mt5-bridge ===\033[0m")
    print(f"Started: {utc_now_iso()}")
    print(f"Repo root: {_REPO_ROOT}")

    repo_root = Path(repo_root_from(str(_REPO_ROOT / "apps" / "core_runtime.py")))
    service = await build_runtime_service(repo_root)

    print("\nConnecting to MT5 and running bootstrap + one cycle...")
    try:
        await service.run_once()
    except MT5ConnectorError as exc:
        print(f"\n\033[31m[ERROR] MT5 connection failed: {exc}\033[0m")
        print("Make sure MT5 terminal is running and logged in before running this probe.")
        return 1
    except Exception as exc:
        print(f"\n\033[31m[ERROR] Unexpected error during run_once(): {exc}\033[0m")
        import traceback
        traceback.print_exc()
        return 1

    print("Bootstrap + run_once() completed. Running invariant checks...\n")

    check_broker_identity(service)
    check_ram_state(service)
    check_sqlite_integrity(service)
    check_physical_invariants(service)
    check_sessions(service)
    check_indicator_bridge(service)
    check_utc_normalization(service)

    await service.shutdown()

    # Summary
    passed = [item for item in _results if item[0] == "PASS"]
    failed = [item for item in _results if item[0] == "FAIL"]
    info = [item for item in _results if item[0] == "INFO"]

    print(f"\n\033[1m--- SUMMARY ---\033[0m")
    print(f"  PASS:  {len(passed)}")
    print(f"  FAIL:  {len(failed)}")
    print(f"  INFO:  {len(info)}")

    if failed:
        print("\n\033[31mFailed checks:\033[0m")
        for _, tag, msg in failed:
            print(f"  - {tag}: {msg}")
        print(f"\n\033[31mResult: {len(failed)} critical check(s) FAILED\033[0m")
        return 1

    print(f"\n\033[32mResult: all {len(passed)} critical checks PASSED\033[0m")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run_probe())
    except KeyboardInterrupt:
        print("\n[interrupted]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
