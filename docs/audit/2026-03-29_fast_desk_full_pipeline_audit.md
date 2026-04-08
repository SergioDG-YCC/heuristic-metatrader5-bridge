# Fast Desk / Fast Trader — Full Pipeline Audit
**Date:** 2026-03-29  
**Scope:** `src/heuristic_mt5_bridge/fast_desk/` + `infra/sessions/` + `core/runtime/service.py`  
**Coverage:** 20 files read in full, ~25 grep passes for precise line citations

---

## A. `scan_and_execute` — 12-Stage Flow

| # | Stage | Function / Gate | File | Key Lines |
|---|-------|-----------------|------|-----------|
| 1 | Fetch M5 candles | `_fetch_candles(symbol, "M5")` | `trader/service.py` | ≈L115 |
| 2 | Account safety | `check_account_safe(account_info)` | `trader/service.py` → `risk/engine.py` | L128–L147 |
| 3 | Cooldown check | `last_signal_at + signal_cooldown > now` | `trader/service.py` | L26 (`signal_cooldown=60.0`) |
| 4 | Build context | `FastContextService.build(symbol, candles_m5, ...)` | `context/service.py` | L60–L220 |
| 5 | Hard gate | `if not context.allowed: return` | `trader/service.py` | L214 (`context/service.py`) |
| 6 | Phase filter for setups | `_setup_allowed_for_phase(phase, setup_type)` | `trader/service.py` | L85–L89 |
| 7 | Detect setups | `detect_setups(candles_m5, context, config)` | `setup/engine.py` | L59 |
| 8 | Fetch M1 candles | `_fetch_candles(symbol, "M1")` | `trader/service.py` | ≈L240 |
| 9 | Trigger confirmation | `FastTriggerEngine.confirm(setup, candles_m1, context)` | `trigger/engine.py` | L37 |
| 10 | Phase filter for triggers | `_trigger_allowed_for_phase(phase, trigger)` | `trader/service.py` | L94–L106 |
| 11 | Entry policy | `EntryPolicy.can_open(symbol, side, positions, config)` | `policies/entry.py` | L10 |
| 12 | Lot size + execution | `calculate_lot_size(...)` → `ExecutionBridge.send_entry(...)` | `risk/engine.py` L23 → `execution/bridge.py` L34 | — |

### Phase-constraint rules (`trader/service.py`)
- `_phase_is_constrained` (L82): classifies `ranging` and `compression` phases as constrained.
- `_setup_allowed_for_phase` (L85–89): in constrained phase only `{liquidity_sweep_reclaim, order_block_retest, sr_polarity_retest}` pass.
- `_trigger_allowed_for_phase` (L94–106): in constrained phase requires trigger in `_STRONG_TRIGGERS` **and** confidence ≥ 0.76 (ranging) or ≥ 0.74 (other constrained).

---

## B. `run_custody` — 15-Stage Flow

| # | Stage | Function / Gate | File | Key Lines |
|---|-------|-----------------|------|-----------|
| 1 | Filter non-fast explicit ownership | skip SMC-owned non-adopted rows | `trader/service.py` | ≈L554 |
| 2 | Build inherited set | `owner=fast && status=inherited_fast` | `trader/service.py` | ≈L561 |
| 3 | Adoption grace (DB + process memory) | `adopted_at` and fallback `inherited_first_seen_at` | `trader/service.py` + `state/desk_state.py` | ≈L568, L17 |
| 4 | Build context (re-use or fresh) | `FastContextService.build(...)` | `context/service.py` | L60 |
| 5 | Initial inherited protection | if inherited missing SL/TP => `adopted_initial_protection` | `trader/service.py` | ≈L619 |
| 6 | Grace hold for inherited | in grace window: no aggressive custody action | `trader/service.py` | ≈L662 |
| 7 | Hard cut | `action=="hard_cut"` → close position | `custody/engine.py` | L81 |
| 8 | Underwater passive check | `action=="no_passive_underwater"` → close | `custody/engine.py` | L90 |
| 9 | Scale-out | `action=="scale_out"` (if enabled, R ≥ 2.5) | `custody/engine.py` | L94 |
| 10 | Break-even | `action=="move_to_be"` (R ≥ 1.2) | `custody/engine.py` | L108 |
| 11 | ATR trail | `action=="trail_atr"` (R ≥ 1.8, if enabled) | `custody/engine.py` | L119 |
| 12 | Structural trail | `action=="trail_structural"` (R ≥ 2.2, if enabled) | `custody/engine.py` | L131 |
| 13 | Hold | `action=="hold"` — no mutation | `custody/engine.py` | default |
| 14 | Dispatch custody action | `ExecutionBridge.apply_professional_custody(...)` | `execution/bridge.py` | L160 |
| 15 | Pending evaluation + mutate | cancel/modify pending by policy | `pending/manager.py` | L32–L71 |

