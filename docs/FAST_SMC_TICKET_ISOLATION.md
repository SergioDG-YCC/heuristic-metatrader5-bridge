# FAST / SMC Ticket Isolation

> **Status**: implemented and tested — 2026-04-07
> **Scope**: `core/runtime`, `core/ownership`, `fast_desk/trader`, `apps/control_plane`, `apps/webui`
> **Tests**: 16 new isolation tests + 28 regression tests → **44 passing**

---

## Problem statement

`CoreRuntimeService` builds a single global MT5 snapshot (all positions + orders). Before this fix, that global snapshot was injected identically into both FAST and SMC desks.

FAST then attempted to exclude SMC tickets by building `smc_pos_ids` / `smc_order_ids` sets — a blacklist approach. This design had two defects:

1. **Conceptually wrong**: FAST should never know that SMC tickets exist.
2. **Functionally broken**: `ownership_open_ref` already filtered FAST-only rows, so the blacklist was always empty and FAST processed all broker positions, including SMC pending orders, repricing their levels and corrupting SMC RR.

---

## Design: positive allowlist

Separation is enforced **upstream**, before any desk logic runs.

```text
MT5 global snapshot
  │
  ├── account_payload_for_desk(desk="fast")
  │     includes: desk_owner=="fast"  OR  ownership_status in {"fast_owned","inherited_fast"}
  │     excludes: everything else (smc_owned, unassigned pending first reconcile)
  │
  └── account_payload_for_desk(desk="smc")
        includes: desk_owner=="smc"   OR  ownership_status=="smc_owned"
        excludes: everything else
```

No desk receives, sees, or iterates tickets outside its allowlist.

---

## Ticket taxonomy

| `ownership_status` | `desk_owner` | Origin |
|---|---|---|
| `fast_owned` | `fast` | Placed by FAST trader |
| `smc_owned` | `smc` | Placed by SMC trader |
| `inherited_fast` | `fast` | External / manual — not placed by either desk |
| `unassigned` | `unassigned` | Unknown — first reconcile pending |

> **Critical**: `inherited_fast` = external to the stack (e.g. human-opened position). SMC tickets are **never** classified as `inherited_fast` — they have their own `smc_owned` row and are found by `get_by_position_id` before the adoption branch runs.

---

## Code changes

### `src/heuristic_mt5_bridge/core/runtime/service.py`

Two new methods on `CoreRuntimeService`:

```python
def ownership_visible_ids_for_desk(self, *, desk: str) -> dict[str, set[int]]:
    """Returns {position_id: set, order_id: set} visible to the given desk."""

def account_payload_for_desk(self, *, desk: str) -> dict[str, Any]:
    """Returns a filtered copy of account_payload containing only the desk's tickets."""
```

`run_forever()` changed to inject desk-scoped payloads:

```python
# Before
fast_desk.attach(..., account_payload_ref=lambda: self.account_payload, ...)
smc_desk.attach(...,  account_payload_ref=lambda: self.account_payload, ...)

# After
fast_desk.attach(..., account_payload_ref=lambda: self.account_payload_for_desk(desk="fast"), ...)
smc_desk.attach(...,  account_payload_ref=lambda: self.account_payload_for_desk(desk="smc"),  ...)
```

`CoreRuntimeConfig.load()`: added legacy env alias so `OWNERSHIP_AUTO_ADOPT_FOREIGN=true` in existing `.env` files is honoured (falls back to canonical `RISK_ADOPT_FOREIGN_POSITIONS`).

---

### `src/heuristic_mt5_bridge/fast_desk/trader/service.py`

**Removed** from `run_custody()`:
- `smc_pos_ids: set[int] = set()`
- `smc_order_ids: set[int] = set()`
- Entire `if owner == "smc":` block building the blacklists
- `if position_id in smc_pos_ids: continue`
- `if order_id in smc_order_ids: continue`

**Added** contract defence:

