# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [SemVer](https://semver.org/).

---

## [Unreleased]

### Added — Correlation engine, desk wiring & WebUI heatmap (2026-04-05)

Full cross-symbol Pearson correlation engine integrated end-to-end: core service, desk policies, HTTP endpoints, and WebUI visualization.

#### Core correlation engine (`core/correlation/`)

- **`service.py`** — `CorrelationService`: background loop refreshes all `(symbol_a × symbol_b × timeframe)` matrices every `CORRELATION_REFRESH_SECONDS` (default 60 s). Uses `MarketStateService.get_candles()` as the only data source — pure RAM, no disk. Prints `[correlation] M5 pairs=N coverage_ok=N stale=N elapsed=Xs` every cycle. `get_matrix(tf)`, `get_pair(a, b, tf)`, `get_exposure_relations(symbol, tf)`, `active_symbols()` public API.
- **`models.py`** — `CorrelationMatrixSnapshot` (timestamp, timeframe, N×M pair list, `all_pairs_coverage_ok`, `compute_stale`). `CorrelationPairValue` carries `symbol_a`, `symbol_b`, `correlation`, `coverage_bars`, `n_aligned`, `source_stale`.
- **`aligner.py`** — `align_and_returns(candles_a, candles_b)`: inner join by ISO epoch, computes simple or log returns, returns `AlignmentResult(returns_a, returns_b, n_aligned, coverage_ratio)`. Requires ≥ `CORRELATION_MIN_COVERAGE_BARS` (default 30) aligned bars.
- Pure Python `_pearson()` implementation — clamped to `[−1, 1]`, returns `None` on zero variance or insufficient data.
- `CoreRuntimeService.correlation_service` created at startup when `CORRELATION_ENABLED=true`, lifecycle managed via `run_forever()`.

#### HTTP endpoints

- `GET /api/v1/correlation/{tf}` — full N×N matrix as `{pairs: [...], symbols: [...], timeframe, computed_at}`. Returns HTTP 503 when `CORRELATION_ENABLED=false`.
- `GET /api/v1/correlation/{tf}/{symbol_a}/{symbol_b}` — single pair value with staleness flag.

#### Fast Desk — correlation policy (`fast_desk/correlation/policy.py`)

- **`FastCorrelationPolicy`**: two risk detectors applied before entry (`timeframe="M5"`, threshold 0.80):
  - **Implicit hedge** — existing position on `symbol_b` with opposite side while `corr(a,b) > threshold` → blocks entry.
  - **Inverse concentration** — existing position on `symbol_b` with same side while `corr(a,b) < −threshold` → blocks entry.
- `check_entry_conflict(symbol, side, open_positions)` → `(blocked: bool, reason: str | None)` injected into `FastContext.warnings`.
- `build_details(symbol)` → dict enriching `FastContext.details["correlation"]`.
- Wired to `FastContextService(context_config, correlation_policy=policy)` (param already existed; now receives a live policy instance).

#### SMC Desk — correlation formatter (`smc_desk/correlation/formatter.py`)

- **`SmcCorrelationFormatter`**: `timeframe="H1"`, `top_n=5` highest-magnitude pairs.
- `build_context_dict(symbol)` → structured dict injected into `analyst_input["correlation_context"]`.
- `build_context_snippet(symbol)` → plain-text block for LLM system prompt.
- Wired to `run_smc_heuristic_analyst(..., correlation_formatter=formatter)` (param already existed; now receives a live formatter instance).

#### Desk wiring (`core/runtime/service.py` + 4 desk files)

Five files modified to thread `CorrelationService` from `CoreRuntimeService` down to each consuming component:

| File | Change |
|---|---|
| `fast_desk/workers/symbol_worker.py` | `run()` accepts `correlation_policy`, forwards to `FastTraderService` |
| `fast_desk/trader/service.py` | `__init__` accepts `correlation_policy`, passes to `FastContextService` |
| `fast_desk/runtime.py` | `FastDeskService` stores `_correlation_policy`; `create_fast_desk_service(db_path, correlation_service=None)` builds `FastCorrelationPolicy(svc, "M5")` when enabled |
| `smc_desk/runtime.py` | `SmcDeskService` stores `_correlation_formatter`; `create_smc_desk_service(db_path, correlation_service=None)` builds `SmcCorrelationFormatter(svc, "H1", top_n=5)` when enabled |
| `core/runtime/service.py` | Both factory calls receive `correlation_service=service.correlation_service` |

Both desk factories use `Optional` pattern — when `CORRELATION_ENABLED=false` all references stay `None` and all downstream code is a no-op.

#### WebUI — Correlation Heatmap (`apps/webui/src/routes/Correlation.tsx`)

