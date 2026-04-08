# PROMPT: Connector Execution Surface Constructor

## Recommended model

**Primary for implementation**: `gpt-5.3-codex`  
**Primary for architecture review**: `gpt-5.4`

## Role

You are closing the missing MT5 execution surface in
`heuristic-metatrader5-bridge`.

This is not a generic refactor.

This is a constrained backend closure task whose output must make the current
heuristic repo capable of:

- modifying live positions
- modifying pending orders
- removing pending orders
- closing positions fully and partially
- finding open positions by ownership tag when the broker allows it
- exposing explicit preflight failures when terminal trading is disabled

Do not redesign the whole runtime.

Do not import the old office stack.

Do not change the architectural principle that the `control plane` is the only
external interface.

## Canonical documents

Read these first and treat them as binding:

1. `docs/ARCHITECTURE.md`
2. `docs/plans/2026-03-24_immutable_bridge_action_plan.md`
3. `docs/plans/2026-03-24_connector_certification_plan.md`
4. `docs/audit/2026-03-24_mt5_official_surface_inventory.md`
5. `docs/audit/2026-03-24_connector_certification_execution_report.md`
6. `docs/audit/2026-03-24_live_bridge_audit.md`

## Old repo source of truth for migration

Use these only as source references, not as target architecture:

1. `../llm-metatrader5-bridge/python/mt5_connector.py`
2. `../llm-metatrader5-bridge/python/execution_bridge.py`
3. `../llm-metatrader5-bridge/python/live_execution_trader_runtime.py`

## Problem statement

Current state in the new repo:

- `src/heuristic_mt5_bridge/infra/mt5/connector.py` exposes:
  - `connect`
  - `shutdown`
  - `broker_identity`
  - `ensure_symbol`
  - `fetch_snapshot`
  - `fetch_symbol_specification`
  - `fetch_available_symbol_catalog`
  - `fetch_account_runtime`
  - `symbol_tick`
  - `login`
  - `probe_account`
  - `send_execution_instruction`
- it does **not** expose:
  - `modify_position_levels`
  - `modify_order_levels`
  - `remove_order`
  - `close_position`
  - `find_open_position_id`

As a result:

- Fast Desk custody is not closed end-to-end
- trailing from the new repo is not closed
- closes and cancellations from the new repo are not closed
- ownership-by-comment cannot even be attempted from the public surface

## Objective

Close the public MT5 execution surface in the new repo with exact, testable
behavior.

The result must satisfy the certification harness already present in:

- `tests/integration/mt5_connector_certification.py`

## Non-negotiable rules

### 1. Keep the current repo architecture

Do not add:

- chairman
- office queues
- cross-cutting trader runtimes from the old repo
- slow multi-stage execution orchestration

### 2. Do not change the canonical public surface

The required public methods are:

- `send_execution_instruction(instruction)`
- `modify_position_levels(symbol, position_id, stop_loss, take_profit)`
- `modify_order_levels(symbol, order_id, price_open, stop_loss, take_profit)`
- `remove_order(order_id)`
- `close_position(symbol, position_id, side, volume, max_slippage_points=20)`
- `find_open_position_id(symbol, comment)`

Do not replace these with alternative names.

### 3. Backward compatibility is allowed only as thin internal shims

If you need compatibility for current desk code, you may add thin wrappers like:

- `place_order(...)`
- `modify_position(...)`

But:

- they are optional
- they must delegate to the canonical methods above
- the canonical methods remain the primary contract

### 4. Explicit preflight safety is required

Before every MT5 write action, the connector must check terminal/account state
and fail explicitly if trading is not possible.

At minimum:

- inspect `mt5.terminal_info()`
- inspect `mt5.account_info()`
- if terminal trading is disabled, fail before `order_send`
- if account access is broken, fail before `order_send`

The error must be explicit and actionable.

### 5. Do not assume order comments are reliable

Certification already proved:

- some brokers in this environment accept execution with `comment=""`
- the same environment may reject populated comments with `Invalid "comment" argument`

Therefore:

- all execution methods must allow empty comment safely
- no write path may require a populated comment to function
- `find_open_position_id()` must work when comments are available
- but the connector must not make comments mandatory

### 6. Do not silently degrade account switching risks

Certification already proved:

- failed `probe_account()` can degrade the terminal session
- failed account auth can leave MT5 in a broken operational state

You are not implementing the full safe account-switch flow here.

But you must:

- document in code comments where necessary that `probe_account()` is risky
- avoid expanding the use of `probe_account()` internally
- keep all execution methods independent from account-probe side effects

## Required file scope

### Required code changes

1. `src/heuristic_mt5_bridge/infra/mt5/connector.py`

### Required integration changes

2. `src/heuristic_mt5_bridge/fast_desk/execution/bridge.py`

Only if needed to align with the canonical connector surface.

### Required test changes

3. `tests/infra/test_mt5_connector.py`

Add or extend unit coverage for the new public methods.

Do not remove the integration harness.

## Exact method behavior

### A. `modify_position_levels(...)`

Implementation:

- use `TRADE_ACTION_SLTP`
- resolve symbol through `ensure_symbol()`
- include `position`
- include `sl` only if positive number provided
- include `tp` only if positive number provided

Return payload:

- `retcode`
- `comment`
- `order`
- `deal`
- `position`
- `request`
- `ok`

