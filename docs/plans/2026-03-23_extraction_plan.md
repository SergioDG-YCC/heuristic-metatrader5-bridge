# Extraction Plan

**Date**: 2026-03-23  
**Goal**: migrate only the useful infrastructure from `llm-metatrader5-bridge` into this new repository.

## 1. Extraction principle

Do not migrate by folder.

Migrate by role:

- keep reusable infrastructure
- rewrite critical-path trading logic
- isolate slow LLM logic

## 2. Keep as shared core

These components are strong candidates for direct migration or light adaptation:

- `mt5_connector.py`
- `market_state_core.py`
- `market_state_runtime.py`
- `account_runtime.py`
- `broker_session_runtime.py`
- `indicator_enrichment.py`
- `execution_bridge.py`
- selected parts of `runtime_db.py`
- `trading_universe.py`
- `main_desk_session_gate.py`

## 3. Keep but redesign

These components contain useful ideas but should not be copied as-is:

- `live_execution_trader_runtime.py`
- `smc_heuristic_scanner.py`
- `smc_thesis_runtime.py`
- `smc_trader_runtime.py`
- `run_market_state_stack.py`
- `control_plane_api.py`

## 4. Do not migrate into fast path

These should not be part of the fast desk critical path:

- `market_analyst_runtime.py`
- `trade_supervisor_runtime.py`
- `chairman_runtime.py`
- `analysis_dispatcher_runtime.py`
- `review_scheduler_runtime.py`
- `memory_curator_runtime.py`
- `geopolitical_runtime.py`
- `treasury_runtime.py`

They may later inspire slow or support services, but not the core fast desk loop.

## 4.1 Explicit replacement for `memory_curator`

The fast desk should not receive a migrated `memory_curator`.

Its replacement is:

- heuristic knowledge translated from prompts/tools
- deterministic policy modules
- small explicit state stores only where needed

If memory-like persistence is added later, it must be:

- narrow
- typed
- operationally justified

never a general narrative accumulation layer in the execution path.

## 5. Fast Desk migration sequence

### Phase 1

Bring over:

- MT5 connector
- market state
- account runtime
- execution bridge
- runtime DB base helpers

### Phase 2

Implement from scratch:

- `fast_signal_engine.py`
- `fast_risk_engine.py`
- `fast_execution_custodian.py`
- `fast_event_bus.py`

### Phase 3

Connect:

- symbol workers
- position workers
- account protection worker

## 6. SMC Desk migration sequence

### Phase 1

Bring over:

- `smc_zone_detection/`
- `smc_heuristic_scanner.py`
- required DB helpers for SMC

### Phase 2

Implement from scratch:

- `smc_heuristic_analyst.py`
- `smc_heuristic_validators.py`

### Phase 3

Implement optional LLM layer:

- `smc_validator_runtime.py`
- multimodal chart snapshot pipeline
- minimal SMC prompts

## 7. Migration constraints

- Do not bring old prompt-heavy design into the fast desk.
- Do not bring office-style role orchestration into the new hot path.
- Do not allow slow SMC queues to affect fast desk custody.
- Do not couple repo bootstrap to legacy stack launch order.

## 8. First code milestone

The first code milestone should not be "full system parity".

It should be:

1. shared core can connect to MT5
2. market state in RAM is live
3. account state is live
4. execution bridge can send a test instruction
5. fast desk skeleton can subscribe to a symbol

## 9. Success criteria

The extraction is successful if:

- fast desk can run without old role stack
- SMC can run independently with heuristic-first logic
- shared core remains reusable by both desks
- the new repo does not inherit unnecessary latency sources