- N×N CSS table heatmap. Color scale: red (−1.0) → white (0.0) → green (+1.0).
- Timeframe tabs: M5 / M30 / H1.
- **Stale source visibility**: amber banner when all data is stale (market closed / feed offline); stale cells show `~` prefix, amber border, reduced opacity 0.75, and extended tooltip with staleness note.
- New types: `CorrelationPairRow`, `CorrelationMatrixResponse` in `types/api.ts`.
- `api.correlationMatrix(timeframe)` in `client.ts`.
- Vite proxy: `/api/v1/correlation` added to `vite.config.ts`.
- Route `/correlation` in `App.tsx`, `⊠ Correlation Matrix` nav item in `AppNav.tsx`.

#### Tests

- **50 new tests** across 3 files: `test_correlation_aligner.py`, `test_correlation_numerical.py`, `test_correlation_service.py`.
- Total test suite: **203 tests, all passing**.

---

### Added — SMC Trader: full execution pipeline (2026-04-03)

Six new modules implement thesis-to-MT5 pending order execution:

- **`smc_desk/trader/config.py`** — `SmcTraderConfig` dataclass loaded from env vars: `SMC_TRADER_ENABLED`, `SMC_TRADER_RISK_PER_TRADE_PCT` (default 0.5), `SMC_TRADER_MAX_LOT_SIZE` (default 10.0), `max_positions_per_symbol`, `max_positions_total`, `min_quality`, `min_rr_ratio`, `pending_ttl_seconds`, `custody_interval_seconds`, `scale_out_pct`, `bias_change_cooldown_seconds`, `entry_zone_buffer_pips`.
- **`smc_desk/trader/entry_policy.py`** — `SmcEntryPolicy`: duplicate prevention (same symbol+side), total position cap, directional concentration guard (≥70% same side blocks new).
- **`smc_desk/trader/pending.py`** — `SmcPendingManager`: evaluates thesis candidates against current price, builds `SmcPendingDecision` (place/modify/cancel/hold). Accepts thesis status `active`, `prepared`, and `watching`.
- **`smc_desk/trader/service.py`** — `SmcTraderService`: orchestrates candidate → entry policy → risk gate → pending decision → risk-based lot sizing → MT5 execution. Normalizes `entry_type` (`buy_limit` → `limit`, `sell_stop` → `stop`) for connector compatibility.
- **`smc_desk/trader/custody.py`** — `SmcCustodyEngine`: break-even, scale-out, and hard-cut custody for open SMC positions.
- **`smc_desk/trader/worker.py`** — `SmcTraderWorker`: async worker that loads thesis, fetches price via `get_candles("M1", 1)`, delegates to `SmcTraderService.process_thesis()`. Uses `asyncio.get_running_loop()` captured before `asyncio.to_thread()` for thread-safe MT5 calls.

#### Runtime wiring

- **`smc_desk/runtime.py`**: reconciliation loop always launches (regardless of initial `enabled` state), dynamically checks `SmcTraderConfig.enabled` each cycle. Added `_ensure_trader()` for lazy trader creation. Per-symbol event deduplication via `_enqueued_symbols` set prevents queue flooding (scanner can emit 40+ events per symbol per cycle).
- **`apps/control_plane.py`**: `.env` values now injected into `os.environ` via `os.environ.setdefault()` loop in `lifespan()`, fixing `SmcTraderConfig.from_env()` which uses `os.getenv()` directly.

#### Risk-based lot sizing

- **Lot calculation always uses `FastRiskEngine.calculate_lot_size()`** — thesis `volume_options` (LLM-generated, account-unaware) are ignored. Formula: `risk_amount / (sl_points × tick_value)` with margin check (≤50% free margin) and cap at `SmcTraderConfig.max_lot_size`.
- **RiskKernel profile integration** — when `risk_gate_ref` returns a profile-based `risk_per_trade_pct` (e.g. profile 4 → 2.0%), that value overrides the config default. Enables centralized risk control across desks.

#### WebUI integration

- **`Settings.tsx`**: new "SMC Trader" section with toggle for `SMC_TRADER_ENABLED`, visible when SMC desk is active.
- **`client.ts`**: API client updated with SMC trader config endpoints.

#### Infrastructure

- **`runtime_db.py`**: new `smc_thesis_orders` table schema (thesis_id, symbol, mt5_order_id, mt5_position_id, operation_type, side, entry_price, stop_loss, take_profit, volume, status).
- **`core/runtime/service.py`**: SMC trader hooks exposed from `CoreRuntimeService` (risk gate, ownership register).
- **`configs/base.env.example`**: added all `SMC_TRADER_*` env var documentation.

### Fixed — SMC candidate generation pipeline (2026-04-02)

