# Deuda Técnica — WebUI Settings Endpoints PUT

**Fecha**: 2026-03-25  
**Estado**: PENDIENTE  
**Prioridad**: MEDIA

---

## Problema

Los endpoints GET de configuración funcionan correctamente:
- `GET /api/v1/config/smc` → ✅ 200 (retorna config desde .env)
- `GET /api/v1/config/fast` → ✅ 200 (retorna config desde .env)
- `GET /api/v1/config/ownership` → ✅ 200
- `GET /api/v1/config/risk` → ✅ 200

Pero los endpoints PUT fallan:
- `PUT /api/v1/config/smc` → ❌ 503 Service Unavailable
- `PUT /api/v1/config/fast` → ❌ 503 Service Unavailable
- `PUT /api/v1/llm/models/default` → ❌ 500 Internal Server Error

---

## Causa Raíz

### SMC/Fast PUT Endpoints

Los endpoints PUT verifican si el desk está inicializado:

```python
# apps/control_plane.py (líneas ~478, ~560)
@app.put("/api/v1/config/smc")
async def update_smc_config(req: SMCConfigUpdateRequest) -> dict[str, Any]:
    svc = _require_service()
    if not hasattr(svc, "smc_desk_config") or not svc.smc_desk_config:
        raise HTTPException(status_code=503, detail="SMC Desk not configured")  # ← 503 AQUÍ
    # ...
```

**Problema**: Si el desk no está habilitado (`SMC_SCANNER_ENABLED=false`), el endpoint rechaza los cambios.

---

### LLM PUT Endpoint

El endpoint LLM intenta llamar a LocalAI:

```python
# apps/control_plane.py (líneas ~783)
@app.put("/api/v1/llm/models/default")
async def set_default_llm_model(req: LLMModelSetRequest):
    discovery = LLMModelDiscovery(localai_base_url=localai_url)
    success = discovery.set_default_model(req.model_id)  # ← Puede fallar
```

**Problema**: LocalAI puede no estar disponible o no soportar `set_default_model`.

---

## Solución Requerida

### SMC/Fast PUT Endpoints

Deberían:
1. **Aceptar cambios** aunque el desk no esté inicializado
2. **Guardar en memoria** o en `.env` para persistencia
3. **Retornar success** con advertencia si el desk no está activo

**Código requerido**:
```python
@app.put("/api/v1/config/smc")
async def update_smc_config(req: SMCConfigUpdateRequest) -> dict[str, Any]:
    svc = _require_service()
    
    # Si el desk está activo, actualizar en memoria
    if hasattr(svc, "smc_desk_config") and svc.smc_desk_config:
        # ... actualizar config existente ...
        return {"status": "success", "config": ..., "message": "Config updated (runtime)"}
    
    # Si el desk NO está activo, guardar en .env o storage temporal
    # Esto permite pre-configurar antes de habilitar el desk
    update_dotenv("SMC_LLM_MODEL", req.llm_model)
    update_dotenv("SMC_HEURISTIC_MAX_CANDIDATES", str(req.max_candidates))
    # ...
    
    return {
        "status": "success",
        "config": {...},
        "message": "Config saved to .env. Restart required to apply.",
    }
```

---

### LLM PUT Endpoint

Debería:
1. **Solo guardar el nombre** del modelo para el stack
2. **No llamar a LocalAI** (es solo para selección runtime)
3. **Retornar success** siempre (es non-critical)

**Código requerido**:
```python
@app.put("/api/v1/llm/models/default")
async def set_default_llm_model(req: LLMModelSetRequest) -> dict[str, Any]:
    # Solo validar que el model_id no esté vacío
    if not req.model_id or not req.model_id.strip():
        return {"status": "error", "error": "model_id is required"}
    
    # Guardar en variable de entorno o memoria
    # El SMC Desk usará este modelo en la próxima iteración
    print(f"[INFO] LLM model changed to: {req.model_id} (runtime only)")
    
    return {
        "status": "success",
        "model_id": req.model_id,
        "message": f"LLM model changed to {req.model_id}. Note: This is runtime only.",
    }
```

---

## Workaround Actual

Mientras no se implemente la solución:

### Para SMC/Fast Config
1. Editar `.env` manualmente
2. Reiniciar backend
3. Los cambios se aplican al inicio

### Para LLM Config
1. El selector muestra modelos disponibles
2. Pero cambiar el modelo no tiene efecto real
3. Para cambiar, editar `SMC_LLM_MODEL` en `.env` y reiniciar

---

## Impacto

| Funcionalidad | Estado | Workaround |
|---------------|--------|------------|
| GET configs | ✅ Funciona | N/A |
| PUT SMC config | ❌ 503 | Editar `.env` |
| PUT Fast config | ❌ 503 | Editar `.env` |
| PUT LLM model | ❌ 500 | Editar `.env` |
| PUT Ownership | ✅ Funciona | N/A |
| PUT Risk | ✅ Funciona | N/A |

---

## Tareas Pendientes

- [ ] **SMC PUT endpoint**: Aceptar cambios aunque desk no esté activo
- [ ] **Fast PUT endpoint**: Aceptar cambios aunque desk no esté activo
- [ ] **LLM PUT endpoint**: Simplificar (solo guardar nombre, no llamar a LocalAI)
- [ ] **Persistencia**: Implementar actualización de `.env` o storage temporal
- [ ] **Tests**: Agregar tests para endpoints PUT con desk deshabilitado

---

## Notas Adicionales

### LocalAI Integration

LocalAI expone sus APIs en `http://localhost:8080/swagger/index.html`.

Endpoints relevantes:
- `GET /v1/models` → Lista modelos disponibles ✅ Implementado
- `POST /v1/chat/completions` → Usado por SMC Desk ✅ Implementado
- `PUT /v1/config` → Cambiar modelo default ❌ No implementado (no necesario)

**Requerimiento real**: El WebUI solo necesita:
1. Listar modelos disponibles (GET /v1/models) ✅
2. Guardar el nombre exacto del modelo seleccionado para usar en el stack ✅ (pendiente implementación)

No es necesario cambiar la configuración de LocalAI — solo usar el modelo seleccionado en las llamadas del SMC Desk.

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Debt Documented ⚠️
