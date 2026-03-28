# Final WebUI Evaluation

## Scope and evidence

This evaluation uses the following sources as the decision baseline:

- Canonical product and architecture docs:
  - `README.md`
  - `docs/WEBUI_ARCHITECTURE.md`
  - `docs/ARCHITECTURE.md`
  - `docs/plans/2026-03-24_immutable_bridge_action_plan.md`
  - `docs/plans/2026-03-24_connector_certification_plan.md`
  - `docs/audit/2026-03-24_live_bridge_audit.md`
  - `docs/audit/2026-03-24_mt5_official_surface_inventory.md`
  - `docs/audit/2026-03-24_connector_certification_execution_report.md`
- Backend/code reality check:
  - `apps/control_plane.py`
  - `src/heuristic_mt5_bridge/core/runtime/service.py`
  - `src/heuristic_mt5_bridge/infra/mt5/connector.py`
  - supporting runtime and desk modules
- Evaluated proposal sets:
  - `docs/webui/codex/`
  - `docs/webui/copilot/`
  - `docs/webui/qwen/`

The standard used here is not "which deck looks better". The standard is: which proposal most accurately represents the actual product, is usable by a human under pressure, and can be built honestly against the current control plane while leaving room for the roadmap.

## Executive summary

No single proposal is sufficient as-is.

`codex` is the strongest primary base. It is the closest to the real product, the cleanest architecturally, and the safest foundation for a Solid.js implementation.

`copilot` has the best operational readability in several areas, especially around account and supervision context, but it overstates what can be controlled live from the current HTTP surface.

`qwen` is not viable as the primary direction. It contains useful ideas around warnings, event framing, and chart drilldown, but it is materially outdated against the certified connector and the current backend surface.

The recommended direction is a consolidation:

- take `codex` as the structural and editorial backbone
- absorb `copilot`'s best operator-facing layout and clarity patterns
- salvage only a small subset of `qwen`: dedicated alerts/events framing, chart drilldown emphasis, and stronger warning language around dangerous operations

## Comparative summary

| Proposal | Overall read | Best use | Main problem | Verdict |
| --- | --- | --- | --- | --- |
| `codex` | Best overall balance | Base IA, capability model, roadmap alignment | Still too optimistic in a few runtime/event assumptions | Winner as primary base |
| `copilot` | Strong operator pragmatism | Operational layout, terminal/account framing | Treats execution controls as more live than the HTTP API allows | Secondary donor |
| `qwen` | Visually energetic but factually stale | Alerts framing, chart drilldown, warning copy | Outdated backend assumptions and route sprawl | Not acceptable as primary base |

## Scorecard

Scores are from `1` to `10`. Higher is better.

| Criterion | `codex` | `copilot` | `qwen` |
| --- | ---: | ---: | ---: |
| Fidelity to the real product | 8.5 | 7.7 | 3.0 |
| Human usability under pressure | 8.2 | 8.3 | 5.7 |
| Operational visualization | 8.1 | 8.0 | 6.2 |
| Coherence with architecture and roadmap | 8.8 | 7.0 | 3.0 |
| Design quality | 8.6 | 8.2 | 5.8 |
| Constructibility in Solid.js | 8.7 | 8.4 | 6.2 |
| Low risk of operator misinterpretation | 7.2 | 6.0 | 2.5 |
| Weighted overall judgment | 8.3 | 7.7 | 4.6 |

## Cross-proposal contradictions that matter

These are not stylistic differences. They materially affect UI honesty and operator safety.

1. `GET /events` is not a semantic event log.
   In `apps/control_plane.py`, the SSE generator streams repeated `build_live_state()` snapshots. Any proposal that treats `/events` as an authoritative event timeline is overstating the backend.

2. The connector now supports execution actions, but the current HTTP control plane still does not expose matching write endpoints.
   A WebUI can show Fast execution panels as preview-ready, but it cannot honestly present open/close/modify/remove as live HTTP actions today.

3. `trade_allowed` is not exposed as a first-class control-plane field.
   The UI must not present a green or red trading permission badge as if the API already provides it. At most, the UI can mark it `Unknown via current API`.

4. Ownership, risk kernel, multi-terminal routing, and explicit desk services are roadmap concepts, not current control-plane resources.
   The UI can reserve space for them, but must label them as `Preview` or `Planned`, never as implemented.

5. MT5 comments are not a reliable ownership primitive.
   Any UX implying stable account/order ownership from comments alone is dangerous and architecturally wrong.

## Proposal-by-proposal assessment

### `codex`

Strengths:

- Best separation between implemented, partial, and future capabilities.
- Best alignment with `BridgeSupervisor`, runtime supervision, account context, and the immutable bridge direction.
- Best candidate for a route tree and component system in Solid.js.
- Strongest editorial discipline: fewer decorative panels, better information hierarchy.

Weaknesses:

- Still leans too far toward richer runtime semantics than the current API actually emits.
- Needs a stricter distinction between snapshot streaming and event history.
- Underuses current `/account` payload detail such as `recent_deals`, `recent_orders`, and exposure-related margin signals.

Risk of misinterpretation:

- Moderate. Mostly fixable with tighter capability badging and stricter wording.

### `copilot`

Strengths:

- Good operator-centric readability.
- Better sense of an operations console used by a human, not just a status dashboard.
- Stronger framing for account, terminal, and practical supervision tasks.

Weaknesses:

- Most serious issue: it treats Fast execution actions as effectively live if health guards pass, but the HTTP control plane does not currently expose those mutations.
- Future API sketches are less aligned with the terminal-scoped roadmap shape.
- Same snapshot-versus-event confusion appears in places.

Risk of misinterpretation:

- High enough to matter. A trader could believe the UI is authorized to act live when the current backend still is not.

### `qwen`

Strengths worth salvaging:

- Dedicated `Alerts / Events` framing.
- Good instinct for chart drilldown and rapid anomaly inspection.
- Better warning tone around dangerous state changes.

Weaknesses:

- Factually stale versus the connector certification and current backend.
- Assumes fields and routes that do not exist.
- Pushes too many engineering/admin surfaces into the primary navigation.
- Visual direction drifts toward a generic devtool/GitHub-dark derivative instead of an operator console.

Risk of misinterpretation:

- Severe. It can mislead the builder about both current capability and future sequencing.

## Which proposal wins on each axis

| Axis | Winner | Why |
| --- | --- | --- |
| Best representation of the real product | `codex` | It tracks the architecture and phased roadmap more closely than the others. |
| Best human UX | `copilot` by a small margin | It reads more like an operator console and less like a systems document. |
| Best operational clarity | `codex` | Cleaner hierarchy and lower UI noise. |
| Best operator visualization | `codex` with `copilot` influence | `codex` has the better structure; `copilot` contributes better practical panel emphasis. |
| Best coherence with backend and roadmap | `codex` | It is the least wrong about current versus future capability. |
| Most reasonable to build in Solid.js | `codex` | It already implies a more modular and routeable UI system. |

## Recommended consolidation

The final direction should not be a rewrite of one proposal. It should be an edited merge with hard corrections.

Use from `codex`:

- the primary information architecture
- the capability-status thinking
- the relationship between runtime supervision, desks, and future governance layers

Use from `copilot`:

- stronger operator-facing panel composition
- clearer terminal/account context
- a more human reading of operational workflows

Use from `qwen`:

- dedicated `Alerts / Events` screen
- chart drilldown as a first-class subflow
- explicit warning language for dangerous operations such as account switching and AutoTrading-related actions

Discard:

- any proposal language that presents non-existent HTTP mutations as available
- any proposal language that implies `/events` is already a durable event feed
- any proposal language that treats ownership, risk, paper/live, or multi-terminal routing as already implemented control-plane resources
- top-level routes for generic settings/admin/env management

## Final decision

The construction baseline should be:

- winner: `codex`
- construction direction: `codex` backbone, `copilot` operational refinements, selective `qwen` salvage

This is the only option that stays honest to the backend, remains usable under operator pressure, and does not trap the future builder into fabricating capabilities that are still roadmap items.

## Decision for construction

- Winning proposal or final combination: `codex` as the primary base, refined with `copilot` for operator ergonomics and a narrow salvage from `qwen` for alerts/events and warning states.
- Recommended build order: shell and capability registry, Runtime Overview, Operations Console, Terminal/Account Context, Alerts/Events, Risk Center read-only shell, Fast Desk shell, SMC Desk shell, Ownership preview, Live vs Paper preview.
- Pending risks: SSE snapshot feed can be mistaken for event history; `trade_allowed` is not first-class in the API; no live write endpoints exist in the HTTP control plane; ownership/risk/multi-terminal semantics are still future-state.
- Depends on future backend: explicit ownership APIs, risk kernel state and actions, live/paper execution mode APIs, terminal-scoped resources, desk-specific telemetry, and true action endpoints for Fast execution.
- Can be built now: runtime supervision, connection and feed state, account/positions/exposure views, chart drilldown, symbol subscription management, broker activity derived from `/account` payloads, alert derivation, and honest preview shells for future modules.
