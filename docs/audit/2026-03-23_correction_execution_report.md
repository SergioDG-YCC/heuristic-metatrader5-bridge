# Correction Execution Report — 2026-03-23

**Plan:** `docs/plans/2026-03-23_correction_action_plan.md`
**Status:** ✅ All fases completed. 15/15 tests pass.

---

## Summary of Changes

### Fase 0 — Pre-existing (no action needed)
- `README.md` MUST/MUST NOT rules — already correct
- `.gitignore` storage paths — already correct

---

### Fase 1.1 — Physical file purge
**Deleted:**
- `storage/live/core_runtime.json`
- `storage/live/` (directory)
- `storage/runtime.db`
- `storage/indicator_snapshots/*.json`

---

### Fase 1.2 — Remove live publish loop
**File:** `src/heuristic_mt5_bridge/core/runtime/service.py`

- Removed `CORE_LIVE_PUBLISH_SECONDS` env var read
- Removed `live_publish_seconds: float` field from `CoreRuntimeConfig`
- Removed `_persist_live_state()` method entirely
- Removed `_persist_live_state()` calls from `bootstrap()`, `run_once()`, `shutdown()`
- Removed `live_state` task from `run_forever()` task loop
- Removed `from heuristic_mt5_bridge.infra.storage.json_files import persist_json` import

`build_live_state()` is retained as a pure in-memory method for future Control Plane HTTP use.

---

### Fase 1.3 — Remove bid/ask from connector spec
**File:** `src/heuristic_mt5_bridge/infra/mt5/connector.py`

- Removed `tick = mt5.symbol_info_tick(symbol)` call from `fetch_symbol_specification()`
- Removed `"bid"` and `"ask"` keys from the return dict
- `fetch_symbol_specification()` now returns only static spec data

---

### Fase 1.4 + 2.1 + 2.2 + 2.4 — runtime_db schema refactor
**File:** `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`

**`market_state_cache` table:**
- Primary key changed from `(symbol, timeframe)` → `(broker_server, account_login, symbol, timeframe)`
- Removed columns: `bid`, `ask`, `feed_status`, `tick_age_seconds`, `bar_age_seconds`, `last_price`
- Added columns: `broker_server TEXT NOT NULL`, `account_login INTEGER NOT NULL`

**`symbol_spec_cache` table:**
- Primary key changed from `symbol` → `(broker_server, account_login, symbol)`
- Removed columns: `bid`, `ask`
- `broker_server` and `account_login` are now `NOT NULL`

**`upsert_market_state_cache()` signature change:**
```python
# Before
upsert_market_state_cache(db_path, *, symbol, timeframe, updated_at,
    last_price, bid, ask, feed_status, tick_age_seconds, bar_age_seconds,
    state_summary, chart_context, indicator_summary, source)

# After
upsert_market_state_cache(db_path, *, broker_server, account_login,
    symbol, timeframe, updated_at,
    state_summary, chart_context, indicator_summary, source)
```

**`upsert_symbol_spec_cache()`:** Now reads `broker_server` and `account_login` from the specification dict and uses them as part of the composite key.

**New function `purge_stale_broker_data(db_path, broker_server, account_login)`:**
- Deletes rows from `market_state_cache` and `symbol_spec_cache` where the stored broker identity does not match the provided values
- Called during `bootstrap()` to evict rows from a previous broker session

---

### Fase 1.5 — Remove local indicator snapshot copy
**File:** `src/heuristic_mt5_bridge/infra/indicators/bridge.py`

- Removed `from heuristic_mt5_bridge.infra.storage.json_files import persist_json`
- Removed `self.local_snapshots_dir = self.storage_root / "indicator_snapshots"` from `__init__`
- Removed `persist_json(self.local_snapshots_dir / ...)` call from `import_snapshots()`

`import_snapshots()` now reads from MT5 Common Files and applies to RAM only — no local disk copy.

---

### Fase 1.6 — Replace persist_json with stdout in core_runtime.py
**File:** `apps/core_runtime.py`

- Removed `from heuristic_mt5_bridge.infra.storage.json_files import persist_json`
- Added `import json`
- `--dry-run-config` mode now prints config payload to stdout via `print(json.dumps(payload, indent=2))`
- Error handler simplified to `except MT5ConnectorError: return 1`

---

### Fase 1.7 — Remove hardcoded pip_size
**File:** `src/heuristic_mt5_bridge/core/runtime/market_state.py`