---

## C. Gates / Filters / Thresholds

| Gate | Type | Threshold / Condition | File | Lines |
|------|------|----------------------|------|-------|
| `symbol_closed` | HARD | broker reports market closed | `context/service.py` | L70 |
| `stale_feed` | HARD | last tick age ≥ `stale_feed_seconds` (default 180 s) | `context/service.py` | L71, L27 |
| `slippage_exceeded` | HARD | current slippage > `max_slippage_pct` × price (default 5%) | `context/service.py` | L71, L27 |
| `spread_exceeded` | HARD | spread > class threshold at `spread_tolerance` level | `context/service.py` | L72, L14 |
| `session_blocked` | HARD | current session not in `allowed_sessions` | `context/service.py` | L72, L27 |
| `context.allowed` aggregate | HARD | `not any(_reason_is_hard(r) for r in reasons)` | `context/service.py` | L214 |
| `check_account_safe` | HARD | drawdown = (balance−equity)/balance×100 ≤ `max_drawdown_percent` (5%) | `risk/engine.py` | L128–L147 |
| Signal cooldown | SOFT-BLOCK | `last_signal_at + signal_cooldown (60 s) > now` | `trader/service.py` | L26 |
| Phase-constrained setup filter | SOFT-BLOCK | only 3 setup types pass in ranging/compression | `trader/service.py` | L85–L89 |
| Phase-constrained trigger filter | SOFT-BLOCK | must be strong trigger + conf ≥ 0.74–0.76 | `trader/service.py` | L94–L106 |
| PD-zone penalty | PENALTY | confidence × 0.7 if price on wrong side of premium/discount | `setup/engine.py` | L152–L156 |
| Bias-alignment penalty | PENALTY | confidence × 0.75 if counter-HTF-bias | `setup/engine.py` | L161–L163 |
| `min_confidence` | DISCARD | setup confidence < 0.55 after penalties | `setup/engine.py` | L17 |
| `min_rr` auto | DISCARD | RR < derived min_rr (`rr_ratio=3.0`) | `setup/engine.py` | L17–L33 |
| Volatility pre-filter | DISCARD | M1 volatility == `very_low` → no trigger | `trigger/engine.py` | L53 |
| Trigger stacking | DISCARD | needs ≥ 2 valid triggers **or** ≥ 1 strong trigger | `trigger/engine.py` | L66–L70 |
| Exhaustion high threshold | DISCARD | exhaustion_high active → trigger conf must be ≥ 0.82 | `trigger/engine.py` | L80 |
| Same symbol+side open | BLOCK | position already open on same symbol & direction | `policies/entry.py` | L37 |
| `max_positions_per_symbol` | BLOCK | symbol count ≥ 1 (default) | `policies/entry.py` | L44 |
| `max_positions_total` | BLOCK | total open ≥ 4 (default) | `policies/entry.py` | L49 |
| Directional concentration | BLOCK | ≥ 70% same direction with ≥ 3 positions | `policies/entry.py` | L55, L67 |
| Margin safety | BLOCK | required margin > free_margin × 0.5 | `risk/engine.py` | ≈L125 |
| Effective risk cap | CAP | risk per trade capped at 2.0% even if configured higher | `risk/engine.py` | L97 |
| Lot size clamp | CAP | `max(0.01, min(max_lot_size=10.0, computed_lot))` | `risk/engine.py` | L125 |

---

## D. Setup Types

| Setup | Base Confidence | Order Type | Key Detection | Discard Conditions |
|-------|-----------------|------------|---------------|-------------------|
| `order_block_retest` | 0.82 | LIMIT | M5 OB zone detected, price pulling back | bias penalty, PD-zone penalty, min_rr |
| `liquidity_sweep_reclaim` | 0.84 | MARKET/LIMIT | sweep of liquidity pool + reclaim of structure | same |
| `breakout_retest` | 0.79 | LIMIT | BOS / CHoCH confirmed, price retesting broken level | same |
| `wedge_retest` | 0.69 | LIMIT | converging trendlines, retest of wedge boundary | same |
| `flag_retest` | 0.66 | LIMIT | impulse + consolidation channel, retest | same |
| `triangle_retest` | 0.64 | LIMIT | symmetrical/ascending/descending triangle, retest | same |
| `sr_polarity_retest` | 0.68 | LIMIT | classic S/R polarity flip retest | same |