- **Skip LLM when candidates=0**: `call_smc_validator` no longer invoked if heuristic pipeline produced no operation candidates. Saves GPU cycles on every empty thesis.
- **Confluence gate lowered from ≥2 to ≥1**: a single valid OB or FVG now generates a preparatory candidate. The previous gate silently discarded all zones with only one structural signal.
- **CHoCH detection window expanded from 8 to 20 swings**: covers ~10 weeks on D1 instead of ~4. Both CHoCH detection and trend derivation use the wider window.
- **CHoCH↔zone overlap tolerance relaxed from 0.1% to 0.5%**: `choch_at_origin` confluence now matches zones within ±0.5% of CHoCH price (was ±0.1%, too tight for real charts).
- **Sweep↔CHoCH correlation window expanded from 5 to 10 bars**: captures sweep→reversal sequences that develop over more candles.
- **Bar depth tripled** — scanner and analyst defaults now D1=300, H4=600, H1=900 (was 100/200/300). All configurable via `SMC_ANALYST_*_BARS` and `SMC_SCANNER_*_BARS` env vars.

### Fixed — SMC LLM pipeline audit (2026-04-02)

#### Config wiring bug (H1, H4)
- **`heuristic_analyst.py`**: `call_smc_validator` now passes full config dict (`max_tokens`, `temperature`, `localai_base_url`) instead of only model and timeout. Previously `max_tokens` always fell back to 500 regardless of `.env` value.
- **`SmcAnalystConfig`**: new `localai_base_url` field loaded from `LOCALAI_BASE_URL` env var, eliminating scattered `os.getenv` calls.

#### LLM concurrency saturation (critical)
- **`runtime.py`**: `_dispatch_loop` now `await`s each analyst run instead of firing concurrent `create_task`. With N symbols active, previously N HTTP calls hit LocalAI simultaneously, saturating a single-GPU inference slot and causing cascading timeouts.
- **`validator.py`**: `_LLM_GATE` (`asyncio.Lock`) ensures only one HTTP call to LocalAI is in flight at any time. Combined with sequential dispatch, the outbound queue always holds 0 or 1 requests.

#### Prompt caching + versioning
- **`validator.py`**: prompts loaded once and cached in `_PROMPT_CACHE`. `get_prompt_version()` returns a SHA-1 short hash for future LoRA traceability.

#### Operational logging
- **`validator.py`**: `call_smc_validator` now prints structured `[smc-validator]` lines with elapsed time, prompt/completion tokens, input chars, and budget. Warns when completion tokens exceed 80% of `max_tokens`.

#### Temperature from config
- **`_call_localai_sync`**: `temperature` is now a parameter (was hardcoded 0.1). Returns `(parsed_json, raw_content, usage)` tuple for observability.

#### Passive LoRA traceability
- **`heuristic_analyst.py`**: `HEURISTIC_VERSION = "2026.04"` constant added (no runtime effect, for future dataset curation).

#### .env example
- **`configs/base.env.example`**: `SMC_LLM_MAX_TOKENS` lowered from 8192 to 500 (matches effective fallback that was always applied).

### Added
- `TRADERS_GUIDE.es.md` — new trader-friendly documentation in Spanish, focused on explaining the system architecture, market desks, risk management, and WebUI panels in accessible language. Complements the technical `README.es.md` and serves as onboarding guide for traders of all experience levels.

---

## [0.3.4] — 2026-03-28

### Added — Broker clock from EA + 6-phase Fast Desk refactoring

#### Broker clock architecture (EA → Python)

- **`LLMBrokerSessionsService.mq5`**: EA now sends `TimeTradeServer()` and `TimeGMTOffset()` in every session payload. Two new JSON fields: `server_time` (epoch int) and `gmt_offset` (seconds int).
- **`registry.py`**: New `set_broker_clock()`, `get_broker_gmt_offset()`, `is_broker_clock_available()` functions store and expose the EA-reported GMT offset.
- **`gate.py`**: `is_trade_open_from_registry()` now uses `broker_gmt_offset` (from EA) instead of tick-derived offset. Session schedule comparison uses system clock UTC + EA GMT offset.
- **`service.py` (sessions)**: Extracts `server_time`/`gmt_offset` from EA payload on every pull cycle, calls `registry.set_broker_clock()`.
- **`/status` endpoint**: Exposes `broker_gmt_offset` and `broker_clock_available` fields.
- **Market gate endpoint**: `GET /api/v1/fast/market-gates` returns per-symbol gate state.

#### Time architecture clarification

- **Authoritative clock**: system UTC + EA-reported `TimeGMTOffset()` + broker session schedules from EA.
- **Tick-based offset** (`estimate_server_time_offset`): demoted to informative-only (candle latency). Not used for market gate decisions.
- **Removed**: ±12h sanitization workaround in `set_server_time_offset()` — no longer needed, offset is purely informative.

