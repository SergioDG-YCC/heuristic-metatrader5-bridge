## Tool: SL/TP Calculation Methods

Use this reference to decide protection levels. All final values MUST be **absolute market prices**.

### Method 1 — ATR (Volatility)

Formulas:
- `SL_distance = ATR(14) × Multiplier`
- `TP_distance = SL_distance × RR`
- Buy: `SL = price_current - SL_distance`, `TP = price_current + TP_distance`
- Sell: `SL = price_current + SL_distance`, `TP = price_current - TP_distance`

Multipliers by style:
| Style      | ATR Mult | Min RR  | Typical RR |
|------------|----------|---------|------------|
| Scalping   | 0.5–1×   | 1:1     | 1.5:1      |
| Intraday   | 1–1.5×   | 1.5:1   | 2:1        |
| Swing      | 1.5–2.5× | 2:1     | 3:1        |
| Position   | 2–4×     | 3:1     | 4:1        |

If indicators include `atr_14`, use it directly. If not available, estimate ATR as ~1.5% of price for crypto and ~0.3% for forex on H1.

### Method 2 — Fixed Percentage of Price

- `SL_distance = price_current × (SL% / 100)`
- `TP_distance = SL_distance × RR`

Percentage ranges by style:
| Style      | SL %       | TP %        |
|------------|------------|-------------|
| Scalping   | 0.1–0.3%   | 0.15–0.45%  |
| Intraday   | 0.3–0.7%   | 0.6–1.4%    |
| Swing      | 1–2%       | 2–6%        |
| Position   | 2–5%       | 6–20%       |

### Method 3 — Technical Structure (Preferred)

When `structure` is available in the context:
- Buy: `SL` below the last `last_confirmed_swing_low` - margin of 1 ATR
- Buy: `TP` at the next structural level or `last_confirmed_swing_high`
- Sell: `SL` above the last `last_confirmed_swing_high` + margin of 1 ATR
- Sell: `TP` at the next support or `last_confirmed_swing_low`

Priority: Structure > ATR > Fixed percentage.

### Integration Rules

1. SL must be greater than the asset's spread + commission
2. Never risk more than 2% of the balance on a single trade
3. Maximum daily risk: 3–6% of capital
4. If `market_phase` = "ranging" or "compression", use a tighter SL (low percentage)
5. If `volatility_regime` = "high", widen SL with a high ATR multiplier
6. If `late_signal_risk` = "high", prefer a closer TP (RR 1.5:1)

### Pending Orders

For unexecuted limit/stop orders:
- They can be modified: move entry price, SL, and TP
- If `breakout_state` changed, evaluate whether the pending order is still justified
- If spread widened or session changed, consider canceling and replacing