Sources: `setup/engine.py` L263 (ob), L321 (sweep), L399 (breakout), L486 (wedge), L547 (flag), L604 (triangle), L640 (sr_polarity).

**Detection pipeline** (`setup/engine.py` L59):
1. Raw detect → filter by `min_confidence`
2. Apply PD-zone penalty (×0.7)
3. Apply bias-alignment penalty (×0.75)
4. Re-filter by `min_confidence`
5. Apply spread adjustment
6. Filter by computed `min_rr`
7. Sort descending by confidence

---

## E. Trigger Types

| Trigger | Strong? | Base Confidence | Stacking Weight |
|---------|---------|-----------------|-----------------|
| `micro_bos` | YES | 0.86 | Counts as 1 strong |
| `displacement` | YES | 0.81 | Counts as 1 strong |
| `reclaim` | YES | 0.74 | Counts as 1 strong |
| `micro_choch` | no | 0.79 | Counts as 1 weak |
| `rejection_candle` | no | 0.72 | Counts as 1 weak |

`_STRONG_TRIGGERS = {"micro_bos", "displacement", "reclaim"}` — `trigger/engine.py` L28  
Stacking rule (L66–70): `len(valid) >= 2 OR any(t in _STRONG_TRIGGERS for t in valid)`  
> **Note (debt #7):** comment at L66 says "1 strong + displacement" but implementation accepts any single strong trigger.

`displacement_body_factor=1.8` — `trigger/engine.py` L16  
Confidence sources: `micro_bos` L92/94, `micro_choch` L107/109, `rejection_candle` L125/127, `reclaim` L138/140, `displacement` L154.

---

## F. Custody Decision Ladder

| Priority | Action | Trigger Condition | R-Multiple | Config Key | Lines |
|----------|--------|-------------------|-----------|------------|-------|
| 1 (highest) | `hard_cut` | position floating loss exceeds hard_cut_r | −1.25 R | `hard_cut_r=1.25` | `custody/engine.py` L81 |
| 2 | `no_passive_underwater` | loss > 0.55R and H1 bias opposite to position side | — | — | L90 |
| 3 | `scale_out` | floating profit ≥ scale_out_r (if enabled) | +2.5 R | `enable_scale_out=False`, `scale_out_r=2.5` | L94 |
| 4 | `move_to_be` | floating profit ≥ be_trigger_r | +1.2 R | `be_trigger_r=1.2` | L108 |
| 5 | `trail_atr` | floating profit ≥ atr_trigger_r (if enabled) | +1.8 R | `enable_atr_trailing=True`, `atr_trigger_r=1.8` | L119 |
| 6 | `trail_structural` | floating profit ≥ structural_trigger_r (if enabled) | +2.2 R | `enable_structural_trailing=True`, `structural_trigger_r=2.2` | L131 |
| 7 (lowest) | `hold` | none of the above | — | — | default |

Dispatch at `execution/bridge.py` L160–L200: `close`, `reduce`, `move_to_be`, `trail_atr`, `trail_structural`.

---

## G. What Fast Desk Does NOT Do

1. **No pyramiding / scale-in** — `enable_scale_out=False` by default; scaling in is entirely absent.
2. **No news/event blackout** — no economic calendar integration; sessions gate only covers broker schedule.
3. **No multi-symbol correlation filter** — directional concentration is per-side count only, not cross-symbol correlation.
4. **No trade journal / P&L persistence** — `SymbolDeskState` counters (`positions_opened_today`, `positions_closed_today`) exist in memory only, reset on restart.
5. **No M30/H1 timeframe candle fetch per scan cycle** — HTF bias comes solely from context build; no mid-cycle HTF check.
6. **No partial close** — `apply_professional_custody` dispatches `reduce` action only when `scale_out` fires (disabled by default); no other partial.

---

## H. Technical Debt / Inconsistencies

| # | Issue | Evidence | Risk |
|---|-------|----------|------|
| 1 | `FAST_TRADER_MAX_SLIPPAGE_POINTS` in env example but never read in source | `configs/base.env.example` L90; `trader/service.py` L35 uses `_execution_slippage_from_spec` instead | Low — misleads operator |
| 2 | Duplicate `FAST_TRADER_ADOPTION_GRACE_SECONDS` in env example | `configs/base.env.example` L100 **and** L101 | Low — cosmetic |
| 3 | `signals/scanner.py` is vestigial | `FastSignal`, `FastScannerConfig` defined at L43, L57 but pipeline ignores them; instantiated in `runtime.py` L274 as legacy param container only | Low — dead weight |
| 4 | `evaluate_symbol_session_gate` not wired to Fast Desk | Defined at `infra/sessions/gate.py` L76; only `is_trade_open_from_registry` called from `runtime.py` L441 | Medium — richer gate logic silently bypassed |
| 5 | Race condition on `SymbolDeskState` | `scan_loop` and `custody_loop` run concurrently via `asyncio.to_thread` on the same symbol, mutating shared state without locks; `desk_state.py` L9–16, `workers/symbol_worker.py` L96, L116 | High — in production with multiple symbols |
| 6 | State fields defined but unused in main flow | `last_signal`, `last_custody_at`, `touched_pending_orders` in `SymbolDeskState` (L10, L12, L16) | Low — dead code |
| 7 | Trigger stacking comment contradicts implementation | Comment L66: "1 strong + displacement"; code L67–70: any single strong trigger passes | Low — documentation confusion |

---

## I. Environment Variables

### Effective variables (read in source)

| Variable | Default | Read At | Purpose |
|----------|---------|---------|---------|
| `FAST_DESK_ENABLED` / `FAST_TRADER_ENABLED` | `false` | `core/runtime/service.py` L1064 | Master on/off switch |
| `FAST_TRADER_SYMBOLS` | — | `runtime.py` ≈L130 | Comma-separated symbol list |
| `FAST_TRADER_RISK_PER_TRADE` | `1.0` | `runtime.py` L131 | Risk % per trade |
| `FAST_TRADER_MAX_DRAWDOWN` | `5.0` | `runtime.py` L132 | Max drawdown % gate |
| `FAST_TRADER_MAX_POSITIONS_PER_SYMBOL` | `1` | `runtime.py` L133 | Per-symbol position cap |
| `FAST_TRADER_MAX_POSITIONS_TOTAL` | `4` | `runtime.py` L134 | Total position cap |
| `FAST_TRADER_MAX_LOT_SIZE` | `10.0` | `runtime.py` L136 | Lot size ceiling |
| `FAST_TRADER_MIN_RR` | auto | `runtime.py` L140 | Override auto min_rr |
| `FAST_TRADER_RR_RATIO` | `3.0` | `runtime.py` ≈L138 | Target R:R ratio (setup engine) |
| `FAST_TRADER_MIN_CONFIDENCE` | `0.55` | `runtime.py` ≈L139 | Minimum setup confidence |
| `FAST_TRADER_SIGNAL_COOLDOWN` | `60.0` | `runtime.py` ≈L125 | Seconds between signals per symbol |
| `FAST_TRADER_ENABLE_PENDING_ORDERS` | `true` | `runtime.py` ≈L126 | Enable limit/stop pending orders |
| `FAST_TRADER_ADOPTION_GRACE_SECONDS` | `120.0` | `runtime.py` ≈L127 | Grace before aggressive custody on inherited rows (initial SL/TP may still be applied) |
| `FAST_TRADER_PENDING_TTL` | `900` | `runtime.py` ≈L143 | Pending order TTL (seconds) |
| `FAST_TRADER_REPRICE_THRESHOLD_PIPS` | `8.0` | `runtime.py` ≈L144 | Reprice trigger (pips) |
| `FAST_TRADER_REPRICE_BUFFER_PIPS` | `1.0` | `runtime.py` ≈L145 | Reprice buffer (pips) |
| `FAST_TRADER_BE_TRIGGER_R` | `1.2` | `runtime.py` ≈L146 | Break-even R trigger |
| `FAST_TRADER_ATR_TRIGGER_R` | `1.8` | `runtime.py` ≈L147 | ATR trail R trigger |
| `FAST_TRADER_STRUCTURAL_TRIGGER_R` | `2.2` | `runtime.py` ≈L148 | Structural trail R trigger |
| `FAST_TRADER_HARD_CUT_R` | `1.25` | `runtime.py` ≈L149 | Hard cut defensive R |
| `FAST_TRADER_SPREAD_TOLERANCE` | `medium` | `runtime.py` ≈L120 | Spread gate level |
| `FAST_TRADER_ALLOWED_SESSIONS` | `london,overlap,new_york` | `runtime.py` ≈L121 | Sessions filter |

### Documented but NOT consumed in source

| Variable | File | Line | Issue |
|----------|------|------|-------|
| `FAST_TRADER_MAX_SLIPPAGE_POINTS` | `configs/base.env.example` | L90 | Slippage is auto-derived from symbol spec in code |

---

## J. Key Config Classes Summary

| Class | File | Notable Defaults |
|-------|------|------------------|
| `FastTraderConfig` | `trader/service.py` L26 | `signal_cooldown=60`, `enable_pending_orders=True`, `adoption_grace_seconds=120` |
| `FastContextConfig` | `context/service.py` L27 | `spread_tolerance="medium"`, `max_slippage_pct=0.05`, `stale_feed_seconds=180`, `allowed_sessions=("london","overlap","new_york")` |
| `FastSetupConfig` | `setup/engine.py` L17 | `rr_ratio=3.0`, `min_confidence=0.55` |
| `FastTriggerConfig` | `trigger/engine.py` L16 | `displacement_body_factor=1.8` |
| `FastRiskConfig` | `risk/engine.py` L9 | `risk_per_trade_percent=1.0`, `max_drawdown_percent=5.0`, `max_positions_per_symbol=1`, `max_positions_total=4`, `max_lot_size=10.0` |
| `FastCustodyPolicyConfig` | `custody/engine.py` L9 | `be_trigger_r=1.2`, `atr_trigger_r=1.8`, `structural_trigger_r=2.2`, `hard_cut_r=1.25`, `enable_atr_trailing=True`, `enable_structural_trailing=True`, `enable_scale_out=False`, `scale_out_r=2.5` |
| `FastPendingPolicyConfig` | `pending/manager.py` L12 | `pending_ttl_seconds=900`, `reprice_threshold_pips=8.0`, `reprice_buffer_pips=1.0` |

---

## K. Infrastructure Notes

### Session Registry (`infra/sessions/`)
- `registry.py`: thread-safe in-memory broker session data; `queue_bootstrap` (L54), `apply_incoming_sessions` (L75), `set_broker_clock` / `get_broker_gmt_offset` (L189, L198)
- `gate.py`: `evaluate_symbol_session_gate` (L76) — **defined but not called by Fast Desk pipeline**
- `service.py`: TCP server (L69) receiving EA schedule; `on_session_data` (L78), session apply (L98), heartbeat (L168)
- `runtime.py` L441–459: `_desired_symbols` calls `is_trade_open_from_registry` directly; fail-open if registry completely empty (L454); rejects with `no_session_data` (L452), `market_closed` (L446), `session_not_enabled` (L459)
- `fast_desk/runtime.py`: ownership rows can force worker start even when session gate rejects symbol; emitted reason `custody_forced`.
- `workers/symbol_worker.py`: transient custody symbols hydrate M1/M5/M30 in background and are removed from in-memory market state when no longer needed.

### MT5 Serialization (`core/runtime/service.py`)
- `_mt5_lock = asyncio.Lock()` (L173) — single lock for all MT5 operations across all symbols
- `_mt5_call` (L213) — serializes via lock
- `attach_fast_desk` (L688) — wires FastDeskService into CoreRuntimeService
- `build_runtime_service` (L1048) — reads feature flags (L1064), calls `create_fast_desk_service` (L1070)

### Execution Bridge (`execution/bridge.py`)
- `_call` (L18): routes through `mt5_execute_sync` (lock-serialized) when provided, else direct connector
- `send_entry` (L34): builds instruction with `execution_constraints.max_slippage_points` (L55), calls `send_execution_instruction` (L63)
- `apply_professional_custody` (L160): dispatches `close` (L175), `reduce` (L186), `move_to_be` / `trail_atr` / `trail_structural` (L200)
- Legacy methods `open_position` (L220) / `apply_custody` (L233): present but unused by current pipeline

### Execution Slippage Derivation (`trader/service.py` L35–52)
1. `trade_stops_level × 10%`, clamped to `[5, stops_level]`
2. Fallback: `spread × 3`
3. Ultimate fallback: `30 points`
