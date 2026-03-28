# Final WebUI Direction

## Recommended vision

The WebUI should behave like a trading operations console, not like a generic SaaS dashboard and not like a backend debug page.

It must help an operator answer three questions quickly:

1. Is the bridge healthy and trustworthy right now?
2. What is happening on this account and on the subscribed market set?
3. What can I act on now, and what is still only preview or roadmap?

The interface should feel dense, deliberate, and calm under pressure. It should privilege immediate state recognition over decorative density. It should never manufacture certainty the backend does not actually provide.

## Core UX principles

### 1. Truth over aspiration

If the backend does not expose a capability, the UI does not imply that capability exists.

- no fake action buttons that silently do nothing
- no green status for inferred or missing fields
- no conflation of roadmap concepts with live resources

### 2. Fast read under pressure

The first screenful of every primary view must answer the essential operational question for that view.

- health before detail
- exposure before ornament
- alerts before decorative charts
- action affordances only where the action is truly available

### 3. Explicit capability labeling

Every important panel or control must show its capability state:

- `Live`: directly backed by current control-plane endpoints
- `Derived`: computed from live data but not provided as a first-class backend primitive
- `Partial`: available, but missing a piece of required semantics
- `Preview`: intentionally designed shell for a backend surface that is planned next
- `Planned`: not yet buildable beyond static framing
- `Unknown`: meaningful state exists, but current API does not expose it

This is stricter than any individual proposal and should become the editorial standard.

### 4. Operator-safe progression

Navigation should move from global supervision to focused desk work.

- Runtime Overview for trust and liveness
- Operations Console for account and bridge supervision
- desk pages only after the operator has enough context

### 5. Progressive disclosure, not route sprawl

Catalog, specs, charts, and symbol details should be accessible, but not all promoted to top-level destinations.

Primary routes should be few. Drilldowns can be deeper.

### 6. No hidden semantic jumps

The UI must not blur these boundaries:

- MT5 account mode versus product execution mode
- snapshot stream versus event history
- comment hints versus ownership truth
- connector capability versus exposed HTTP control

## Visual principles

The visual language should read as trading-native and operationally serious.

- dark-neutral base with high-contrast, low-glare surfaces
- restrained accent system:
  - cyan for live data and connectivity
  - amber for caution, pending, partial, and degraded states
  - red for risk breaches, feed loss, and operator danger
  - muted steel/stone neutrals for structure
- typography with strong numeric readability and compact tabular figures
- dense cards and strips, but with clear grouping and rhythm
- charts and ladders framed as instruments, not marketing visuals

Avoid:

- purple-heavy AI-dashboard styling
- glossy SaaS gradients as the main identity
- oversized hero sections
- decorative charts that do not answer an operator question

## How the interface should feel

It should feel like a desk console attached to a real terminal session:

- immediate
- accountable
- slightly severe
- readable at a glance
- explicit about uncertainty

The operator should feel informed, not entertained.

## What to keep from each proposal

### Keep from `codex`

- primary navigation skeleton
- strongest overall route discipline
- capability-state framing
- best alignment with runtime supervision and roadmap layering

### Keep from `copilot`

- stronger human-readable supervision panels
- clearer account and terminal context composition
- practical focus on what an operator checks first

### Keep from `qwen`

- dedicated `Alerts / Events` destination
- chart drilldown as a natural inspection path
- more forceful warning language around dangerous or destabilizing operations

## What to discard from each proposal

### Discard from `codex`

- any wording that overstates current event semantics
- any panel that assumes desk-specific telemetry not yet exposed

### Discard from `copilot`

- any live execution affordance that depends on HTTP endpoints not yet present
- any future endpoint model that ignores the terminal-scoped roadmap direction

### Discard from `qwen`

- outdated statements about missing connector execution methods
- top-level admin/settings drift
- any assumption that `trade_allowed`, terminal identity, or desk state are already first-class API fields

## Implemented backend versus future backend

The UI must always separate three layers:

### Layer 1: Implemented now

Backed directly by current control-plane endpoints:

- runtime status
- catalog and specs
- account summary
- positions
- exposure
- chart snapshots
- subscribe/unsubscribe
- live-state SSE snapshots

### Layer 2: Derived now

Computed honestly from current payloads:

- freshness and stale-state warnings
- broker activity stream derived from `recent_orders` and `recent_deals`
- exposure concentration warnings
- data quality or feed-loss alerts

### Layer 3: Future backend

Must remain `Preview` or `Planned` until explicit APIs exist:

- ownership registry
- risk kernel actions and governance
- live versus paper mode control
- multi-terminal switching/routing
- desk-specific execution actions
- certified audit/event history

## Navigation criteria

The navigation should prioritize the operator's sequence of thought, not the backend module tree.

Primary navigation:

- Runtime Overview
- Operations Console
- Fast Desk
- SMC Desk
- Risk Center
- Terminal / Account Context
- Alerts / Events

Secondary navigation or tabs:

- Ownership
- Live vs Paper
- symbol drilldown
- spec detail

Do not make these top-level:

- raw settings
- environment editing
- catalog browser
- specs browser
- health debug pages

They can exist as embedded drawers, tabs, or contextual panels.

## Alerting criteria

Alerts must be triaged by operational consequence, not by backend source.

Priority order:

1. bridge disconnected or stale
2. feed degraded or frozen
3. exposure or margin danger
4. broker activity requiring attention
5. preview/governance notices

Alert objects should show:

- severity
- freshness
- source type: `live`, `derived`, `preview`
- affected symbol/account scope
- recommended next operator check

## Fast versus SMC treatment

Do not force Fast and SMC into the same visual grammar.

### Fast Desk

Should emphasize:

- execution readiness
- symbol focus
- position and order awareness
- latency of state change
- directness and minimal path to action

Today, because HTTP action endpoints are not exposed, the page should be a read-heavy shell with explicitly disabled or preview-marked action zones.

### SMC Desk

Should emphasize:

- thesis context
- zone/state tracking
- market structure reasoning
- pending candidate review
- deliberate, lower-frequency decision support

Until explicit SMC endpoints exist, it should stay mostly preview-driven with carefully chosen live context panels.

## Accounts, terminals, ownership, and risk

These concepts must not be visually collapsed.

- `Terminal / Account Context` is live and concrete.
- `Ownership` is a governance layer and currently future-state.
- `Risk Center` can partially exist now from derived account and exposure signals, but the true `RiskKernel` control surface is still future-state.
- `Live vs Paper` must not be implied from `account_mode` alone.

When a state is unknown, say `Unknown`. Do not substitute optimism.
