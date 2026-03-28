# Plan Estructural: Sessions, Spread y Risk — Modificación Integral

> **Estado:** IMPLEMENTADO ✅  
> **Fecha:** 2025-07-21 (plan) → 2026-03-25 (implementación completa)  
> **Alcance:** FastDesk + SMC Desk + Core Risk + Control Plane API + WebUI Settings  
> **Tests:** 116 passing (97 existentes + 19 nuevos session/spread + 2 nuevos risk kernel)

---

## Correcciones Aplicadas Post-Aprobación

1. **Spread thresholds editables desde WebUI** — La tabla `_SPREAD_THRESHOLDS` ya no es constante module-level. Ahora es un campo mutable `spread_thresholds` en `FastContextConfig` y `SmcAnalystConfig`, editable via API+WebUI con validación de estructura.
2. **Sin tramo "unknown"** — `session_name_from_timestamp()` cubre 24h (tokyo 23-06, london 7-12, overlap 13-16, new_york 17-22). Los horarios operables los fija la especificación de cada símbolo (`trade_mode` del spec), no se asume que a cierta hora no se puede operar.
3. **Risk panel editable** — Los effective limits del panel Global son editables como overrides directos. Desk limits son computed (read-only). API `PUT /api/v1/config/risk` acepta `overrides: dict[str, float]`.
4. **Spread tolerance por separado para cada mesa** — SMC Desk tiene su propio `spread_tolerance` + `spread_thresholds` en `SmcAnalystConfig`, independiente de Fast Desk. SMC usa "high" como default (trades de largo plazo toleran spreads más amplios).

---

## Contexto

Tres subsistemas están operando con valores hardcodeados que bloquean el funcionamiento real del sistema:

1. **Sessions** — `allowed_sessions = ("london", "overlap", "new_york")` hardcodeado en `FastContextConfig`. No hay variable de entorno, no hay endpoint API, no hay control WebUI. Resultado: fuera de esos rangos UTC el sistema no opera.
2. **Spread** — Umbral fijo en pips (`max_spread_pips=3.0` forex / `max_spread_pct=0.5` non-forex). No diferencia entre EURUSD, USDJPY, BTCUSD. En horarios de bajo volumen los spreads se amplían y el filtro es demasiado rígido o demasiado laxo según el símbolo.
3. **Risk Profiles** — WebUI muestra sólo selectores de perfil (1-4) y kill switch. No expone: budget weights, effective limits calculados, overrides, allocator state. El endpoint `GET /api/v1/config/risk` busca un `to_dict()` que no existe en RiskKernel y cae al fallback con sólo 3 campos.

---

## Objetivo

Modificación estructural que convierte los tres sistemas en configurables, observables y coherentes entre sí, con persistencia en DB y exposición completa en WebUI.

---

## BLOQUE A — Market Sessions (Solo Fast Desk)

> **Alcance:** Estas reglas de sesión aplican **exclusivamente a la Mesa Fast**.
> La Mesa SMC por diseño opera globalmente — no está limitada por horarios de mercado.
> El único limitante para SMC es el horario del símbolo concreto (si el broker lo marca como cerrado).
> SMC nunca se bloquea por sesión de mercado; sus estrategias deciden cuándo operar.

### A.1 Modelo de Datos

Definir en `FastContextConfig` y `FastDeskConfig` (solo Fast Desk):

```
allowed_sessions: tuple[str, ...]
```

Valores válidos para cada elemento del tuple:
| Valor | Significado |
|-------|-------------|
| `"tokyo"` | UTC 00:00–06:59 |
| `"london"` | UTC 07:00–12:59 |
| `"overlap"` | UTC 13:00–16:59 |
| `"new_york"` | UTC 17:00–21:59 |
| `"all_markets"` | Equivale a `("tokyo","london","overlap","new_york")` — todo horario conocido |
| `"global"` | Opera 24h incluyendo el tramo `unknown` (22:00–23:59). Sólo se detiene si el símbolo concreto está marcado como cerrado por SymbolSpec |

La lógica `session_name_from_timestamp()` ya define las 5 ventanas (tokyo, london, overlap, new_york, unknown). No se modifica la función — se modifica cómo se evalúa la pertenencia.

