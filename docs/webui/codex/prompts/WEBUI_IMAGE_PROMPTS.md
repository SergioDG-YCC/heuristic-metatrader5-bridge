# WEBUI Image Prompts

Date: 2026-03-24  
Project: `heuristic-metatrader5-bridge`  
Use case: stakeholder concept images for Solid.js WebUI direction

## Prompt 1: Master Moodboard

Composition: 4x3 board of interface fragments and mini-screens, including runtime health strip, operations tables, fast signal lane, SMC zone chart, ownership preview matrix, risk preview board, terminal warning panel, and execution-mode comparison panel.  
Information density: medium-high, dense labels and numeric fields, realistic operational detail.  
Mood: serious, disciplined, pressure-ready, professional desk operations.  
Trading context: MT5 bridge supervision for fast execution and thesis-driven SMC review, with live-now plus planned-next capabilities.  
Color/material direction: industrial dark-neutral surfaces, matte panels, teal accent for Fast, steel-blue accent for SMC, amber/red for risk and blockers, precise border hierarchy.  
Screen type: composite moodboard.  
Must be visible: positions/orders grids, exposure bars, chart overlays (order blocks, liquidity, FVG, fibo), capability badges (Live/Partial/Planned), explicit warning surfaces.  
Must be avoided: generic SaaS KPI tiles, purple theme, crypto-hype neon, playful retail widgets, marketing hero sections.

## Prompt 2: Launch / Runtime Overview

Composition: desktop control screen with left nav rail, top critical status strip, central multi-panel runtime board, right incident timeline.  
Information density: high but structured for rapid scanning.  
Mood: calm under stress, technical confidence.  
Trading context: backend startup health, MT5 connector state, market feed health, subscribed symbols, chart workers, broker/account summary, pending alerts.  
Color/material direction: dark graphite background, cool neutral panels, high-contrast badges, restrained red/amber alerts.  
Screen type: operations startup cockpit.  
Must be visible: `status`, health badges, broker identity card, account snapshot, chart worker matrix, feed status row, event timeline.  
Must be avoided: decorative empty spaces, oversized decorative charts, generic admin hero cards.

## Prompt 3: Operations Console

Composition: dual central tables (open positions and pending orders), right column event feed, bottom exposure heatmap and symbol watch strip.  
Information density: very high, compact rows and numeric columns.  
Mood: decisive, controlled urgency, institutional desk feel.  
Trading context: live supervision of positions, orders, execution activity, symbol attention, account quick metrics.  
Color/material direction: dark neutral base, restrained green/red PnL accents, amber for concentration risk, steel-blue separators.  
Screen type: execution supervision console.  
Must be visible: ticket id, symbol, side, volume, open/current, SL/TP, floating PnL, age, exposure concentration bars, event timestamps.  
Must be avoided: cartoon chart icons, giant donut charts, CRM-style card grid.

## Prompt 4: Fast Desk View

Composition: top horizontal signal lane, center symbol-state matrix, right custody timeline, lower fast trade log panel.  
Information density: high and rapid-scan focused.  
Mood: tactical, fast, disciplined automation under human oversight.  
Trading context: per-symbol confidence, trigger, cooldown, custody state, active/recent fast decisions, fast trade log.  
Color/material direction: dark slate panels, Fast accent teal-green, critical close actions in red, muted cool grays for cooldown.  
Screen type: high-speed desk control surface.  
Must be visible: cooldown countdowns, trigger thresholds, custody actions (trail/hold/close), fast decision timestamps, capability badge where data is partial.  
Must be avoided: arcade aesthetics, rainbow effects, flashy glow overload, empty KPI-only layout.

## Prompt 5: SMC Desk View

Composition: chart-dominant center with structural overlays, left thesis list, right validation/review panels, bottom candidate table.  
Information density: medium-high with analytical annotations.  
Mood: strategic, patient, forensic market reading.  
Trading context: zone map, thesis status, bias, validation state, review schedule, operation candidates, analysis-first posture.  
Color/material direction: same core dark system, SMC blue accent, distinct overlay colors for OB/FVG/liquidity/fibo, muted annotation labels.  
Screen type: thesis and structure workstation.  
Must be visible: clear badge that SMC execution trader is planned/partial, bias card, invalidation notes, candidate entries.  
Must be avoided: AI chat bubble gimmicks, sentiment gauge cliches, retail chart palettes.

## Prompt 6: Ownership and Adoption View

Composition: central ownership matrix, left adoption queue, right reassignment panel and audit timeline.  
Information density: high in table, medium in side panels.  
Mood: governance-focused, auditable, procedural.  
Trading context: ownership attribution for positions/orders, inherited operations, reassignment concept to Fast/SMC, reevaluation toggle, audit trace.  
Color/material direction: dark neutral with muted planned-state chips, warning tones for unknown ownership.  
Screen type: operations governance board.  
Must be visible: many `Unknown` or `Inherited` rows, disabled reassignment controls marked Planned, explicit roadmap callouts.  
Must be avoided: fake enabled buttons for unavailable backend, playful icons, false automation impression.

## Prompt 7: Risk Center

Composition: top global risk profile panel, center dual desk budget bars, right kill-switch concept card, bottom limits and exposure grid.  
Information density: medium-high with strong alert hierarchy.  
Mood: authoritative, risk-first, no ambiguity.  
Trading context: global risk profile, per-desk profile, budget allocation, exposure pressure, limits/overrides, kill-switch concept.  
Color/material direction: industrial dark base, amber/red gradients for stress, green only for safe bands, muted planned-state controls.  
Screen type: risk governance console.  
Must be visible: read-only current exposure from backend, Planned markers on missing risk controls, explicit override and kill-switch placeholders.  
Must be avoided: gamified risk meters, celebratory visuals, faux-live controls.

## Prompt 8: Terminal / Account Context View

Composition: top terminal identity and broker/account card, center session integrity board, left danger warning, right recovery checklist and disruption timeline.  
Information density: medium with high warning readability.  
Mood: cautious, procedural, operator safety first.  
Trading context: MT5 installation context, broker, account, terminal health, AutoTrading risk, account-switch disruption warning and recovery path.  
Color/material direction: dark neutral base with high-contrast danger banners and checklist surfaces.  
Screen type: terminal safety and session context panel.  
Must be visible: explicit warning text that failed authentication can disrupt MT5 session and disable AutoTrading, recovery steps (re-enable AutoTrading, restart control plane).  
Must be avoided: minimized warnings, tiny unreadable danger copy, optimistic marketing tone.

## Prompt 9: Paper vs Live Execution View

Composition: two-column comparison (`Account Mode observed now` vs `Execution Mode planned`), lower simulation concept panel, side impact checklist.  
Information density: medium with strict semantic labeling.  
Mood: controlled, compliance-like clarity.  
Trading context: separation of `execution_mode` from `account_mode`, live/paper/simulation model, current vs planned backend truth.  
Color/material direction: consistent dark system, restrained red for live risk, cool neutral tones for paper/simulation states, strong typography for mode labels.  
Screen type: mode governance and readiness panel.  
Must be visible: disabled preview toggles for execution mode, explicit warning that account mode does not define execution mode.  
Must be avoided: ambiguous labels, toy-like toggles, mixed semantics between account and execution modes.