#### 6-phase Fast Desk analysis refactoring

Complete overhaul of the Fast Desk analysis pipeline per Senior Quant spec:

**Phase 0 — H1 → M30 normalization**
- HTF bias candles changed from H1 to M30 across `FastContextService`, `FastSetupEngine`, and `FastTraderService`.
- `candles_h1` parameter renamed to `candles_htf` with backward compatibility.
- Default watch timeframes: `M1,M5,M30,H1,H4,D1` (H1 preserved for SMC Desk).

**Phase 1 — Hard/soft gate split**
- `_HARD_GATES` frozenset: `stale_feed`, `symbol_closed`, `session_blocked`, `spread_too_wide`, `slippage`, `no_trade_regime`.
- Hard gates return immediately with 0.0 confidence. Soft gates apply a multiplier penalty.
- `session_blocked` promoted from soft to hard gate.

**Phase 2 — ATR-aware EMA overextension**
- EMA overextension threshold now uses `max(2.0%, 0.5 × ATR/price × 100)` instead of fixed 2%.
- Adapts to volatile instruments (BTCUSD, XAUUSD) vs tight forex pairs.

**Phase 3 — M5-only market phase detection**
- Market phase (`trending`/`ranging`/`compression`/`breakout`) now computed from M5 candles only.
- Removed H1 dependency for phase detection.

**Phase 4 — Setup engine fixes**
- ATR floor for SL removed (was rejecting valid setups on volatile instruments).
- Premium/Discount filter softened to ×0.7 confidence multiplier (was hard block).
- Bias alignment filter softened to ×0.75 multiplier (was hard block).

**Phase 5 — Trigger engine fixes**
- Optional `context` parameter for future context-aware triggers.
- `very_low` volatility rejection in trigger.
- Trigger stacking: requires ≥2 triggers or 1 strong trigger.
- Exhaustion confidence gate.

**Phase 6 — Debug logging**
- Comprehensive debug logging across trader service pipeline.
- Activity log throttled to 60s for noisy hard gates (`stale_feed`, `symbol_closed`, `session_blocked`).
- Pipeline traces suppressed for noisy hard-gated symbols in SSE.

#### SSE improvements

- SSE heartbeat changed from `data: {"traces": [], ...}` to SSE comment `": heartbeat\n\n"` when there are no traces.
- Eliminates noise in WebUI from empty trace payloads.

#### Worker market-gate integration

- `FastDeskService._desired_symbols()` now checks `is_trade_open_from_registry()` before spawning workers.
- Workers only created for symbols with open broker trade sessions.
- Market gate events emitted to activity_log ring buffer with state change tracking.
- `FastDeskService.get_market_gates()` class method for WebUI/API consumption.

### Changed
- Fast Desk RR is now governed by a single operator-facing value: `FAST_TRADER_RR_RATIO`.
- Fast Desk runtime/setup config no longer expose a second independent RR floor on the public config surface.
- Fast Desk live config propagation now updates shared setup/risk/trader objects so RR and related WebUI changes affect active workers without waiting for process restart.
- Fast custody level updates preserve the current take-profit when only the stop-loss is being moved (break-even / trailing), preventing accidental TP clearing.

### Fixed
- Fast risk engine now clamps `risk_pct` to the documented 2% cap.
- Fast risk engine accepts legacy `pip_value` callers for backward compatibility while preserving the MT5 `symbol_spec` path.
- Fast Desk test suite debt around `calculate_lot_size()` compatibility is now green again.
- Weekend/holiday bug: `server_time_offset = -86400` from stale Friday ticks no longer corrupts market gate (offset removed from gate logic).
- Forex symbols no longer appear as pipeline noise when markets are closed.

### Planned
- `GET /smc/thesis/{symbol}` — latest SMC thesis per symbol
- `GET /smc/zones/{symbol}` — active order-block / FVG zones
- `GET /smc/events` — recent SMC event log
- `GET /smc/status` — scanner health + last run timestamp
- SMC Trader integration — live order execution from SMC thesis
- `OwnershipRegistry` — formal Fast/SMC position ownership layer
- `RiskKernel` — global + per-desk heuristic risk (account-aware, desk-aware, API-configurable)
- `FastTraderService` — real execution + custody, depends only on connector surface
- `SmcTraderService` — execution + ownership-aware operation flow
- `BridgeSupervisor` — multi-terminal / multi-account runtime
- Paper mode separation and UI hooks

---

## [0.3.2] — 2026-03-27

### Added — Symbol Catalog page & per-symbol desk assignment

New WebUI page for browsing and managing the full broker symbol catalog.
Per-symbol desk assignment (FAST / SMC) allows controlling which desk
processes each subscribed symbol, live, without restart.

