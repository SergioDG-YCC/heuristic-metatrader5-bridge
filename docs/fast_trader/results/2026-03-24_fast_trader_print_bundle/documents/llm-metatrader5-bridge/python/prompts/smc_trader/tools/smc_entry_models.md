## Tool: SMC Entry Models

Use this reference to select the correct entry model based on the type of prepared setup.

---

### MODEL 1 — Pullback to Order Block After Sweep (Maximum quality)

**Required context**:
- Identified liquidity zone that has been swept (sweep confirmed)
- Visible CHoCH on H4 or H1 after the sweep
- Active OB in the pullback zone
- Minimum 3 confluences

**Entry**: Limit order at the OB (outer edge of the origin candle body).
**SL**: Below/above the sweep extreme + margin of 0.5-1 ATR.
**TP1**: Next opposing liquidity pool.
**TP2**: Fibonacci 161.8% extension of the post-sweep impulse.

**H1 Confirmation**: `h1_choch_aligned` or `h1_bos_aligned`.

**Typical R:R**: 1:3 to 1:5.

**Buy example**:
- SSL swept at 1.0840 (equal lows)
- Bullish CHoCH on H4 confirmed
- Bullish OB on H4 between 1.0855-1.0865
- Fibonacci 61.8% retracement at 1.0858
- Entry: limit buy at 1.0860
- SL: 1.0830 (below the sweep low)
- TP1: 1.0930 (BSL pool, equal highs)
- TP2: 1.0970 (Fibo 161.8%)

---

### MODEL 2 — Pullback to FVG with OB (High quality)

**Required context**:
- Unmitigated FVG inside or adjacent to an active OB
- Multi-timeframe aligned structure
- Minimum 2 confluences

**Entry**: Limit order at the FVG + OB overlap (narrower zone).
**SL**: Below/above the full OB + margin.
**TP1**: Next structural level.
**TP2**: Fibonacci 127.2%-161.8% extension.

**H1 Confirmation**: `h1_fvg_fill_and_hold` or `h1_rejection_candle`.

**Typical R:R**: 1:2 to 1:4.

---

### MODEL 3 — End of ABC Correction in Value Zone (High quality)

**Required context**:
- Clear Elliott count: identifiable end of Wave C
- Wave C reaches the 50%-61.8% retracement of the complete 1-5 impulse
- OB or FVG in the Wave C termination zone
- Ideally with a liquidity sweep at the termination

**Entry**: After reversal confirmation on H1 (do not anticipate the end of Wave C).
**SL**: Below/above the Wave C extreme + margin.
**TP1**: Start of what would be Wave 3 of the new cycle (38.2% retracement of the 1-5 move).
**TP2**: Fibonacci 161.8% extension of the new Wave 1.

**H1 Confirmation**: `h1_choch_aligned` + `h1_bos_aligned` in sequence.

**Typical R:R**: 1:3 to 1:6 (end-of-ABC setups have the highest potential).

---

### MODEL 4 — Entry at Wave 4 for Wave 5 (Medium-high quality)

**Required context**:
- Elliott count: Wave 3 complete, Wave 4 developing
- Wave 4 retraces between 23.6%-50% of Wave 3
- OB in the Wave 4 retracement zone
- Wave 4 does NOT overlap with Wave 1 territory

**Entry**: Limit order at OB in the 38.2% retracement zone of Wave 3.
**SL**: Below the high of Wave 1 (Elliott rule invalidation).
**TP1**: Wave 5 projection (61.8%-100% of Wave 1 from the end of Wave 4).
**TP2**: If Wave 3 was moderate, Wave 5 could extend further.

**H1 Confirmation**: `h1_bos_aligned` in trend direction.

**Typical R:R**: 1:2 to 1:3. Lower than Models 1 and 3 because Wave 5 may truncate.

**Warning**: if Wave 3 was very extended (261.8%+), Wave 5 may truncate. Consider a closer TP.

---

### MODEL 5 — Continuation After BOS with Pullback to OB (Medium quality)

**Required context**:
- Confirmed BOS in trend direction
- Active OB in the post-BOS pullback zone
- At least 2 confluences

**Entry**: Limit order at the OB.
**SL**: Below/above the OB + margin.
**TP1**: Next liquidity level.
**TP2**: Impulse extension.

**H1 Confirmation**: `h1_bos_aligned`.

**Typical R:R**: 1:2 to 1:3.

**Note**: this is the most frequent model but lower quality than the previous ones because it lacks a sweep or a defined Elliott count. It requires solid confluences.

---

### MODEL SELECTION

When evaluating an `operation_candidate` from the thesis:

1. Is there a confirmed sweep? → **Model 1** (sweep + OB)
2. Is there FVG + OB without a sweep? → **Model 2** (FVG + OB)
3. Does Elliott indicate end of ABC? → **Model 3** (end of correction)
4. Does Elliott indicate Wave 4? → **Model 4** (Wave 4 → 5)
5. Is there only BOS + OB? → **Model 5** (continuation)

If no model clearly applies, the intent is `observe`.

### UNIVERSAL RULES

- Never enter without at least 2 validated confluences.
- Never enter with R:R lower than 1:2.
- Never enter against D1 structure without a confirmed CHoCH on H4.
- Prefer London and New York sessions for execution. Asian session only for JPY with clear context.
- If the thesis marks quality as "medium", raise the bar: require 3 confluences or wait for a better setup.