### A.2 Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `fast_desk/context/service.py` | En `build_context()`: si `cfg.allowed_sessions` contiene `"global"` → skip session check (sólo respetar symbol spec closed). Si contiene `"all_markets"` → expandir a las 4 sesiones. Si no → comportamiento actual (check membership). |
| `fast_desk/runtime.py` → `FastDeskConfig` | Agregar campo `allowed_sessions: tuple[str, ...] = ("london", "overlap", "new_york")`. Cargar desde env `FAST_TRADER_ALLOWED_SESSIONS` (comma-separated). Propagar a `FastContextConfig`. Incluir en `to_dict()`. |
| `fast_desk/runtime.py` → `FastDeskConfig.from_env()` | Parsear `FAST_TRADER_ALLOWED_SESSIONS` string como tuple. Validar valores contra set permitido. |
| `apps/control_plane.py` | Agregar `allowed_sessions: list[str] | None` a `FastConfigUpdateRequest`. En `PUT /api/v1/config/fast`: si viene, actualizar `cfg.allowed_sessions` + re-crear `context_config` de workers activos. En `GET`: ya se expone via `to_dict()`. |
| `apps/webui/src/routes/Settings.tsx` | En el panel "Fast Desk Configuration": agregar multi-select con checkboxes para las 6 opciones (tokyo, london, overlap, new_york, all_markets, global). Si se selecciona `global` → deshabilitar el resto. Si se selecciona `all_markets` → marcar las 4 automáticamente. Incluir nota visible: _"Aplica solo a Fast Desk. La Mesa SMC opera globalmente sin restricción de horario de mercado."_ |
| `configs/base.env.example` | Agregar `FAST_TRADER_ALLOWED_SESSIONS=london,overlap,new_york` |

### A.3 Lógica de Evaluación Resultante

```python
# En build_context()
if "global" in cfg.allowed_sessions:
    # Sólo verificar que el símbolo no esté cerrado (symbol_spec trade_mode)
    if symbol_spec and symbol_spec.get("trade_mode", 0) == 0:
        reasons.append("symbol_closed")
elif "all_markets" in cfg.allowed_sessions:
    if session_name == "unknown":
        reasons.append(f"session_blocked:{session_name}")
else:
    if session_name not in set(cfg.allowed_sessions):
        reasons.append(f"session_blocked:{session_name}")
```

### A.4 Nota en WebUI

En el panel Fast Desk Configuration, junto al multi-select de sessions, mostrar:

```
ℹ️ Session filtering applies to Fast Desk only.
   SMC Desk operates globally — only restricted by symbol trading hours.
```

### A.5 Tests a Agregar

- Test con `global`: no bloquea ninguna hora, bloquea symbol con `trade_mode=0`
- Test con `all_markets`: permite tokyo/london/overlap/new_york, bloquea unknown
- Test con subset: comportamiento actual
- Test de parsing env: `"tokyo,london"` → `("tokyo","london")`
- Test que SMC desk no tiene session filtering (no existe `allowed_sessions` en su config)

---

## BLOQUE B — Spread Tolerance (Porcentual, Por Símbolo)

### B.1 Nuevo Modelo de Tolerancia

Reemplazar el actual `max_spread_pips: float` por un sistema de **tolerancia porcentual con niveles**:

```python
@dataclass
class SpreadToleranceConfig:
    level: str = "medium"  # "low" | "medium" | "high"
```

Tabla de niveles — porcentaje máximo del mid-price permitido como spread:

| Nivel | Forex Major | Forex Minor/Exotic | Metals (XAU,XAG) | Indices | Crypto |
|-------|------------|-------------------|-------------------|---------|--------|
| `low` | 0.02% | 0.04% | 0.05% | 0.03% | 0.10% |
| `medium` | 0.04% | 0.08% | 0.10% | 0.06% | 0.25% |
| `high` | 0.10% | 0.15% | 0.20% | 0.12% | 0.50% |

La clasificación del símbolo se obtiene del `SymbolSpec` ya disponible en `build_context()`:
- `trade_calc_mode == 0` → Forex. Sub-clasificar: majors por lista (`EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD`) → "forex_major", resto → "forex_minor"
- `trade_calc_mode == 2 / 4` → CFD/Exchange → detectar por prefix/suffix (XAU, XAG → metals; US30, SPX, NAS → indices)
- `trade_calc_mode == 3` → Futures
- Nombre contiene BTC/ETH/LTC/XRP + USD/EUR → crypto