#### WebUI — Symbol Catalog (`/symbols`)
- Tree-view of all broker symbols grouped by `asset_class > path_group`
- Auto-flatten for singleton groups (e.g. Crypto on FBS)
- Full-text search filter (name, description, asset class, group)
- Click-to-subscribe / unsubscribe with live SSE refresh
- Symbol detail panel: catalog info + full MT5 specification for subscribed symbols
- EA requirement warning for subscribed symbols
- Per-symbol FAST / SMC desk toggles (rectangular badges matching design system)
- Tree-row compact badges (`⚡ FAST` / `◆ SMC`) + detail-panel toggle buttons

#### Backend — Desk assignment system
- `CoreRuntimeService.symbol_desk_assignments` dict tracks per-symbol desk set
- Helper methods: `get_symbol_desks()`, `set_symbol_desks()`, `get_all_symbol_desk_assignments()`, `subscribed_symbols_for_desk()`
- `_default_desks()` auto-detects attached desks (FAST/SMC)
- FAST desk lambda filtered: only symbols with `"fast"` in their desk set are fed to `FastDeskService`
- `GET /api/v1/symbols/desk-assignments` — returns full assignment map
- `PUT /api/v1/symbols/{symbol}/desks` — set desks for a symbol (validates subscribed + at least one desk)
- `symbol_desk_assignments` included in `/status` SSE payload

#### Types & API client
- `CatalogEntry` type enriched with all broker fields (`path`, `asset_class`, `path_group`, `path_subgroup`, `visible`, `trade_mode`, `digits`, currencies, broker identity)
- `LiveStateSnapshot.symbol_desk_assignments` field
- API client: `getDeskAssignments()`, `setSymbolDesks(symbol, desks)`
- Vite proxy: `/api/v1/symbols` route added

#### Design system
- `.desk-badge` CSS class (compact, tree rows) with `.fast.on/off`, `.smc.on/off` variants
- `.desk-btn` CSS class (larger, detail panel) matching `cap-badge` design language

---

## [0.3.1] — 2026-03-26

### Changed — Fast Desk analysis audit & strategic gate hardening

Point-by-point audit of the Fast Desk analysis layer against Smart Money Concepts
educational doctrine.  8 strategic gates added across context, setup, and policy layers.
Slippage model replaced from hardcoded points to spec-driven calculation.

#### Context service (`fast_desk/context/service.py`)

| Gate | Type | Detail |
|------|------|--------|
| Market phase detection | hard | `_detect_market_phase()` classifies M5 into `trending` / `ranging` / `compression` / `breakout`; `ranging` blocks trading |
| Exhaustion risk | soft | `_detect_exhaustion()` detects late-trend signals (H1 CHoCH, directional dominance + shrinking bodies); `high` + confidence < 0.80 → skip setup |
| EMA alignment + overextension | hard | `_ema_check()` computes EMA20/50 on H1 closes; price > 2% from EMA20 → `ema_overextended` blocks trading |
| Slippage model rewrite | hard | Replaced `max_slippage_points=30` (fixed for all symbols) with `max_slippage_pct=0.05` (percentage of price, universal across forex/crypto/metals/indices) |

#### Setup engine (`fast_desk/setup/engine.py`)

| Gate | Detail |
|------|--------|
| Spread-aware SL buffer | SL widened by live `spread_pips` distance before RR calculation |
| Minimum RR gate | Effective RR < `FAST_TRADER_MIN_RR` (default 2.0) → setup rejected |
| OB mitigation filter | Order blocks where any candle body closed inside zone after origin → marked consumed, skipped |
| Premium/Discount zone filter | Buy only in discount zone, sell only in premium zone (H1 impulse high/low reference) |
| BOS impulse validation | Breakout-retest requires BOS candle body ≥ 1.2× average M5 body; rejects weak/fake breakouts |

#### Entry policy (`fast_desk/policies/entry.py`)

| Gate | Detail |
|------|--------|
| Directional concentration | ≥ 70% of open positions (min 3) on same side → block new entries in that direction |

#### Execution slippage (`fast_desk/trader/service.py`)

Replaced global `max_slippage_points=30` with `_execution_slippage_from_spec()`:
- Primary: 10% of `trade_stops_level` from symbol spec (clamped to `[5, stops_level]`)
- Fallback: 3× typical `spread` from symbol spec
- Ultimate fallback: 30 points (unknown specs only)

Applied at both entry execution and custody execution (close/reduce).

#### Configuration changes

| Old | New | Default |
|-----|-----|---------|
| `FAST_TRADER_MAX_SLIPPAGE_POINTS=30` | `FAST_TRADER_MAX_SLIPPAGE_PCT=0.05` | 0.05% |
| — | `FAST_TRADER_MIN_RR=2.0` | 2.0 |
| `FastTraderConfig.max_slippage_points` | Removed from config — now derived per-symbol from spec | — |