Success retcodes:

- `TRADE_RETCODE_DONE`
- `TRADE_RETCODE_PLACED`
- `TRADE_RETCODE_DONE_PARTIAL`

### B. `modify_order_levels(...)`

Implementation:

- use `TRADE_ACTION_MODIFY`
- resolve symbol through `ensure_symbol()`
- include `order`
- include `price` only if positive number provided
- include `sl` only if positive number provided
- include `tp` only if positive number provided

Return payload:

- `retcode`
- `comment`
- `order`
- `deal`
- `request`
- `ok`

### C. `remove_order(order_id)`

Implementation:

- use `TRADE_ACTION_REMOVE`
- include `order`

Return payload:

- `retcode`
- `comment`
- `order`
- `deal`
- `request`
- `ok`

### D. `close_position(...)`

Implementation:

- close by opposite market deal
- resolve symbol through `ensure_symbol()`
- fetch tick through `symbol_tick()`
- side `buy` closes with sell
- side `sell` closes with buy
- include explicit `position`
- include requested `volume`
- use `max_slippage_points`
- use the same `magic_number`
- do not require non-empty comment

Return payload:

- `retcode`
- `comment`
- `order`
- `deal`
- `position`
- `request`
- `ok`

Must support:

- full close
- partial close

### E. `find_open_position_id(symbol, comment)`

Implementation:

- resolve symbol through `ensure_symbol()`
- call `positions_get(symbol=...)`
- exact string match on `comment`
- return `position_id` when found
- return `None` when not found or when comment is empty

Do not raise on comment-not-found.

## Preflight contract for all write methods

Add one internal helper in the connector, for example:

- `_ensure_trading_available()`

This helper must:

1. verify `account_info()` is not `None`
2. verify `terminal_info()` is not `None`
3. verify terminal trading is enabled
4. preserve current `ACCOUNT_MODE` guard semantics

Failure output must raise `MT5ConnectorError` with actionable text.

Required message content:

- mention if terminal trading is disabled
- mention if MT5 account/session is unavailable
- mention if `ACCOUNT_MODE=demo` blocks a real account

## Fast Desk integration rule

If you modify `fast_desk/execution/bridge.py`, the result must:

- stop depending on undefined methods
- use the canonical connector surface
- keep current intent:
  - open market position
  - close position
  - trail stop

Preferred mapping:

- open uses `send_execution_instruction(...)`
- trail uses `modify_position_levels(...)`
- close uses `close_position(...)`

## Unit tests required

Extend `tests/infra/test_mt5_connector.py` with fake MT5 coverage for:

1. `modify_position_levels()` builds `TRADE_ACTION_SLTP`
2. `modify_order_levels()` builds `TRADE_ACTION_MODIFY`
3. `remove_order()` builds `TRADE_ACTION_REMOVE`
4. `close_position()` builds opposite-side close request
5. `find_open_position_id()` finds exact comment match
6. preflight fails when terminal trading is disabled

Do not make the unit tests depend on a real MT5 terminal.

## Integration certification target

After implementation, this command must pass all relevant connector cases except
the already-known comment-tagging and disruptive account-probe caveats:

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --symbol EURUSD --timeframe M5 --allow-live-writes --allow-destructive --comment-mode empty --exclude connector.read.probe_invalid_account
```

Expected non-green cases after this task:

- none in the connector surface closure itself
- only environment-dependent comment-tagging limitations may remain outside the
  core closure scope

This command must continue to show the risky probe behavior as documented:

```powershell
.\.venv\Scripts\python.exe tests\integration\mt5_connector_certification.py --include connector.read.probe_invalid_account --symbol EURUSD --timeframe M5
```

## Acceptance criteria

1. The five missing public methods exist on `MT5Connector`.
2. Fast Desk no longer points at non-existent execution methods.
3. The connector fails explicitly when terminal trading is disabled.
4. Full close and partial close are both supported.
5. Pending order modification and removal are both supported.
6. The integration certification run passes the useful live path with
   `comment_mode=empty`.
7. No unrelated architectural refactor is introduced.

## Final output requirements

When finished, report:

1. files changed
2. exact method signatures added
3. exact tests added or updated
4. certification commands executed
5. residual risks that still remain after the closure

## Sequencing rule after this constructor

This constructor ends at connector surface closure and certification readiness.

Do not continue into risk, ownership, trader orchestration or WebUI in the same implementation pass.

Once this connector task is complete, the next implementation order is mandatory and is defined by the canonical plan:

1. `OwnershipRegistry` + inherited operation adoption
2. global and per-desk heuristic `RiskKernel`
3. `FastTraderService` real execution + custody
4. `SmcTraderService` real execution + ownership-aware operation flow
5. `BridgeSupervisor` multi-terminal / multi-account runtime
6. `paper` mode separation and UI hooks

Additional binding rules:

- The future `RiskKernel` must be heuristic, account-aware, desk-aware, and configurable by API.
- The future `FastTraderService` must depend only on the canonical connector surface, never on raw MT5 calls spread across desks.
- The future `SmcTraderService` must use the same execution surface and ownership model as Fast.
- WebUI work must not start as if backend ownership, risk and execution were already complete.
- If this constructor discovers missing backend contracts required by the next phases, it must report them explicitly instead of improvising a UI-first workaround.
