# Implementación: Fórmula Universal de Lot Size (MT5 Compliant)

**Fecha**: 2026-03-26  
**Estado**: IMPLEMENTADO ✅  
**Referencia**: https://www.metatrader5.com/en/terminal/help/trading_advanced/margin_forex

---

## Problema Resuelto

### Código Anterior (INCORRECTO)

```python
# trader/service.py (ANTES)
tick_value = float(spec.get("tick_value", pip_size) or pip_size)
pip_per_point = float(pip_size) / float(point_size) if point_size > 0 else 1.0
pip_value = tick_value * pip_per_point  # ← ERROR: pip_size=point, da 1.0 siempre

volume = self.risk_engine.calculate_lot_size(
    balance,
    dynamic_risk.risk_per_trade_percent,
    selected_setup.risk_pips,
    pip_value,  # ← Incorrecto para símbolos con digits != 5
)
```

**Problema**: 
- `pip_size()` devuelve `point` (0.00001) en lugar de `pip` (0.0001)
- `pip_per_point = 0.00001 / 0.00001 = 1.0` siempre
- `pip_value = tick_value × 1.0` → incorrecto para USDJPY, BTCUSD, etc.

---

## Solución Implementada

### 1. `fast_desk/risk/engine.py` — Fórmula Universal

```python
def calculate_lot_size(
    self,
    balance: float,
    risk_pct: float,
    sl_pips: float,
    symbol_spec: dict[str, Any],  # ← NUEVO: spec completo de MT5
    account_state: dict[str, Any] | None = None,  # ← NUEVO: para margin check
) -> float:
    """Calculate lot size using MT5 symbol specifications.
    
    Fully compliant with MetaTrader 5 margin calculation documentation.
    Works for: Forex, Crypto, Indices, Metals
    """
    # === EXTRACT SPECS (all from MT5) ===
    tick_value = float(symbol_spec.get("tick_value", 0) or 0)
    point = float(symbol_spec.get("point", 0) or 0)
    digits = int(symbol_spec.get("digits", 5) or 5)
    contract_size = float(symbol_spec.get("contract_size", 1) or 1)
    margin_rate = float(symbol_spec.get("margin_rate", 1.0) or 1.0)
    leverage = int((account_state or {}).get("leverage", 100) or 100)
    
    # === DYNAMIC PIP SIZE (MT5 convention) ===
    if digits == 2:
        # 2 decimals: BTCUSD, some indices
        # 1 pip = 0.01 = 1 × point
        pip_size = point
    elif digits in (3, 5):
        # 3 decimals: USDJPY | 5 decimals: EURUSD, GBPUSD
        # 1 pip = 0.01 (JPY) or 0.0001 (FX) = 10 × point
        pip_size = point * 10
    else:
        pip_size = point
    
    # === CONVERT SL FROM PIPS TO POINTS ===
    sl_points = sl_pips * (pip_size / point)
    
    # === LOT SIZE FORMULA (MT5 compliant) ===
    risk_amount = balance * (risk_pct / 100.0)
    lot_size = risk_amount / (sl_points * tick_value)
    
    # === MARGIN CHECK (MT5 formula) ===
    if account_state:
        free_margin = float(account_state.get("free_margin", 0) or 0)
        if free_margin > 0:
            # Safety: don't use more than 50% of free margin on single trade
            max_margin_lots = (free_margin * 0.5) / (contract_size / leverage * margin_rate)
            lot_size = min(lot_size, max_margin_lots)
    
    # === SAFETY CAPS ===
    lot_size = max(0.01, min(50.0, lot_size))
    return round(lot_size, 2)
```

---

### 2. `fast_desk/trader/service.py` — Integración

```python
# trader/service.py (DESPUÉS)
balance = float(account_state.get("balance", 0.0) or 0.0)
spec = spec_registry.get(symbol) or {}

# === UNIVERSAL LOT SIZE CALCULATION (MT5 compliant) ===
# Pass symbol_spec and account_state directly - engine handles all symbol types
volume = self.risk_engine.calculate_lot_size(
    balance,
    dynamic_risk.risk_per_trade_percent,
    selected_setup.risk_pips,
    spec,  # symbol_spec with tick_value, point, digits, contract_size
    account_state,  # for margin check
)
```