#### Tests

- Updated 4 test files for new config field names (`max_slippage_pct` replaces `max_slippage_points`)
- Added BOS impulse validation test data (strong candle at BOS index)
- **48 passing** (3 pre-existing `calculate_lot_size` signature mismatches excluded)

---

## [0.3.0] — 2026-03-26

### Changed — SMC Desk doctrine audit & correction

Full point-by-point audit of the SMC analysis layer against Smart Money Concepts
doctrine.  All 7 detection modules, the scanner, the analyst, and the confluence
evaluator were reviewed and corrected.  The system now enforces the complete SMC
rule set while keeping tolerances generous enough for real market noise.

#### Detection layer (`smc_desk/detection/`)

| Module | Change | Detail |
|--------|--------|--------|
| `structure.py` | CHoCH confirmation flag | `last_choch.confirmed = True` when a follow-through BOS in the new direction appears after CHoCH |
| `structure.py` | Impulse bounds fix | `_impulse_bounds()` now derives swing high/low from the structural event (BOS/CHoCH), not just the last swing pair |
| `order_blocks.py` | Mitigation tracking | Every OB carries `mitigated: bool` — True when price closed inside the zone after formation |
| `order_blocks.py` | CHoCH-based OBs | OB validation now accepts both BOS **and** CHoCH as valid structural breaks; new `structure_break: "bos" \| "choch"` field |
| `fair_value_gaps.py` | Mitigation tracking | Every FVG carries `mitigated: bool` |
| `liquidity.py` | Taken tracking | After sweep detection, swept zones are marked `taken: True` in-place |
| `liquidity.py` | Sweep quality | Each sweep classified as `sweep_quality: "clean" \| "deep"` (≤ 0.15 % overshoot = clean) |
| `elliott.py` | Fibonacci cross-validation | Impulse scoring now checks W2/W4 retracement depths and W3 extension ratio; soft penalties (−0.05 per hard violation) |
| `confluences.py` | **Weighted scoring** | Linear `len / MAX` replaced by a weighted sum per confluence; high-conviction signals (sweep+CHoCH, Fib-618, premium/discount) score more than informational ones |
| `confluences.py` | New confluences | `ob_unmitigated`, `fvg_unmitigated`, `choch_confirmed`, `sweep_choch_corr` |
| `confluences.py` | Sweep → CHoCH correlation | New T1 confluence: sweep occurring ≤ 5 candles before a CHoCH (liquidity grab → reversal) |

#### Scanner (`smc_desk/scanner/`)

- **Mitigation lifecycle** — new `_is_mitigated()` helper distinguishes zone mitigation (price inside OB/FVG body → status `"mitigated"`) from full invalidation (price closes beyond zone → status `"invalidated"`).
- **`zone_mitigated` event** — emitted alongside existing `zone_invalidated`.
- **Detection-level filter** — zones with `mitigated: True` from the detection layer are excluded from candidate generation before confluence scoring.
- Scan summary now includes `mitigated` count.

#### Analyst (`smc_desk/analyst/`)

- **Minimum confluence gate** — zones with < 2 confluences are silently dropped before candidate emission.
- **Anti-D1 guard** — when a candidate's side opposes D1 trend, require H4 CHoCH confirmed before emitting.
- **ATR-calibrated SL** — SL margin is now floored at `1.2 × ATR(H4, 14)`, providing volatility-aware stop placement.  New `sl_method: "atr_calibrated_zone_margin"` when ATR dominates.
- `_compute_atr()` helper added (simple True Range average, same formula as Fast Desk).

#### Tests

- **14 new unit tests** covering OB/FVG mitigation fields, sweep quality, CHoCH confirmation, weighted confluences, scanner mitigation helpers, Elliott Fibonacci validation, and ATR helper.
- **Total: 29/29 passing** (was 15).

---

## [0.2.1] — 2026-03-24

### Added

**MT5Connector execution surface closure** — the five missing public methods are now implemented,
certified, and covered by unit tests.

| Method | MT5 action | Notes |
|--------|-----------|-------|
| `modify_position_levels(symbol, position_id, sl, tp)` | `TRADE_ACTION_SLTP` | Sets SL/TP on open position; omits zero/None values |
| `modify_order_levels(symbol, order_id, price, sl, tp)` | `TRADE_ACTION_MODIFY` | Modifies price/SL/TP of pending order |
| `remove_order(order_id)` | `TRADE_ACTION_REMOVE` | Cancels a pending order |
| `close_position(symbol, position_id, side, volume, slippage)` | `TRADE_ACTION_DEAL` | Opposite-side market deal; full and partial close supported; `comment=""` |
| `find_open_position_id(symbol, comment)` | `positions_get` | Exact comment match; returns `None` when comment empty or not matched |

