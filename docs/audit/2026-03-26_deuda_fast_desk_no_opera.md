# Deuda Técnica — Fast Desk No Opera

**Fecha**: 2026-03-26  
**Estado**: PENDIENTE — INVESTIGACIÓN REQUERIDA  
**Prioridad**: CRÍTICA

---

## Resumen Ejecutivo

El **Fast Desk está habilitado y corriendo** pero **NO genera ninguna operación**. Los logs muestran:

```
[fast-desk] worker started: BTCUSD
[fast-desk] worker started: EURUSD
...
```

Pero la DB muestra:
```
Total signals in DB: 0
❌ NO SIGNALS IN DB - Fast Desk is not detecting setups
```

---

## Lo que SÍ Funciona

| Componente | Estado | Evidencia |
|------------|--------|-----------|
| **Backend** | ✅ UP | `status=up`, `health=up` |
| **MT5 Connector** | ✅ UP | Broker: FBS-Demo, Account: 105845678 |
| **Indicator Bridge** | ✅ HEALTHY | `indicator=healthy`, archivos .json se crean/borran |
| **SMC Desk** | ✅ OPERA | `analyst done EURUSD bias=bearish`, `candidates=1` |
| **Fast Desk Workers** | ✅ CORREN | `worker started: BTCUSD, EURUSD, ...` |
| **Risk Kernel** | ✅ CONFIG | Profile global=4, fast=2 |
| **Symbol Specs** | ✅ DISPONIBLES | EURUSD, GBPUSD, USDJPY, BTCUSD con specs correctas |

---

## Lo que NO Funciona

| Componente | Estado | Síntoma |
|------------|--------|---------|
| **Fast Desk Operations** | ❌ CERO OPERACIONES | `fast_desk_signals = 0 rows` en DB |
| **Broker Sessions Service** | ❌ ERROR 5273 | `SendFramed(pull) failed err=5273` en MT5 |

---

## Diagnóstico del Problema

### Fast Desk Pipeline

El Fast Desk sigue este pipeline:

```
1. build_context() → ¿allowed=true?
2. detect_setups() → ¿setups detectados?
3. confirm() → ¿trigger confirmado?
4. can_open() → ¿entry policy permite?
5. calculate_lot_size() → ¿lot size válido?
6. send_entry() → ¿orden ejecutada?
```

**Cualquiera de estos 6 pasos puede estar bloqueando.**

---

## Hipótesis de Bloqueo

### Hipótesis 1: Session Gate (MÁS PROBABLE)

**Configuración actual**:
```
allowed_sessions: ['london', 'overlap', 'new_york']
```

**Hora actual**: 06:33 UTC = **Tokyo session** (23:00-06:59 UTC)

**Problema**: Tokyo NO está en `allowed_sessions`.

**Verificación**:
```python
# En context/service.py línea ~101
if "global" not in cfg.allowed_sessions and "all_markets" not in cfg.allowed_sessions:
    if session_name not in set(cfg.allowed_sessions):
        reasons.append(f"session_blocked:{session_name}")
        return FastContext(..., allowed=False, reasons=reasons)
```

**Solución**: Agregar `tokyo` a `allowed_sessions` o seleccionar `Global (24h)` en Settings.

---

### Hipótesis 2: Require H1 Alignment

**Configuración actual**:
```
require_h1_alignment: True
```

**Problema**: Si el H1 bias es `neutral` o no coincide con el setup, se filtra.

**Verificación**:
```python
# En trader/service.py línea ~117
if self.trader_config.require_h1_alignment and context.h1_bias in {"buy", "sell"} and setup.side != context.h1_bias:
    continue  # ← FILTRADO
```

**Solución**: Desactivar `require_h1_alignment` en Settings.

---

### Hipótesis 3: Spread Tolerance

**Configuración actual**:
```
spread_tolerance: medium
```

**Problema**: Si el spread actual excede el threshold para `medium`, se bloquea.

**Thresholds medium**:
- forex_major: 0.04%
- forex_minor: 0.08%
- crypto: 0.25%

**Verificación**: Revisar logs del backend por `spread_exceeded`.

**Solución**: Cambiar a `spread_tolerance: high`.

---

### Hipótesis 4: No Setups Detectados

**Problema**: El mercado actual no tiene patrones detectables por el setup engine.

**Setups que detecta**:
- order_block_retest
- liquidity_sweep_reclaim
- breakout_retest
- wedge patterns

**Verificación**: Agregar logging en `setup_engine.detect_setups()`.

