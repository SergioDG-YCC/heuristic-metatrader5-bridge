# PROMPT: SMC Desk Multimodal Constructor

## Recommended model

**Primary for implementation**: `gpt-5.3-codex`  
**Primary for architecture review**: `gpt-5.4`

## Role

You are implementing the slower SMC desk for this repository.

This desk is allowed to use LLM, including image input, but only after a strong heuristic pipeline has already built and validated the thesis.

## Canonical docs

Use these as canonical:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. the SMC strategy migrated from the old repo design decisions

## Objective

Build an SMC desk with this flow:

```text
market_state RAM
  -> smc_heuristic_scanner
  -> smc_heuristic_analyst
  -> smc_heuristic_validators
  -> optional multimodal llm validator
  -> smc_thesis
  -> smc_trader
```

## Core principles

### The thesis must originate in Python

The LLM must not:

- invent levels
- invent operation candidates from scratch
- replace heuristic invalidations
- receive oversized textual payloads by default

### The LLM may

- validate a heuristic thesis
- summarize the scenario
- inspect a chart image
- flag semantic contradictions

## Required SMC layers

### 1. `smc_heuristic_scanner`

Detect:

- order blocks
- FVG
- liquidity
- sweeps
- confluences

### 2. `smc_heuristic_analyst`

Build:

- bias
- base scenario
- watch conditions
- invalidations
- operation candidates anchored to real zones

### 3. `smc_heuristic_validators`

Reject:

- wrong price regime
- wrong side for zone type
- invalid SL/TP geometry
- weak R:R
- internal contradictions

### 4. `smc_validator_runtime`

Minimal LLM layer.

Preferred input:

- compact heuristic JSON
- chart image snapshot
- symbol
- timeframe
- current price
- trigger reason

## Multimodal policy

Image input is encouraged for SMC final validation if it reduces textual payload.

Preferred LLM pattern:

- heuristic thesis JSON
- one chart image
- minimal metadata

Avoid:

- large candle dumps
- all tools loaded at once
- narrative-heavy prompts

## Constraints

- do not place LLM before heuristics
- do not allow the LLM to create raw trade math from nothing
- keep prompts minimal
- keep image usage optional but supported
- never allow SMC latency to affect fast desk critical path

## First milestone

Deliver:

1. heuristic scanner
2. heuristic analyst
3. hard validators
4. minimal SMC thesis persistence
5. optional multimodal validator hook

## Final output

At the end:

- summarize heuristic rules implemented
- summarize validator constraints
- summarize where image-based LLM validation plugs in
- state residual risks clearly

