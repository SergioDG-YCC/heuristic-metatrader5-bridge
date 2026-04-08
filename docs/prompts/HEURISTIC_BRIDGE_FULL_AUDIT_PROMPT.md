## Heuristic MT5 Bridge Full Audit Prompt

Use this prompt to run a deep audit of the current `heuristic-metatrader5-bridge` repo without rewriting it from scratch.

Recommended model:
- `gpt-5.4` for the audit itself
- `gpt-5.3-codex` later only for targeted fixes after the audit is accepted

### Prompt

```text
Audit this repository deeply and produce a findings-first technical report.

Repository:
- heuristic-metatrader5-bridge

Canonical design documents:
1. docs/ARCHITECTURE.md
2. docs/plans/2026-03-23_mt5_data_ownership_boundary.md
3. docs/plans/2026-03-23_chart_ram_runtime_architecture.md
4. docs/plans/2026-03-23_core_runtime_subscription_refactor_plan.md
5. docs/prompts/CORE_RUNTIME_SUBSCRIPTION_REFACTOR_CONSTRUCTOR.md

Context and intended architecture:
- There must be exactly one owner of the MetaTrader5 connector.
- Charts must live in RAM, not on disk.
- Dynamic market data must be polled only for the subscribed symbol universe.
- The initial subscribed universe currently comes from `.env`.
- The architecture must already be ready for future subscribe/unsubscribe from WebUI without another redesign.
- Disk is not a runtime transport.
- JSON and SQLite may exist only for strictly necessary operational persistence, recovery, or auditability, never as the hot-path bus for chart consumers.
- Control Plane must obtain live state from RAM/service access, not by reading disk snapshots as the source of truth.
- The system must fetch enough broker/account/symbol-specific data at startup to support real operational decisions, including lot sizing and order validation.
- If broker or account changes, stale dynamic data must not survive as if it were valid for the new broker/account context.

Specific concerns that must be audited:

1. Live schema bloat:
- Audit `storage/live/core_runtime.json` and every place where live runtime state is serialized.
- Identify fields that should not be persisted or exposed in control-plane snapshots.
- In particular, challenge whether fields like `bid`, `ask`, `last_price`, `tick_age_seconds`, `bar_age_seconds`, per-timeframe price rows, and similar dynamic items belong in the live file.
- Decide the minimum viable control-plane schema.

2. RAM vs disk boundary:
- Verify whether chart state, live feed state, and worker-owned runtime state really live in RAM.
- Identify every place where disk is still being used as a transport or pseudo-cache for hot-path consumers.
- State clearly what must remain in RAM only and what is allowed to persist to disk.

3. Startup completeness for trading:
- Verify whether startup loads all broker/account/symbol data required for:
  - lot sizing
  - volume min/max/step
  - digits / point / tick size / tick value
  - stops level / freeze level
  - trade mode / filling mode / order mode
  - margin / leverage / currencies
  - market sessions / quote-trade availability
- Determine whether the migrated runtime is already sufficient to calculate real lot sizing and validate orders for subscribed symbols.
- If not, list exactly what is missing and where.

4. Subscription-driven correctness:
- Verify that only subscribed symbols are polled dynamically.
- Verify that visible broker symbols outside the subscribed universe do not create live chart workers or hot-path polling work.
- Verify that unsubscribe removes RAM state correctly and that disk persistence does not keep stale active state pretending to be current.

5. Broker/account change safety:
- Audit what happens if the broker, server, account login, or account mode changes.
- Identify stale caches or persisted rows that could leak across broker/account contexts.
- Verify whether symbol specs, sessions, exposure, account state, and market-state checkpoints are partitioned or invalidated correctly.

6. Control Plane contract:
- Audit whether current control-plane access is still coupled to disk.
- Recommend the correct boundary for future WebUI integration.
- The target is:
  - UI selects active symbols
  - runtime updates subscribed universe in RAM
  - desks/analysis/trader modules consume RAM state or service APIs
  - disk remains secondary persistence only

7. Broker sessions and indicators:
- Audit whether broker sessions service is truly live and represented honestly in runtime health.
- Audit whether indicator enrichment is still file-driven and whether that is acceptable as a transitional path.
- Distinguish clearly between:
  - acceptable transitional persistence
  - forbidden hot-path transport

How to work:
- Read the repo and inspect the actual implementation.
- Run local validation where useful.
- If the runtime can be smoke-tested live, do it.
- Do not refactor or patch code unless explicitly asked after the audit.
- Be strict. If the current implementation violates the architecture, say so directly.

Required output format:

1. Findings
- List findings first, ordered by severity.
- Each finding must include:
  - severity
  - precise file references
  - current behavior
  - why it violates the intended architecture
  - operational impact

2. Architecture verdict
- State whether the current repo is:
  - aligned
  - partially aligned
  - misaligned
with the intended design.

3. RAM/Disk boundary table
- Provide a compact table with:
  - data domain
  - source of truth
  - where it currently lives
  - where it should live
  - whether current placement is acceptable

4. Startup readiness verdict
- Answer directly:
  - Can this runtime currently support real lot sizing for subscribed symbols?
  - Can it support real order validation?
  - Is broker/account state sufficiently loaded?

5. Minimal correction plan
- Propose the smallest safe patch set to bring the implementation in line.
- Group fixes by priority.
- Avoid big rewrites.

6. Acceptance criteria
- Define concrete pass/fail criteria for:
  - chart RAM ownership
  - subscription-only polling
  - control-plane minimal schema
  - startup symbol-spec completeness
  - broker/account invalidation behavior

Important constraints:
- Do not drift into generic architecture advice.
- Ground every conclusion in the current codebase.
- Prefer concrete technical judgment over vague recommendations.
- If something is only acceptable temporarily, say that explicitly.
```

### Suggested chat header

```text
Run a deep architecture and implementation audit on this repo using the attached prompt as the canonical instruction set.

Do not patch code yet.
First produce a findings-first audit with severity, exact file references, architecture verdict, RAM/disk boundary review, startup readiness verdict, and a minimal correction plan.
```
