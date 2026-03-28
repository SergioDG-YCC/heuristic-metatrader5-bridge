# Runtime Configuration API — Execution Report

**Fecha**: 2026-03-25  
**Estado**: Phase 1-4 Completadas ✅  
**Próximo**: Phase 5 (WebUI Settings Screen)

---

## Resumen de Cambios

Se implementó una API de configuración runtime que permite:

1. **Descubrir modelos LLM disponibles** en LocalAI
2. **Cambiar configuración de SMC Desk** sin restart
3. **Cambiar configuración de Fast Desk** sin restart
4. **Cambiar configuración de Ownership** sin restart
5. **Cambiar configuración de RiskKernel** sin restart

---

## Archivos Creados

### 1. `src/heuristic_mt5_bridge/core/llm/model_discovery.py`

Nuevo módulo para descubrimiento de modelos LLM:

```python
LLMModelDiscovery
  - list_models() → list[LLMModel]
  - get_default_model() → str | None
  - set_default_model(model_id) → bool
  - get_status() → LLMStatus
```

### 2. `src/heuristic_mt5_bridge/core/llm/__init__.py`

Exporta el módulo de descubrimiento.

---

## Archivos Modificados

### 1. `apps/control_plane.py`

**Imports agregados**:
```python
import os
from fastapi import Request
from heuristic_mt5_bridge.core.llm.model_discovery import LLMModelDiscovery
```

**Request Models agregados**:
- `LLMModelSetRequest`
- `SMCConfigUpdateRequest`
- `FastConfigUpdateRequest`
- `OwnershipConfigUpdateRequest`
- `RiskConfigUpdateRequest`

**Endpoints nuevos** (12 endpoints):

| Método | Ruta | Propósito |
|--------|------|-----------|
| `GET` | `/api/v1/llm/models` | Listar modelos LLM disponibles |
| `GET` | `/api/v1/llm/status` | Estado del servicio LLM |
| `PUT` | `/api/v1/llm/models/default` | Cambiar modelo por defecto |
| `GET` | `/api/v1/config/smc` | Obtener config SMC Desk |
| `PUT` | `/api/v1/config/smc` | Actualizar config SMC Desk |
| `GET` | `/api/v1/config/fast` | Obtener config Fast Desk |
| `PUT` | `/api/v1/config/fast` | Actualizar config Fast Desk |
| `GET` | `/api/v1/config/ownership` | Obtener config Ownership |
| `PUT` | `/api/v1/config/ownership` | Actualizar config Ownership |
| `GET` | `/api/v1/config/risk` | Obtener config RiskKernel |
| `PUT` | `/api/v1/config/risk` | Actualizar config RiskKernel |

### 2. `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`

**Agregado a `SmcAnalystConfig`**:
- Nuevos campos: `llm_max_tokens`, `llm_temperature`, `analyst_cooldown_seconds`
- Método `to_dict()` para serialización API
- Actualizado `from_env()` para leer nuevas variables

### 3. `src/heuristic_mt5_bridge/fast_desk/runtime.py`

**Agregado a `FastDeskConfig`**:
- Método `to_dict()` para serialización API

### 4. `.env`

**Variables nuevas**:
```ini
# SMC LLM
SMC_LLM_MAX_TOKENS=500
SMC_LLM_TEMPERATURE=0.1

# SMC Desk
SMC_ANALYST_COOLDOWN_SECONDS=300

# Fast Desk
FAST_DESK_SPREAD_MAX_PIPS=3.0
FAST_DESK_MAX_SLIPPAGE_POINTS=30
FAST_DESK_REQUIRE_H1_ALIGNMENT=true
FAST_DESK_ENABLE_PENDING_ORDERS=true
FAST_DESK_ENABLE_STRUCTURAL_TRAILING=true
FAST_DESK_ENABLE_ATR_TRAILING=true
FAST_DESK_ENABLE_SCALE_OUT=false
FAST_DESK_PENDING_TTL_SECONDS=900

# Ownership
OWNERSHIP_AUTO_ADOPT_FOREIGN=true
OWNERSHIP_HISTORY_RETENTION_DAYS=30
```

---

## Cómo Usar la API

### 1. Listar Modelos LLM Disponibles

```bash
curl http://localhost:8765/api/v1/llm/models
```

**Respuesta**:
```json
{
  "status": "success",
  "models": [
    {
      "id": "gemma-3-4b-it-qat",
      "name": "Gemma 3 4B IT QAT",
      "size": "2.5GB",
      "format": "gguf",
      "family": "gemma",
      "parameter_size": "4B",
      "quantization": "Q4_K_M"
    }
  ],
  "count": 1
}
```

### 2. Obtener Estado LLM

```bash
curl http://localhost:8765/api/v1/llm/status
```

**Respuesta**:
```json
{
  "status": "success",
  "localai_url": "http://127.0.0.1:8080",
  "default_model": "gemma-3-4b-it-qat",
  "current_model": "gemma-3-4b-it-qat",
  "llm_enabled": true,
  "available": true,
  "models_count": 1
}
```

### 3. Cambiar Modelo LLM por Defecto

```bash
curl -X PUT http://localhost:8765/api/v1/llm/models/default \
  -H "Content-Type: application/json" \
  -d '{"model_id": "llama-3.1-8b-instruct"}'
```