### B.2 Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `fast_desk/context/service.py` | Reemplazar lógica de `spread_exceeded` por: `spread_pct = raw_spread / mid_price * 100`. Lookup asset_class del symbol. Lookup threshold de la tabla por `(level, asset_class)`. Comparar `spread_pct > threshold`. Mantener `spread_pips` en el contexto para logging. |
| `fast_desk/context/service.py` → `FastContextConfig` | Eliminar `max_spread_pips` y `max_spread_pct`. Agregar `spread_tolerance: str = "medium"`. La tabla de thresholds es un dict constante en el módulo. |
| `fast_desk/runtime.py` → `FastDeskConfig` | Renombrar `spread_max_pips` → `spread_tolerance: str = "medium"`. Cargar desde `FAST_TRADER_SPREAD_TOLERANCE=medium`. Propagar a `FastContextConfig`. Actualizar `to_dict()`. Mantener `spread_max_pips` como legacy alias si se detecta en env (deprecation path). |
| `apps/control_plane.py` | En `FastConfigUpdateRequest`: reemplazar `spread_max_pips: float | None` por `spread_tolerance: str | None`. Validar contra `{"low","medium","high"}`. |
| `apps/webui/src/routes/Settings.tsx` | En "Fast Desk Configuration": reemplazar cualquier control de spread existente por un `<select>` con 3 opciones: Low (Conservative), Medium (Normal), High (Aggressive). Con texto explicativo: "Controla la tolerancia al spread por tipo de activo. Low rechaza spreads altos, High permite operar con spreads más amplios." |
| `configs/base.env.example` | Reemplazar `FAST_TRADER_SPREAD_MAX_PIPS=3.0` por `FAST_TRADER_SPREAD_TOLERANCE=medium` |

### B.3 Helper de Clasificación de Asset

Nuevo helper en `context/service.py` (función module-level, no clase nueva):

```python
_FOREX_MAJORS = {"EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD"}
_CRYPTO_TOKENS = {"BTC","ETH","LTC","XRP","SOL","ADA","DOT","DOGE","BNB"}

def _classify_asset(symbol: str, spec: dict | None) -> str:
    """Return asset class: forex_major, forex_minor, metals, indices, crypto, other."""
    sym = symbol.upper()
    calc_mode = int((spec or {}).get("trade_calc_mode", -1))
    if calc_mode == 0:
        return "forex_major" if sym in _FOREX_MAJORS else "forex_minor"
    # Check crypto by name pattern
    if any(tok in sym for tok in _CRYPTO_TOKENS):
        return "crypto"
    # Metals
    if any(m in sym for m in ("XAU","XAG","GOLD","SILVER")):
        return "metals"
    # Indices - common patterns
    if any(idx in sym for idx in ("US30","SPX","NAS","DAX","FTSE","JP225","US500","US100","US2000")):
        return "indices"
    return "other"
```

### B.4 Tabla de Thresholds (constante module-level)

```python
_SPREAD_THRESHOLDS: dict[str, dict[str, float]] = {
    "low":    {"forex_major": 0.02, "forex_minor": 0.04, "metals": 0.05, "indices": 0.03, "crypto": 0.10, "other": 0.05},
    "medium": {"forex_major": 0.04, "forex_minor": 0.08, "metals": 0.10, "indices": 0.06, "crypto": 0.25, "other": 0.10},
    "high":   {"forex_major": 0.10, "forex_minor": 0.15, "metals": 0.20, "indices": 0.12, "crypto": 0.50, "other": 0.20},
}
```

### B.5 Lógica de Evaluación Resultante

```python
# En build_context() — reemplaza la sección actual de spread check
spread_exceeded = False
spread_pct = 0.0
if bid > 0 and ask > 0:
    mid_price = (bid + ask) / 2.0
    raw_spread = ask - bid
    spread_pct = (raw_spread / mid_price) * 100.0
    spread_pips = raw_spread / pip_size if pip_size > 0 else 0.0  # para logging

    asset_class = _classify_asset(symbol, symbol_spec)
    level = cfg.spread_tolerance  # "low", "medium", "high"
    threshold_pct = _SPREAD_THRESHOLDS.get(level, _SPREAD_THRESHOLDS["medium"]).get(asset_class, 0.10)
    spread_exceeded = spread_pct > threshold_pct

if spread_exceeded:
    reasons.append(f"spread_exceeded:{spread_pct:.4f}%>{threshold_pct:.4f}%")
```

### B.6 Tests a Agregar

- Test `_classify_asset`: EURUSD→forex_major, EURAUD→forex_minor, BTCUSD→crypto, XAUUSD→metals, US30→indices
- Test spread threshold por nivel: Low rechaza 0.05% en forex_major, Medium acepta, High acepta
- Test spread threshold crypto: 0.30% rechazado en low/medium, aceptado en high
- Test legacy: si `FAST_TRADER_SPREAD_MAX_PIPS` está en env sin `SPREAD_TOLERANCE`, usar fallback "medium"