**Solución**: Esperar condiciones de mercado más favorables o ajustar parámetros.

---

### Hipótesis 5: Entry Policy Bloquea

**Problema**: `FastEntryPolicy.can_open()` puede estar bloqueando por límites de posiciones.

**Verificación**: Revisar `entry_policy.py`.

---

### Hipótesis 6: Risk Gate Bloquea

**Problema**: `risk_gate_ref()` puede estar retornando `allowed=False`.

**Verificación**: Revisar logs del Risk Kernel.

---

## Plan de Investigación

### Paso 1: Agregar Logging Detallado

Agregar logs en `trader/service.py`:

```python
# Línea ~95
if not context.allowed:
    print(f"[fast-desk] CONTEXT BLOCKED ({symbol}): {context.reasons}")
    return None

# Línea ~103
if not setups:
    print(f"[fast-desk] NO SETUPS ({symbol}/{timeframe})")
    return None

# Línea ~120
if selected_setup is None or selected_trigger is None:
    print(f"[fast-desk] NO TRIGGER CONFIRMED ({symbol})")
    return None

# Línea ~135
if not allowed:
    print(f"[fast-desk] ENTRY POLICY BLOCKED ({symbol}/{side})")
    return None
```

### Paso 2: Verificar Session Actual

En Settings → Fast Desk Configuration:
- **Cambiar** `Allowed Market Sessions` a `Global (24h)`
- **Guardar**
- **Reiniciar backend**
- **Verificar logs**

### Paso 3: Verificar H1 Bias

En logs del backend, buscar:
```
context.h1_bias=neutral  # ← Si es neutral, bloquea setups
```

### Paso 4: Verificar Spread

En logs del backend, buscar:
```
spread_exceeded:0.05%>0.04%  # ← Spread actual > threshold
```

---

## Error 5273 (Broker Sessions Service)

**NO BLOQUEA EL FAST DESK** — es un error separado.

**Causa**: `LLMBrokerSessionsService` intenta hacer WebRequest pero falla.

**Impacto**: Nulo para el Fast Desk — el Broker Sessions Service es opcional.

**Solución**: 
1. Verificar URL en MT5 Options → Experts → WebRequest
2. O desactivar `BROKER_SESSIONS_ENABLED=false` en `.env`

---

## Acciones Inmediatas Recomendadas

### 1. Cambiar Allowed Sessions a Global (24h)

**En Settings WebUI**:
- Fast Desk Configuration → Allowed Market Sessions
- Marcar `Global (24h)`
- Guardar

**O en `.env`**:
```ini
FAST_DESK_ALLOWED_SESSIONS=global
```

### 2. Desactivar Require H1 Alignment

**En Settings WebUI**:
- Fast Desk Configuration → Require H1 Alignment
- Desmarcar

**O en `.env`**:
```ini
FAST_DESK_REQUIRE_H1_ALIGNMENT=false
```

### 3. Cambiar Spread Tolerance a High

**En Settings WebUI**:
- Fast Desk Configuration → Spread Tolerance
- Seleccionar `High (Aggressive)`

**O en `.env`**:
```ini
FAST_DESK_SPREAD_TOLERANCE=high
```

### 4. Reiniciar Backend

```powershell
# Ctrl+C
python apps/control_plane.py
```

### 5. Monitorear Logs

Buscar logs como:
```
[fast-desk] CONTEXT BLOCKED (EURUSD): ['session_blocked:tokyo']
[fast-desk] NO SETUPS (EURUSD/M5)
[fast-desk] NO TRIGGER CONFIRMED (GBPUSD)
```

---

## Estado Actual

| Ítem | Estado | Notas |
|------|--------|-------|
| Indicator Bridge | ✅ IMPLEMENTADO | EA escribe/lee snapshots correctamente |
| Fast Desk Workers | ✅ CORRIENDO | Workers activos por símbolo |
| Fast Desk Operations | ❌ CERO OPERACIONES | Bloqueado en algún gate |
| Broker Sessions Error | ⚠️ NO BLOQUEANTE | Error 5273 no afecta Fast Desk |
| SMC Desk | ✅ OPERA | Genera análisis y candidatos |

---

## Próximos Pasos

1. **Cambiar Allowed Sessions a Global (24h)** ← MÁS PROBABLE
2. **Agregar logging detallado** en trader/service.py
3. **Reiniciar backend**
4. **Monitorear logs** por mensajes de bloqueo
5. **Ajustar configuración** según logs

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-26  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Investigation Required 🔍
