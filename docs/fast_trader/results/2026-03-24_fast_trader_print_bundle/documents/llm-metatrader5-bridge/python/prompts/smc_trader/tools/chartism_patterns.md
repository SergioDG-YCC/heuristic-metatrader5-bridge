## Tool: Chart Patterns

Use this reference to identify patterns in the context of structure (`market.structure`) and decide actions on positions/orders.

---

### TREND REVERSAL PATTERNS

#### Head and Shoulders (H&S) — Reliability 93%
- Three peaks: the central one (head) higher than the laterals (shoulders)
- Neckline: connects the two valleys between the peaks
- Confirmation: close below neckline with high volume. Pullback to neckline in ~65% of cases
- Invalidation: price recovers neckline and exceeds the right shoulder
- **Target**: `Neckline − (Head − Neckline)`
- Right shoulder lower than left = higher reliability
- Decreasing volume on each successive peak

#### Inverse Head and Shoulders — Reliability 89%
- Three lows: the central one deepest. Signal of bearish trend exhaustion
- Confirmation: close above neckline with increasing volume. Pullback in ~60%
- Invalidation: price loses neckline and breaks below right shoulder low
- **Target**: `Neckline + (Neckline − Head)`
- Look for bullish divergences in RSI/MACD to confirm

#### Double Top (M) — Reliability 85%
- Two peaks at a similar level (1–3% tolerance) with an intermediate valley
- Second peak with lower volume = buyer weakness
- Confirmation: close below the intermediate valley
- Invalidation: price exceeds both tops with close and volume
- **Target**: `Neckline − (Top − Neckline)`
- Bearish RSI divergence between the two peaks reinforces the signal

#### Double Bottom (W) — Reliability 85%
- Two lows at a similar level. "W" shape
- Second valley with lower volume = decreasing selling pressure
- Confirmation: close above intermediate peak with volume
- Invalidation: price breaks below both bottoms
- **Target**: `Neckline + (Neckline − Bottom)`
- Second bottom slightly higher = aggressive accumulation

#### Triple Top/Bottom — Reliability 88%
- Three failed attempts to break through a level
- Decreasing volume on each attempt = progressive exhaustion
- Less frequent but more reliable than the double
- **Target**: `Neckline ± Pattern_height`

#### Wedges — Reliability 80%
- Converging lines sloped in the same direction
- Rising wedge = bearish (exhaustion). Falling wedge = bullish (accumulation)
- Decreasing volume within the formation
- Ideal breakout: in the final third (2/3 of the way to the apex)
- **Target**: `Breakout_point ± Wedge_base`
- If the breakout exceeds the apex, the signal weakens

---

### CONTINUATION PATTERNS

#### Flags — Reliability 82%
- Short rectangular channel against the main trend, after a strong impulse (pole)
- Ideal duration: 5–15 candles. More than 20 candles weakens the pattern
- Confirmation: breakout of the channel in the pole direction with volume
- **Target**: `Breakout ± Pole_length`
- The flag must slope AGAINST the main trend

#### Pennants — Reliability 80%
- Small symmetrical triangle after a strong impulse
- Must be small relative to the pole (max 1/3 of its length)
- Rapid convergence: 1–2 weeks
- **Target**: `Breakout ± Pole_length`

#### Triangles — Reliability 78%
- Ascending (flat top, rising bottom): bullish bias ~75%
- Descending (flat bottom, falling top): bearish bias ~75%
- Symmetrical: breaks in the direction of the prior trend ~60%
- Ideal breakout between 50% and 75% of the way to the apex
- Breakouts very close to the apex are weak
- **Target**: `Breakout ± Triangle_base`

#### Cup and Handle — Reliability 83%
- Gradual "U" shape (not "V") + minor pullback (handle)
- Handle must not retrace more than 50% of the cup depth
- Ideal handle slopes slightly downward
- **Target**: `Cup_rim + Cup_depth`

---

### BASE STRUCTURES

#### Support and Resistance — Reliability 90%
- Minimum 2 touches, ideally 3+. They are zones, not exact lines
- **Polarity**: broken support → new resistance, and vice versa. The polarity retest is the highest-probability entry
- Levels on higher timeframes take priority
- Round numbers (100, 50, 1000) act as psychological S/R
- False breakouts are common at obvious levels: market makers sweep stops before reversing

#### Channels — Reliability 82%
- Two parallel lines containing price. Minimum 2 touches on each
- Trade internal bounces: buy at channel support, sell at channel resistance
- Downside break of a bullish channel is more significant than an upside break
- **Target**: `Channel_width from breakout point`

---

### UNIVERSAL BREAKOUT RULES

Apply to ALL patterns above:

1. **Volume**: Every valid breakout requires volume > 20-period average. No volume = suspicious
2. **Close vs Wick**: Confirm with candle close, not wick. Wicks that cross and return = rejection
3. **Pullback**: 60–70% of breakouts present a retest of the broken level. This is the highest-probability entry
4. **Polarity**: Broken support → resistance, broken resistance → support
5. **Timeframe**: Breakouts on higher TFs (daily, weekly) are more reliable than lower ones
6. **False breakouts**: Obvious levels generate more false breakouts. Wait for confirmation
7. **Target projection**: Pattern height projected from breakout. Achieved ~70% of the time
8. **Trend context**: Reversal patterns require a clear prior trend. Continuation patterns require a prior impulse (pole)

### APPLICATION FOR SL/TP

When `market.structure` contains swing and breakout data:
- **SL for buy**: below the nearest support/swing_low that validates the pattern
- **SL for sell**: above the nearest resistance/swing_high that validates the pattern
- **TP**: at the projected pattern target or at the next known S/R level
- If `breakout_state` indicates an active breakout, consider whether the position is aligned with the breakout direction
- If `retest_state` indicates a retest in progress, it is a high-probability zone to protect or enter