```python
# Any row with desk_owner != "fast" is a contract violation — log and skip.
if owner != "fast":
    logger.warning(
        "unexpected non-visible ticket in fast ownership ref: "
        "owner=%s status=%s pos_id=%s ord_id=%s — skipping",
        owner, status, pos_id or None, ord_id or None,
    )
    continue
```

A legitimate `inherited_fast` row always has `desk_owner="fast"`. A row with `desk_owner="smc"` is invalid regardless of its `ownership_status`.

---

### `src/heuristic_mt5_bridge/core/ownership/registry.py`

Added clarifying comments in `reconcile_from_caches()` (both position and order adoption branches):

```python
# ``inherited_fast`` means: ticket external to the stack (e.g. opened
# manually by a human trader).  Tickets created by the SMC desk are
# never reclassified as ``inherited_fast`` — they have their own
# ``smc_owned`` row and are found by get_by_position_id above.
```

Existing guard preserved: `reassign()` raises `ValueError("reassigning from smc to fast is not allowed")`.

---

### `apps/control_plane.py`

Two new endpoints:

```python
GET /api/v1/fast/operations
  → {"positions": [...], "orders": [...], "updated_at": "..."}
  # Only fast_owned / inherited_fast tickets

GET /api/v1/smc/operations
  → {"positions": [...], "orders": [...], "updated_at": "..."}
  # Only smc_owned tickets
```

`GET /positions` retained as global broker view for audit consoles.

---

### `apps/webui/src/` — desk-scoped stores and routes

| File | Change |
|---|---|
| `src/api/client.ts` | Added `fastOperations()` / `smcOperations()` methods |
| `src/stores/fastOperationsStore.ts` | **New** — polls `/api/v1/fast/operations` every 3 s |
| `src/stores/smcOperationsStore.ts` | **New** — polls `/api/v1/smc/operations` every 3 s |
| `src/routes/FastDesk.tsx` | Uses `fastOperationsStore.positions` — no longer reads from global `operationsStore` |
| `src/routes/SmcDesk.tsx` | Uses `smcOperationsStore.positions` — no longer reads from global `operationsStore` |

---

## Tests

### New files

| File | Tests | What it verifies |
|---|---|---|
| `tests/core/test_desk_payload_isolation.py` | 7 | `account_payload_for_desk` filters correctly: smc_owned absent from FAST, fast_owned/inherited_fast absent from SMC, mixed partitioning, account state passthrough |
| `tests/core/test_ownership_isolation.py` | 6 | Manual ticket adopted as `inherited_fast`; SMC ticket not re-adopted by `reconcile`; `reassign(smc→fast)` blocked; order adoption; no-adopt flag |
| `tests/fast_desk/test_fast_custody_isolation.py` | 3 | Custody only touches payload positions; contract defence warning on unexpected ownership row; `inherited_fast` position receives custody |

### Modified

| File | Tests | What changed |
|---|---|---|
| `tests/fast_desk/test_fast_trader_service_flow.py` | 1 updated | `test_custody_ignores_non_fast_positions` — now uses desk-scoped payload (only FAST position), SMC ownership rows remain to test contract defence warning |

---

## Regression baseline

```
44 passed in 10.80s
```

Files covered: `test_desk_payload_isolation.py`, `test_ownership_isolation.py`,
`test_fast_custody_isolation.py`, `test_ownership_registry.py`,
`test_runtime_service.py`, `test_fast_trader_service_flow.py`.

---

## Residual risks (acknowledged)

| Risk | Mitigation |
|---|---|
| Bootstrap race: first reconcile hasn't run yet, ownership_registry is empty | `account_payload_for_desk` falls back to global payload when `ownership_registry is None` — safe degraded mode |
| SMC tickets with concurrent MT5 closure + FAST first-seen | `get_by_position_id` finds the `smc_owned` row before adoption branch — reclassification is blocked |
| `fastDeskRuntime._forced_custody_symbols` uses `ownership_open_ref` directly | Already correct — `ownership_open_ref` for FAST was already filtered before this PR; now doubly safe |