- Removed `instrument_scale_for_symbol()` function entirely
- Removed `pip_size_for_symbol()` function entirely
- Changed `build_chart_context()` signature: added `*, pip_size: float | None = None` kwarg
- Distance fields (`distance_to_session_high_pips`, etc.) now return `None` when `pip_size is None` (was `0.0`)

`pip_size` wiring from broker spec data is deferred to Fase 3 (Control Plane / ChartWorker wiring).

---

### Fase 2.3 — Pass broker_identity to upserts
**File:** `src/heuristic_mt5_bridge/core/runtime/service.py`

- Added `purge_stale_broker_data` to runtime_db imports
- `_persist_market_state_checkpoint()` now reads `broker_server`/`account_login` from `self.broker_identity` and passes them to `upsert_market_state_cache()`
- `bootstrap()` calls `purge_stale_broker_data(db_path, broker_server, account_login)` immediately after acquiring `broker_identity`

---

### Tests — runtime_db + runtime_service
**File:** `tests/infra/test_runtime_db.py`

- Added `purge_stale_broker_data` to imports
- Updated `upsert_market_state_cache` call: removed feed data params, added `broker_server="Broker-1"` / `account_login=123456`
- Added `test_purge_stale_broker_data_removes_other_broker_rows`: inserts rows for two broker identities, purges one, asserts only the kept identity remains

**File:** `tests/core/test_runtime_service.py`

- Removed `live_publish_seconds=1.0` from `_build_config()` (field no longer exists)
- Removed `"bid": 1.1008, "ask": 1.101` from `FakeConnector.fetch_symbol_specification()` return dict
- `test_bootstrap_persists_runtime_and_uses_env_subscriptions`: replaced file-based assertions (`live_path.exists()`, JSON parse) with direct service state assertions:
  - `service.broker_identity["account_login"] == 123456`
  - `service.subscribed_universe == ["EURUSD", "GBPUSD"]`
  - `service.chart_registry.worker_count() == 2`
  - `service.health["status"] == "up"`

**Pre-existing flaky test fixed:**
- `tests/infra/test_session_gate.py`: the test used `{"trade_sessions": {"1": [...]}}` (Monday sessions only) but called `evaluate_symbol_session_gate()` without a fixed `now_utc`, causing failure on any day except Monday.
- Fix: added `now_utc: datetime | None = None` parameter to `evaluate_symbol_session_gate()` in `src/heuristic_mt5_bridge/infra/sessions/gate.py` and passed it through to `is_trade_open_from_registry()`; pinned the test to `datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc)` (a known Monday).

---

## Verification

```
$ .\.venv\Scripts\python.exe -m pytest tests/ -x -q
15 passed in 1.98s

$ .\.venv\Scripts\python.exe apps/core_runtime.py --dry-run-config
{
  "status": "dry_run",
  "storage_root": "...\storage",
  "runtime_db_path": "...\storage\runtime.db",
  "bootstrap_symbols": ["BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "VIX", "USDOLLAR"],
  "watch_timeframes": ["M5", "H1", "H4", "D1"],
  "sessions_enabled": true,
  "indicator_enabled": true,
  "market_state_checkpoint_seconds": 30.0,
  "updated_at": "2026-03-24T02:44:00Z"
}

$ Test-Path "...\storage\live"
False
```

---

## Architectural Invariants Enforced

| Rule | Status |
|------|--------|
| `storage/live/` directory must not exist | ✅ Directory absent |
| `core_runtime.json` must not be written at runtime | ✅ File never created |
| `bid`/`ask` must not appear in SQLite | ✅ Columns removed from both tables |
| `market_state_cache` partitioned by broker identity | ✅ PK = `(broker_server, account_login, symbol, timeframe)` |
| `symbol_spec_cache` partitioned by broker identity | ✅ PK = `(broker_server, account_login, symbol)` |
| Stale broker rows purged on bootstrap | ✅ `purge_stale_broker_data()` called in `bootstrap()` |
| No hardcoded `pip_size` per symbol | ✅ `pip_size_for_symbol()` removed; param is `None` until wired |
| Indicator snapshots: no local disk copy | ✅ `persist_json` call removed from `import_snapshots()` |

---

## Pending (Fase 3+)

- **pip_size wiring**: `build_chart_context(pip_size=...)` accepts the param but callers currently pass `None`. Wiring from `symbol_spec_cache.point` data is deferred to ChartWorker integration in Fase 3.
- **Control Plane HTTP API** (F-01): FastAPI endpoint exposing `build_live_state()` — not yet implemented.
- **BrokerSessionsService Python receiver** (F-06): MQL5 `.ex5` binaries are now in `mql5/`; Python TCP receiver on port 5561 is operational but installation docs are not yet written.
