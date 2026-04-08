# PROMPT: Fast Desk Constructor (v2 — current architecture)

> **Context**: This prompt is self-contained. Read it completely before writing
> any code. The codebase is `heuristic-metatrader5-bridge`. The SMC desk
> migration is complete and serves as the canonical reference pattern.

---

## Role

You are a senior trading systems engineer implementing the **Fast Desk** inside
`heuristic-metatrader5-bridge`. This desk has no LLM in the critical path.
It detects high-confidence setups from live market data and manages its own
positions through account-protection-first policies.

---

## Non-negotiable principles

1. **No LLM** — not even optional/behind a flag in the hot path.
2. **No global slow queue** — each symbol has its own independent custody cycle.
3. **Priority order**: protect account → protect open profit → cut losses →
   execute signal → explain later.
4. **No module-level config** — all configuration via explicit dataclass params,
   loaded from env at bootstrap.
5. **Broker-partitioned tables** — every DB table has composite PK
   `(broker_server, account_login, ...)`.
6. **`spec_registry.pip_size(symbol)`** replaces any legacy
   `instrument_scale_for_symbol()` calls.

---

## Current repo state (read before implementing)

### Key existing files

| File | Purpose |
|------|---------|
| `src/heuristic_mt5_bridge/core/runtime/service.py` | `CoreRuntimeService` — the runtime host |
| `src/heuristic_mt5_bridge/core/runtime/market_state.py` | `MarketStateService` — live candles in RAM |
| `src/heuristic_mt5_bridge/core/runtime/spec_registry.py` | `SymbolSpecRegistry` — `pip_size(symbol)` |
| `src/heuristic_mt5_bridge/infra/storage/runtime_db.py` | SQLite CRUD layer |
| `src/heuristic_mt5_bridge/infra/mt5/connector.py` | `MT5Connector` — order placement |
| `src/heuristic_mt5_bridge/smc_desk/runtime.py` | **CANONICAL PATTERN** — copy this wiring style |

### CoreRuntimeService integration contract

`CoreRuntimeService` (in `service.py`) exposes:

```python
# Attach a desk — called before run_forever()
def attach_smc_desk(self, desk: Any) -> None: ...

# run_forever() launches attached desks inside a TaskGroup:
if self._smc_desk is not None:
    tg.create_task(
        self._smc_desk.run_forever(
            self.market_state,        # MarketStateService
            str(self.broker_identity.get("broker_server", "")),
            int(self.broker_identity.get("account_login", 0) or 0),
            self.spec_registry,       # SymbolSpecRegistry
        ),
        name="smc_desk",
    )
```

You must add `attach_fast_desk()` and wire it the same way.
The `account_payload` field on the service carries the live account + positions
dict (refreshed every 2s via `_refresh_account_state()`).

### MarketStateService key API

```python
svc.market_state.get_candles(symbol, timeframe, bars=200) -> list[dict]
svc.market_state.build_chart_context(symbol, timeframe)   -> dict | None
svc.market_state.subscribed_symbols()                     -> list[str]
```

### MT5Connector key API for order execution

```python
connector.place_order(
    symbol, side, volume, entry_type,
    price=None, stop_loss=None, take_profit=None, comment=""
) -> dict   # raises MT5ConnectorError on failure

connector.modify_position(ticket, stop_loss=None, take_profit=None) -> dict
connector.close_position(ticket) -> dict
```

### Existing fast_desk folder skeleton (all stubs — implement these)

```
src/heuristic_mt5_bridge/fast_desk/
    __init__.py
    signals/         __init__.py   ← signal detection
    risk/            __init__.py   ← lot-size + drawdown
    policies/        __init__.py   ← entry/exit rules
    custody/         __init__.py   ← per-symbol position tracking
    state/           __init__.py   ← internal state (last signal, last action)
    workers/         __init__.py   ← per-symbol async worker
    execution/       __init__.py   ← MT5 order submission wrapper
```