### 4. Obtener Configuración SMC Desk

```bash
curl http://localhost:8765/api/v1/config/smc
```

**Respuesta**:
```json
{
  "status": "success",
  "config": {
    "max_candidates": 3,
    "min_rr": 2.0,
    "next_review_hint_seconds": 14400,
    "d1_bars": 100,
    "h4_bars": 200,
    "h1_bars": 300,
    "llm_enabled": true,
    "llm_model": "gemma-3-4b-it-qat",
    "llm_timeout_seconds": 120,
    "llm_max_tokens": 500,
    "llm_temperature": 0.1,
    "analyst_cooldown_seconds": 300
  }
}
```

### 5. Actualizar Configuración SMC Desk

```bash
curl -X PUT http://localhost:8765/api/v1/config/smc \
  -H "Content-Type: application/json" \
  -d '{
    "llm_max_tokens": 800,
    "llm_temperature": 0.2,
    "max_candidates": 5
  }'
```

**Respuesta**:
```json
{
  "status": "success",
  "config": { ... config actualizada ... },
  "message": "SMC configuration updated (runtime only, restart to persist to .env)"
}
```

### 6. Obtener/Actualizar Fast Desk Config

```bash
curl http://localhost:8765/api/v1/config/fast

curl -X PUT http://localhost:8765/api/v1/config/fast \
  -H "Content-Type: application/json" \
  -d '{
    "scan_interval": 3.0,
    "risk_per_trade_percent": 0.5,
    "max_positions_total": 6
  }'
```

### 7. Obtener/Actualizar Ownership Config

```bash
curl http://localhost:8765/api/v1/config/ownership

curl -X PUT http://localhost:8765/api/v1/config/ownership \
  -H "Content-Type: application/json" \
  -d '{
    "auto_adopt_foreign": false,
    "history_retention_days": 60
  }'
```

### 8. Obtener/Actualizar RiskKernel Config

```bash
curl http://localhost:8765/api/v1/config/risk

curl -X PUT http://localhost:8765/api/v1/config/risk \
  -H "Content-Type: application/json" \
  -d '{
    "profile_global": 3,
    "profile_fast": 2,
    "profile_smc": 2,
    "fast_budget_weight": 1.5,
    "smc_budget_weight": 0.5,
    "kill_switch_enabled": true
  }'
```

---

## Consideraciones Importantes

### Runtime vs Persistencia

⚠️ **Los cambios via API son solo runtime**. Se pierden al reiniciar el servicio.

Para hacer cambios permanentes:
1. Actualizar via API (efecto inmediato)
2. Editar `.env` manualmente (persistencia)
3. Reiniciar servicio (carga desde `.env`)

### Validación

Los endpoints validan:
- Tipos de datos (int, float, bool)
- Rangos válidos (ej: profile 1-4)
- Valores mínimos/máximos (ej: budget_weight ≥ 0.01)

### Concurrencia

Los cambios se aplican inmediatamente a la configuración en memoria.
No hay locking explícito — cambios concurrentes pueden sobrescribirse.

---

## Próximos Pasos (Phase 5)

### WebUI Settings Screen

Implementar en Solid.js:

1. **LLM Configuration Panel**
   - Model selector dropdown (desde `/api/v1/llm/models`)
   - Max tokens slider
   - Temperature slider
   - Test connection button

2. **SMC Desk Configuration Panel**
   - Max candidates slider
   - Min R:R input
   - Review interval selector
   - LLM enabled toggle

3. **Fast Desk Configuration Panel**
   - Scan interval slider
   - Risk per trade slider
   - Max positions inputs
   - Toggles para features

4. **Ownership Configuration Panel**
   - Auto-adopt toggle
   - History retention days input

5. **Risk Configuration Panel**
   - Profile selectors (1-4)
   - Budget weight sliders
   - Kill switch toggle

---

## Testing Checklist

### ✅ Phase 1-4 Tests

- [x] `GET /api/v1/llm/models` returns model list
- [x] `GET /api/v1/llm/status` returns status
- [x] `PUT /api/v1/llm/models/default` changes default
- [x] `GET /api/v1/config/smc` returns current config
- [x] `PUT /api/v1/config/smc` updates runtime config
- [x] `GET /api/v1/config/fast` returns current config
- [x] `PUT /api/v1/config/fast` updates runtime config
- [x] `GET /api/v1/config/ownership` returns config
- [x] `PUT /api/v1/config/ownership` updates registry
- [x] `GET /api/v1/config/risk` returns risk config
- [x] `PUT /api/v1/config/risk` updates kernel
- [x] Invalid config returns 400 error

---

## Errores Conocidos

| Error | Causa | Solución |
|-------|-------|----------|
| `LocalAI unavailable` | LocalAI no está corriendo | Iniciar LocalAI: `localai.exe` |
| `SMC Desk not configured` | SMC Desk no está habilitado | Setear `SMC_SCANNER_ENABLED=true` |
| `Fast Desk not configured` | Fast Desk no está habilitado | Setear `FAST_DESK_ENABLED=true` |
| `Ownership registry not initialized` | Servicio no inicializado | Reiniciar control plane |
| `RiskKernel not initialized` | Servicio no inicializado | Reiniciar control plane |

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Backend Architect (AI-Assisted)  
**Status**: Phase 1-4 Complete ✅, Phase 5 Pending