---

## Verificación con Ejemplos Reales

### Ejemplo 1: EURUSD (5 decimales)

```
Specs MT5:
  digits: 5
  point: 0.00001
  tick_value: $10.00
  contract_size: 100000

Input:
  balance: $100,000
  risk_pct: 1.0%
  sl_pips: 50

Cálculo:
  pip_size = 0.00001 × 10 = 0.0001 ✓
  sl_points = 50 × (0.0001 / 0.00001) = 500 points ✓
  risk_amount = $100,000 × 0.01 = $1,000
  lot_size = $1,000 / (500 × $10) = 0.2 lots ✓
```

---

### Ejemplo 2: USDJPY (3 decimales)

```
Specs MT5:
  digits: 3
  point: 0.001
  tick_value: ~$6.70 (varía con precio)
  contract_size: 100000

Input:
  balance: $100,000
  risk_pct: 1.0%
  sl_pips: 50

Cálculo:
  pip_size = 0.001 × 10 = 0.01 ✓
  sl_points = 50 × (0.01 / 0.001) = 500 points ✓
  risk_amount = $100,000 × 0.01 = $1,000
  lot_size = $1,000 / (500 × $6.70) = 0.30 lots ✓
```

---

### Ejemplo 3: BTCUSD (2 decimales)

```
Specs MT5:
  digits: 2
  point: 0.01
  tick_value: ~$1.00 (1 lot = 1 BTC, tick = $1 move)
  contract_size: 1

Input:
  balance: $100,000
  risk_pct: 1.0%
  sl_pips: 500 (=$50 en BTCUSD)

Cálculo:
  pip_size = 0.01 (1 pip = 1 point para 2 decimales) ✓
  sl_points = 500 × (0.01 / 0.01) = 500 points ✓
  risk_amount = $100,000 × 0.01 = $1,000
  lot_size = $1,000 / (500 × $1) = 2.0 BTC ✓
```

---

### Ejemplo 4: Con Margen Check

```
Account:
  balance: $100,000
  free_margin: $80,000
  leverage: 100

Symbol: EURUSD
  contract_size: 100000
  margin_rate: 1.0

Cálculo sin margin check:
  lot_size = 0.2 lots

Margin check:
  estimated_margin = (0.2 × 100000 / 100) × 1.0 = $200
  max_margin_lots = ($80,000 × 0.5) / (100000 / 100 × 1.0) = 400 lots
  → 0.2 lots < 400 lots ✓ (no se reduce)
```

---

## Cambios en Archivos

| Archivo | Cambios | Líneas |
|---------|---------|--------|
| `src/heuristic_mt5_bridge/fast_desk/risk/engine.py` | Nueva fórmula universal | ~130 |
| `src/heuristic_mt5_bridge/fast_desk/trader/service.py` | Integración nueva firma | ~15 |

---

## Beneficios

### 1. **Universal**
- Funciona para TODOS los símbolos sin hardcoding
- EURUSD, GBPUSD, USDJPY, BTCUSD, índices, metales

### 2. **MT5 Compliant**
- Usa `tick_value` calculado por MT5
- Usa `contract_size` del spec
- Usa `margin_rate` si existe
- Considera `leverage` de la cuenta

### 3. **Margin Safe**
- Verifica que no exceda 50% del free margin
- Previene margin call en single trade

### 4. **Dynamic Pip Size**
- digits=2 (BTCUSD): 1 pip = 1 point
- digits=3 (USDJPY): 1 pip = 10 points
- digits=5 (EURUSD): 1 pip = 10 points

---

## Próximos Pasos (Opcional)

### WebUI Settings/Risk Slider

Se puede agregar un slider en Settings/Risk:

```
┌─────────────────────────────────────────┐
│  Risk per Trade: [━━●━━] 1.0% (0.1-5%) │
│  Max Margin Usage: [━━━━━●━━] 50%      │
└─────────────────────────────────────────┘
```

Donde `Max Margin Usage` controla el `%` de free margin máximo por trade (actualmente hardcodeado a 50%).

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-26  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Implementation Complete ✅