---

## Data flow

```
CoreRuntimeService.market_state (RAM, updated every MT5_POLL_SECONDS)
    │
    ▼
FastDeskScanner  (signals/)
  scan_symbol(symbol, candles, spec) → FastSignal | None
    │
    ▼
FastRiskEngine   (risk/)
  calculate_lot_size(balance, risk_pct, sl_pips, pip_value) → float
  check_drawdown(account_state, config) → bool
    │
    ▼
FastPolicyEngine (policies/)
  can_open(symbol, side, open_positions, config) → bool
    │
    ▼
FastCustodian    (custody/)
  update(symbol, position, market_price, config) → CustodyAction | None
  CustodyAction: CLOSE | TRAIL_SL | TAKE_PARTIAL | HOLD
    │
    ▼
FastExecutionBridge (execution/)
  submit(connector, action) → dict    # wraps MT5Connector calls
    │
    ▼
runtime_db  (fast_desk_signals table, fast_desk_trade_log table)
```

---

## Files to implement

### 1. `signals/scanner.py`

```python
@dataclass
class FastSignal:
    symbol: str
    side: Literal["buy", "sell"]
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_loss_pips: float
    confidence: float          # 0.0–1.0
    trigger: str               # e.g. "momentum_breakout", "mean_reversion"
    evidence: dict[str, Any]
    generated_at: str          # UTC ISO

@dataclass
class FastScannerConfig:
    min_confidence: float = 0.65
    momentum_window: int = 14       # bars for momentum calc
    volume_multiplier: float = 1.5  # volume spike threshold
    atr_multiplier_sl: float = 1.5  # SL = ATR * multiplier
    rr_ratio: float = 2.0           # TP = entry ± SL_distance * rr_ratio

class FastScannerService:
    def scan_symbol(
        self, symbol: str, candles: list[dict], pip_size: float
    ) -> FastSignal | None: ...
```

Detection logic (implement all three, combine for confidence):
- **Momentum**: close crosses above/below `n`-bar EMA with expanding volume
- **Volume spike**: current volume > `volume_multiplier × mean(last 20 bars volume)`
- **Spread/ATR filter**: skip signal if ATR < `2 × pip_size` (choppy market)

### 2. `risk/engine.py`

```python
@dataclass
class FastRiskConfig:
    risk_per_trade_percent: float = 1.0    # max 2.0
    max_drawdown_percent: float = 5.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 4

class FastRiskEngine:
    def calculate_lot_size(
        self, balance: float, risk_pct: float, sl_pips: float,
        pip_value: float
    ) -> float: ...

    def check_account_safe(
        self, account_state: dict, config: FastRiskConfig
    ) -> bool: ...
    # returns False if drawdown > max_drawdown_percent
```

### 3. `policies/entry.py`

```python
class FastEntryPolicy:
    def can_open(
        self,
        symbol: str,
        side: str,
        open_positions: list[dict],  # from account_payload["positions"]
        config: FastRiskConfig,
    ) -> tuple[bool, str]: ...
    # returns (allowed, reason)
    # Reject if: same symbol + same side already open, total > max_positions_total
```

### 4. `custody/custodian.py`

```python
from enum import Enum

class CustodyAction(str, Enum):
    HOLD         = "hold"
    TRAIL_SL     = "trail_sl"
    TAKE_PARTIAL = "take_partial"
    CLOSE        = "close"

@dataclass
class CustodyDecision:
    action: CustodyAction
    position_id: int
    new_sl: float | None = None
    partial_volume: float | None = None
    reason: str = ""

class FastCustodian:
    """Evaluates each open position each custody cycle."""

    def evaluate(
        self,
        position: dict,        # from account_payload["positions"]
        current_price: float,
        pip_size: float,
        config: FastRiskConfig,
    ) -> CustodyDecision: ...
```