**Preflight safety helper** — `_ensure_trading_available()`:
- Verifies `account_info()` is not `None`
- Verifies `terminal_info()` is not `None`
- Verifies `terminal_info().trade_allowed` is `True`
- Preserves `ACCOUNT_MODE` guard (blocks real-account writes when `ACCOUNT_MODE=demo`)
- Raises `MT5ConnectorError` with actionable text on any failure
- Called before every write action; `probe_account()` is intentionally excluded to avoid
  session-degradation side effects (documented in code)

**`FastExecutionBridge` canonical surface adoption:**
- `open_position` → `connector.send_execution_instruction(...)` (was `place_order`)
- `apply_custody` TRAIL_SL → `connector.modify_position_levels(...)` (was `modify_position`)
- `apply_custody` CLOSE → `connector.close_position(symbol, position_id, side, volume)` (was `close_position(position_id)` with missing args)
- `apply_custody` now accepts `position=` kwarg so `symbol`, `side`, `volume` are available from live account state
- `FastSymbolWorker.apply_custody` call updated to pass the live position dict

**Integration certification** (`tests/integration/mt5_connector_certification.py`):
```
summary passed=52 failed=0 skipped=1
```
- Skipped: `connector.manage.find_open_position_id` (requires `--comment-mode tagged`; broker rejects populated comments)
- Risky probe test: `connector.read.probe_invalid_account` continues to demonstrate documented disruptive behavior

**Unit tests added** — 13 new cases in `tests/infra/test_mt5_connector.py`:
- `modify_position_levels` builds `TRADE_ACTION_SLTP` request
- `modify_position_levels` omits zero/None SL and TP fields
- `modify_order_levels` builds `TRADE_ACTION_MODIFY` request
- `remove_order` builds `TRADE_ACTION_REMOVE` request
- `close_position` with `side=buy` closes using sell + bid price
- `close_position` with `side=sell` closes using buy + ask price
- `close_position` with invalid side raises `MT5ConnectorError`
- `find_open_position_id` finds exact comment match
- `find_open_position_id` returns `None` when comment not found
- `find_open_position_id` returns `None` when comment is empty
- Preflight fails when `trade_allowed=False` on `modify_position_levels`
- Preflight blocks `remove_order` when trading disabled
- Preflight blocks `close_position` when trading disabled

**Total test suite: 62/62 passing** (was 49/49 before this release).

### Residual risks documented

1. **Comment-tagging** — `find_open_position_id` by comment is environment-dependent.
   Formal ownership requires `OwnershipRegistry` (next phase).
2. **`probe_account()` session degradation** — `_ensure_trading_available()` intentionally
   avoids calling it. Risk is documented in code comments.
3. **`CustodyDecision.CLOSE` without position context** — callers must pass a real `position`
   dict (with `symbol`, `side`, `volume`) to `apply_custody`. `FastSymbolWorker` always does.

---

## [0.2.0] — 2026-03-24

### Added

**Fast Desk** (`FAST_DESK_ENABLED=true`) — deterministic, no LLM, per-symbol custody loop:

| Module | File | Responsibility |
|--------|------|----------------|
| `FastScannerService` | `fast_desk/signals/scanner.py` | EMA crossover + volume spike + ATR range filter |
| `FastRiskEngine` | `fast_desk/risk/engine.py` | lot-size (hard cap 2% account) · drawdown guard |
| `FastEntryPolicy` | `fast_desk/policies/entry.py` | no-duplicate · max open positions enforcement |
| `FastCustodian` | `fast_desk/custody/custodian.py` | TRAIL_SL · lock profit · CLOSE (deterministic) |
| `FastExecutionBridge` | `fast_desk/execution/bridge.py` | MT5Connector wrapper · no retries |
| `FastDeskState` | `fast_desk/state/desk_state.py` | per-symbol in-memory state |
| `FastSymbolWorker` | `fast_desk/workers/symbol_worker.py` | scan 5s / custody 2s independent async loop |
| `FastDeskService` | `fast_desk/runtime.py` | TaskGroup · per-symbol worker lifecycle |

**SQLite tables added:**

- `fast_desk_signals` — signal log with confidence, trigger, side
- `fast_desk_trade_log` — custody actions (TRAIL_SL, CLOSE, HOLD) per position

**Tests added:** 19 Fast Desk unit tests, all passing.

### Changed
- `build_runtime_service()` auto-wires `FastDeskService` when `FAST_DESK_ENABLED=true`
- `CoreRuntimeService.run_forever()` TaskGroup drives both desks concurrently