---

## BLOQUE C — Risk Profiles: Exposición Completa en WebUI

### C.1 Problema Actual

1. `GET /api/v1/config/risk` busca `to_dict()` que no existe → fallback devuelve sólo 3 campos (profiles)
2. WebUI sólo muestra: 3 profile selectors + kill switch
3. **No visible**: `fast_budget_weight`, `smc_budget_weight`, effective limits, allocator state, overrides

### C.2 Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `core/risk/kernel.py` | Agregar método `to_dict()` que retorne toda la configuración serializable: profiles, weights, kill_switch_enabled, overrides, effective_limits, allocator_state. Ahora `GET /api/v1/config/risk` usará el path principal en lugar del fallback. |
| `apps/control_plane.py` | `RiskConfigUpdateRequest` ya tiene `fast_budget_weight` y `smc_budget_weight` — OK. Verificar que la respuesta de `GET` incluya todo via `to_dict()`. |
| `apps/webui/src/routes/Settings.tsx` | Expandir panel "Risk Configuration" con: |

### C.3 Nuevo contenido del panel Risk en WebUI

```
┌──────────────── Risk Configuration ────────────────┐
│                                                      │
│  ── Profiles ──                                      │
│  Global Profile:  [1-Low ▾ 2-Medium ▾ 3-High ▾ 4]  │
│  Fast Desk Profile: [selector]                       │
│  SMC Desk Profile:  [selector]                       │
│                                                      │
│  ── Budget Allocation ──                             │
│  Fast Budget Weight: [slider 0.1 — 3.0] actual: 1.2 │
│  SMC Budget Weight:  [slider 0.1 — 3.0] actual: 0.8 │
│  ┌─ Computed Allocation ──────────────────────────┐  │
│  │ Fast Share: 60.0%  │  SMC Share: 40.0%         │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ── Effective Limits (read-only) ──                  │
│  ┌─ Global ───────────────────────────────────────┐  │
│  │ Max Drawdown: 15.0%  Max Risk/Trade: 2.0%      │  │
│  │ Max Positions: 20    Max Per Symbol: 5          │  │
│  │ Max Pending: 20      Max Gross Exp: 20.0        │  │
│  └────────────────────────────────────────────────┘  │
│  ┌─ Fast Desk ────────────────────────────────────┐  │
│  │ Max Drawdown: 15.0%  Max Risk/Trade: 1.2%      │  │
│  │ Max Positions: 12    Max Per Symbol: 5          │  │
│  │ Max Pending: 12      Max Gross Exp: 12.0        │  │
│  └────────────────────────────────────────────────┘  │
│  ┌─ SMC Desk ─────────────────────────────────────┐  │
│  │ Max Drawdown: 15.0%  Max Risk/Trade: 0.8%      │  │
│  │ Max Positions: 8     Max Per Symbol: 5          │  │
│  │ Max Pending: 8       Max Gross Exp: 8.0         │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ── Safety ──                                        │
│  [✓] Kill Switch Enabled                             │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### C.4 `RiskKernel.to_dict()` — Nuevo Método

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "profile_global": self.profile_global,
        "profile_fast": self.profile_fast,
        "profile_smc": self.profile_smc,
        "fast_budget_weight": self.fast_budget_weight,
        "smc_budget_weight": self.smc_budget_weight,
        "kill_switch_enabled": self.kill_switch_enabled,
        "overrides": dict(self.overrides),
        "effective_limits": self.effective_limits(),
        "allocator": self.allocator_state(),
    }
```

### C.5 Tests a Agregar

- Test `to_dict()` retorna todos los campos esperados
- Test que `effective_limits` se recalcula al cambiar profile/weight
- Test API `GET /api/v1/config/risk` retorna estructura completa

---

## BLOQUE D — Integración Coherente

### D.1 Propagación en Caliente

Cuando un parámetro se modifica via API/WebUI, los workers activos deben recibir el cambio sin reiniciar:

| Parámetro | Propagación |
|-----------|-------------|
| `allowed_sessions` | `FastDeskConfig` se muta → workers leen `context_config` en cada ciclo de scan. Se necesita que `FastContextConfig` sea referenciado (no copiado) por los workers, O que se implemente `reload_config()` en los workers. **Decisión**: mutar `FastDeskConfig` en memoria y re-crear `context_config` — los workers ya acceden a it por referencia. |
| `spread_tolerance` | Mismo mecanismo que sessions — viaja en `FastContextConfig`. |
| `budget_weight` | RiskKernel ya es singleton en runtime → cambio inmediato en `evaluate_entry()`. |
| `profiles` | RiskKernel ya persiste y ya es usado live. Sin cambio. |

### D.2 Verificar Propagación de Context Config a Workers

En `fast_desk/runtime.py`, `FastDeskService.run_forever()` crea `context_config` una vez (línea ~173) y lo pasa a los workers. Para que cambios via API se reflejen, se necesita que `PUT /api/v1/config/fast` no sólo mute `FastDeskConfig` sino también actualice el `context_config` compartido.

**Solución**: Almacenar referencia a `context_config` en `FastDeskService` y exponer `update_context_config()`. El endpoint `PUT /api/v1/config/fast` invoca este método. Los workers leen la config al inicio de cada `scan_and_execute()` cycle.

### D.3 API Client WebUI

Verificar que `apps/webui/src/api/client.ts` exponga los métodos necesarios para los nuevos campos. Los endpoints ya existen (`GET/PUT /api/v1/config/fast`, `GET/PUT /api/v1/config/risk`) — sólo se agregan campos a los request/response models.

---

## Orden de Implementación

| Paso | Bloque | Descripción | Dependencias |
|------|--------|-------------|--------------|
| 1 | C | `RiskKernel.to_dict()` + fix `GET /api/v1/config/risk` | Ninguna |
| 2 | C | WebUI: expandir panel Risk con weights, effective limits | Paso 1 |
| 3 | A | `FastDeskConfig.allowed_sessions` + env + `from_env()` + `to_dict()` | Ninguna |
| 4 | A | Lógica `build_context()` con global/all_markets | Paso 3 |
| 5 | A | API: `FastConfigUpdateRequest.allowed_sessions` + endpoint | Paso 3 |
| 6 | A | WebUI: multi-select sessions | Paso 5 |
| 7 | B | `_classify_asset()` + `_SPREAD_THRESHOLDS` + nueva lógica spread | Ninguna |
| 8 | B | `FastDeskConfig.spread_tolerance` + env + deprecation path | Paso 7 |
| 9 | B | API: `spread_tolerance` en request model | Paso 8 |
| 10 | B | WebUI: selector spread tolerance | Paso 9 |
| 11 | D | Propagación caliente de context_config a workers | Pasos 4, 8 |
| 12 | ALL | Tests completos: sessions, spread, risk to_dict, propagation | Todos |

---

## Archivos Afectados (Consolidado)

| Archivo | Bloques |
|---------|---------|
| `src/heuristic_mt5_bridge/fast_desk/context/service.py` | A, B |
| `src/heuristic_mt5_bridge/fast_desk/runtime.py` | A, B, D |
| `src/heuristic_mt5_bridge/core/risk/kernel.py` | C |
| `apps/control_plane.py` | A, B, C |
| `apps/webui/src/routes/Settings.tsx` | A, B, C |
| `apps/webui/src/api/client.ts` | verificar |
| `configs/base.env.example` | A, B |
| `tests/fast_desk/test_context_service.py` | A, B |
| `tests/core/test_risk_kernel.py` | C |

---

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Clasificación errónea de asset class → threshold incorrecto | Fallback a "other" con thresholds conservadores. Log del asset_class detectado. |
| Workers no reciben cambio de sessions/spread en caliente | Implementar `update_context_config()` en FastDeskService, no copiar config. |
| Legacy env `FAST_TRADER_SPREAD_MAX_PIPS` presente → confusión | Si está presente sin `SPREAD_TOLERANCE`, mapear a "medium" + log warning. |
| `to_dict()` en RiskKernel expone datos sensibles | Solo datos de configuración, no credenciales. API ya es local. |

---

## Confirmación Requerida

Antes de implementar, confirmar:

1. ¿Los thresholds de spread de la tabla son adecuados? (Se pueden ajustar post-implementación via la tabla `_SPREAD_THRESHOLDS`)
2. ¿Se mantiene el tramo "unknown" (22-23 UTC) como bloqueado en `all_markets` y sólo permitido en `global`?
3. ¿El panel Risk muestra effective limits como read-only, o se quiere poder editar overrides directamente desde WebUI?
4. ¿Se necesita spread tolerance separado para FastDesk y SMC Desk, o uno global es suficiente?