Custody rules (deterministic, no LLM):
- If floating profit ≥ `2 × risk_distance_pips`: trail SL to breakeven + 1 pip
- If floating profit ≥ `3 × risk_distance_pips`: trail SL to lock 50% of profit
- If floating loss > `1.2 × original_risk_pips` (slippage exceeded): CLOSE
- Otherwise: HOLD

### 5. `execution/bridge.py`

```python
class FastExecutionBridge:
    def open_position(
        self, connector: Any, signal: FastSignal, volume: float
    ) -> dict: ...

    def apply_custody(
        self, connector: Any, decision: CustodyDecision
    ) -> dict: ...
```

### 6. `state/desk_state.py`

```python
@dataclass
class SymbolDeskState:
    last_signal: FastSignal | None = None
    last_signal_at: float = 0.0          # monotonic
    last_custody_at: float = 0.0
    positions_opened_today: int = 0
    positions_closed_today: int = 0

class FastDeskState:
    """In-memory per-symbol state. Not persisted."""
    def get(self, symbol: str) -> SymbolDeskState: ...
    def set(self, symbol: str, state: SymbolDeskState) -> None: ...
```

### 7. `workers/symbol_worker.py`

```python
@dataclass
class FastWorkerConfig:
    scan_interval: float = 5.0       # seconds between scan cycles
    custody_interval: float = 2.0    # seconds between custody evaluations
    signal_cooldown: float = 60.0    # seconds before same symbol re-signals

class FastSymbolWorker:
    """Per-symbol async worker. One per subscribed symbol."""
    async def run(
        self,
        symbol: str,
        market_state: MarketStateService,
        account_payload_ref: Callable[[], dict],  # returns live account_payload
        connector: Any,
        spec_registry: SymbolSpecRegistry,
        db_path: Path,
        broker_server: str,
        account_login: int,
        config: FastWorkerConfig,
        risk_config: FastRiskConfig,
        scanner_config: FastScannerConfig,
    ) -> None: ...
```

Worker loop (every `scan_interval` seconds):
1. Get candles from `market_state.get_candles(symbol, "M5", 100)`
2. Run `FastScannerService.scan_symbol()` → `FastSignal | None`
3. If signal and `signal_cooldown` elapsed: check policy → check risk → open position
4. Every `custody_interval`: evaluate all open positions for this symbol via `FastCustodian`
5. Persist signal to `fast_desk_signals` table

### 8. `runtime.py` (desk orchestrator)

```python
@dataclass
class FastDeskConfig:
    scan_interval: float = 5.0
    custody_interval: float = 2.0
    signal_cooldown: float = 60.0
    risk_per_trade_percent: float = 1.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 4
    min_signal_confidence: float = 0.65
    atr_multiplier_sl: float = 1.5
    rr_ratio: float = 2.0

    @classmethod
    def from_env(cls) -> FastDeskConfig: ...

class FastDeskService:
    async def run_forever(
        self,
        market_state: MarketStateService,
        broker_server: str,
        account_login: int,
        spec_registry: SymbolSpecRegistry,
        connector: Any,                  # MT5Connector
        account_payload_ref: Callable[[], dict],
    ) -> None: ...

def create_fast_desk_service(db_path: Path) -> FastDeskService: ...
```

Note: `FastDeskService.run_forever()` takes `connector` and `account_payload_ref` in
addition to the SMC pattern, because it needs direct MT5 access to place orders.
`account_payload_ref` is a zero-arg callable returning `service.account_payload`.

---

## CoreRuntimeService changes (service.py)

### Add field

```python
self._fast_desk: Any = None  # Optional[FastDeskService]
```

### Add method

```python
def attach_fast_desk(self, desk: Any) -> None:
    self._fast_desk = desk
```

### In run_forever() TaskGroup, after smc_desk block