### Docs
- `docs/ARCHITECTURE.md` — full rewrite with Mermaid diagrams (7 diagrams)
- `README.md` — full rewrite with Mermaid diagram, tables, env vars, SQLite schema
- `FAST_DESK_CONSTRUCTOR.md` — rewritten as self-contained implementation prompt
- `docs/plans/2026-03-24_next_5_steps.md` — 5-step roadmap

---

## [0.1.1] — 2026-03-24

### Fixed
- `GET /positions` was returning the aggregate `exposure_state` dict instead of individual
  position and order records. Now returns `{"positions": [...], "orders": [...]}`.
- `GET /exposure` added as the correct endpoint for aggregate gross/net volume data.
- Console status loop reported `positions=0` always — wrong dict key
  (`exp.get("open_positions", [])` → `exp.get("open_position_count", 0)`).
- Startup banner balance/currency read from `account_state` (correct) instead of
  `broker_identity` (which has no balance field).

### Changed
- Console startup banner shows: Python version, MT5 account, balance, subscribed symbols.
- Console status line every 30s: `positions=N | orders=N | equity=X | uptime=Xs`.

---

## [0.1.0] — 2026-03-23

### Added

**SMC Desk** (`SMC_SCANNER_ENABLED=true`) — full migration from `llm-metatrader5-bridge`:

| Module | File | Responsibility |
|--------|------|----------------|
| `structure.py` | `smc_desk/detection/` | BOS · CHoCH · trend direction |
| `order_blocks.py` | `smc_desk/detection/` | bullish / bearish OB identification |
| `fair_value_gaps.py` | `smc_desk/detection/` | FVG classification |
| `liquidity.py` | `smc_desk/detection/` | sweet spots · equal highs/lows |
| `fibonacci.py` | `smc_desk/detection/` | retracement levels |
| `elliott.py` | `smc_desk/detection/` | wave labelling |
| `confluences.py` | `smc_desk/detection/` | zone scoring |
| `SmcScannerService` | `smc_desk/scanner.py` | full detection pipeline per symbol |
| `SmcAnalystService` | `smc_desk/analyst.py` | bias · scenario · candidate thesis |
| `HeuristicValidator` | `smc_desk/validators/` | confidence · pip · risk/reward filters |
| `LLM Validator` | `smc_desk/validators/llm_validator.py` | Gemma 3 12B fallback (optional) |
| `ThesisStore` | `smc_desk/thesis_store.py` | LRU cache + SQLite persistence |
| `SmcDeskService` | `smc_desk/runtime.py` | event queue · dispatch loop · cooldown |

**SQLite tables added:**

- `symbol_catalog_cache` — broker-partitioned symbol list
- `symbol_spec_cache` — pip_size, contract size, margin currency per symbol
- `account_state_cache` — balance, equity, margin
- `position_cache` — open positions per broker/account
- `order_cache` — pending orders per broker/account
- `smc_zones` — active OB / FVG zones
- `smc_thesis_cache` — latest thesis per symbol
- `smc_events_log` — scanner event history

**Core runtime wiring:**
- `CoreRuntimeService.attach_smc_desk(desk)` + `attach_fast_desk(desk)`
- `SubscriptionManager` — symbol hot-add/remove without restart
- `ChartRegistry` — ChartWorker per symbol, shared `_mt5_lock`
- `SymbolSpecRegistry` — broker-agnostic `pip_size(symbol)`
- `MT5Connector._mt5_call()` — serialized MT5 API access (not thread-safe upstream)

**Control Plane (FastAPI :8765):**
- `GET /status` · `GET /chart/{symbol}/{tf}` · `GET /specs` · `GET /specs/{symbol}`
- `GET /account` · `GET /positions` · `GET /exposure`
- `GET /catalog` · `POST /subscribe` · `POST /unsubscribe`
- `GET /events` — SSE live stream

**Tests:** 30 unit tests (core:6, infra:6, smc_desk:15, integration:3 skipped)

### Initial baseline
- Architectural correction from `llm-metatrader5-bridge`: MT5 ownership boundary,
  RAM-first market state, broker-partitioned SQLite, no disk JSON during runtime.
- Repo: `heuristic-metatrader5-bridge` / `heuristic_mt5_bridge` package.
- Python 3.13.3 · FastAPI · uvicorn · MetaTrader5 · aiofiles · structlog

---

[Unreleased]: https://gitlab.com/Sergio_Privado/heuristic-metatrader5-bridge/compare/HEAD...HEAD
[0.2.0]: https://gitlab.com/Sergio_Privado/heuristic-metatrader5-bridge/compare/v0.1.1...v0.2.0
[0.1.1]: https://gitlab.com/Sergio_Privado/heuristic-metatrader5-bridge/compare/v0.1.0...v0.1.1
[0.1.0]: https://gitlab.com/Sergio_Privado/heuristic-metatrader5-bridge/compare/098229c...v0.1.0