```python
if self._fast_desk is not None:
    tg.create_task(
        self._fast_desk.run_forever(
            self.market_state,
            str(self.broker_identity.get("broker_server", "")),
            int(self.broker_identity.get("account_login", 0) or 0),
            self.spec_registry,
            self.connector,
            lambda: self.account_payload,
        ),
        name="fast_desk",
    )
```

### In build_runtime_service()

```python
fast_enabled = os.getenv("FAST_DESK_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
if fast_enabled:
    from heuristic_mt5_bridge.fast_desk.runtime import create_fast_desk_service
    fast_desk = create_fast_desk_service(config.runtime_db_path)
    service.attach_fast_desk(fast_desk)
```

---

## DB tables to add (runtime_db.py)

```sql
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
);

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
);
```

CRUD functions to add:
- `upsert_fast_signal(db_path, broker_server, account_login, signal: dict) -> None`
- `load_recent_fast_signals(db_path, broker_server, account_login, symbol, limit=50) -> list[dict]`
- `append_fast_trade_log(db_path, broker_server, account_login, entry: dict) -> None`

---

## New env vars

```ini
FAST_DESK_ENABLED=false
FAST_DESK_SCAN_INTERVAL=5
FAST_DESK_CUSTODY_INTERVAL=2
FAST_DESK_SIGNAL_COOLDOWN=60
FAST_DESK_RISK_PERCENT=1.0
FAST_DESK_MAX_POSITIONS_PER_SYMBOL=1
FAST_DESK_MAX_POSITIONS_TOTAL=4
FAST_DESK_MIN_CONFIDENCE=0.65
FAST_DESK_ATR_MULTIPLIER_SL=1.5
FAST_DESK_RR_RATIO=2.0
```

---

## Tests to write (tests/fast_desk/test_fast_desk.py)

Minimum 12 tests covering:

1. `TestFastScanner` (4 tests)
   - Returns `None` on flat/choppy market (ATR too small)
   - Returns `FastSignal` on momentum breakout
   - Signal `side` matches breakout direction
   - Signal `confidence` is within [0, 1]

2. `TestFastRiskEngine` (3 tests)
   - `calculate_lot_size` returns correct volume given known inputs
   - `check_account_safe` returns `False` when drawdown exceeds max
   - `check_account_safe` returns `True` on healthy account

3. `TestFastEntryPolicy` (2 tests)
   - Rejects when same symbol + same side already open
   - Allows when total < max_positions_total

4. `TestFastCustodian` (3 tests)
   - Returns `TRAIL_SL` when profit ≥ 2× risk distance
   - Returns `CLOSE` when loss exceeds 1.2× risk distance
   - Returns `HOLD` under normal conditions

---

## apps/fast_desk_runtime.py (replace stub)

```python
"""Standalone entry: boots CoreRuntimeService + FastDeskService."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from heuristic_mt5_bridge.core.config.env import load_env_file, repo_root_from
from heuristic_mt5_bridge.core.runtime.service import build_runtime_service


async def _run() -> None:
    repo_root = Path(repo_root_from(__file__))
    os.environ.setdefault("FAST_DESK_ENABLED", "true")
    service = await build_runtime_service(repo_root)
    await service.bootstrap()
    await service.run_forever()


def main() -> int:
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Constraints summary

- Do NOT use `asyncio.to_thread` for custody or signal evaluation — these are
  pure Python, fast enough to run in the event loop directly.
- Do NOT add retries inside `FastExecutionBridge` — if MT5 rejects, log and
  move on. Retries belong to the next custody cycle.
- Do NOT share `FastDeskState` between workers — each `FastSymbolWorker` owns
  its own `SymbolDeskState` instance.
- All DB writes must go through the `runtime_db.py` CRUD layer, never raw SQL
  from worker code.

## Final output

After implementation:
1. All 12+ tests pass with `pytest tests/fast_desk/ -v`
2. `FAST_DESK_ENABLED=true python apps/fast_desk_runtime.py` boots without error
3. `git status` shows no untracked non-test files outside `fast_desk/` module

