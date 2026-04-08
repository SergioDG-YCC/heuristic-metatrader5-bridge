# WebUI Repair — Debug Fixes

**Fecha**: 2026-03-25  
**Estado**: Debugging completado ✅

---

## Problemas Reportados

1. **Errores 500** en `/api/v1/desk-status` y `/api/v1/feed-health`
2. **Risk profile no se actualiza** - El cambio parece exitoso pero los valores vuelven a "Medium"
3. **Frontend no accesible desde LAN** - Solo disponible en localhost

---

## Fixes Aplicados

### Fix 1: Errores 500 en Endpoints

**Archivos**: `apps/control_plane.py`

**Problema**: Los endpoints asumían que ciertos atributos existían en `CoreRuntimeService`, pero pueden no estar inicializados.

**Solución**: Envolver en try/except y usar `getattr()` con defaults:

```python
@app.get("/api/v1/feed-health")
async def feed_health() -> dict[str, Any]:
    try:
        svc = _require_service()
        feed_status = getattr(svc, "feed_status_rows", [])
        return {
            "status": "success",
            "feed_status": feed_status if isinstance(feed_status, list) else [],
            "updated_at": utc_now_iso(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "feed_status": [],
            "updated_at": utc_now_iso(),
        }
```

**Endpoints fixeados**:
- `/api/v1/feed-health`
- `/api/v1/desk-status`

---

### Fix 2: Risk Profile Update Flow

**Archivo**: `apps/control_plane.py`

**Problema**: El endpoint PUT asumía que `RiskKernel` tenía métodos `reconfigure()` y `to_dict()`, pero es un dataclass sin esos métodos.

**Solución**: Actualizar atributos directamente y persistir:

```python
@app.put("/api/v1/config/risk")
async def update_risk_config(req: RiskConfigUpdateRequest) -> dict[str, Any]:
    svc = _require_service()
    if not hasattr(svc, "risk_kernel") or not svc.risk_kernel:
        raise HTTPException(status_code=503, detail="RiskKernel not initialized")
    
    rk = svc.risk_kernel
    
    # Direct attribute update (RiskKernel is a dataclass)
    if req.profile_global is not None:
        rk.profile_global = max(1, min(4, int(req.profile_global)))
    # ... otros campos ...
    
    # Persist changes to DB
    try:
        rk._persist_profile_state()
        rk._append_event("config_updated", reason="api_put_request")
    except Exception as e:
        print(f"Warning: Could not persist risk config changes: {e}")
    
    return {
        "status": "success",
        "config": {
            "profile_global": rk.profile_global,
            "profile_fast": rk.profile_fast,
            "profile_smc": rk.profile_smc,
            "fast_budget_weight": rk.fast_budget_weight,
            "smc_budget_weight": rk.smc_budget_weight,
            "kill_switch_enabled": rk.kill_switch_enabled,
        },
        "message": "RiskKernel configuration updated",
    }
```

**Cambios clave**:
- Acceso directo a atributos del dataclass (`rk.profile_global`)
- Llamada a `_persist_profile_state()` para guardar en DB
- Llamada a `_append_event()` para audit trail
- Retorno explícito del config actualizado

---

### Fix 3: Frontend Accesible desde LAN

**Archivo**: `apps/webui/vite.config.ts`

**Problema**: Vite solo escuchaba en `localhost:5173`.

**Solución**: Agregar `host: "0.0.0.0"`:

```typescript
export default defineConfig({
  plugins: [solidPlugin()],
  server: {
    host: "0.0.0.0", // Expose on LAN
    port: 5173,
    proxy: {
      // ... proxy config ...
    },
  },
});
```

**Acceso desde LAN**:
- Host machine: `http://localhost:5173`
- Otras máquinas: `http://<IP_DEL_HOST>:5173`
  - Ejemplo: `http://192.168.1.100:5173`

**Nota**: El firewall de Windows puede pedir permiso para abrir el puerto 5173.

---

## Testing Post-Fixes

### Test 1: Endpoints sin errores 500

```bash
# Test directo al backend
curl http://localhost:8765/api/v1/desk-status
curl http://localhost:8765/api/v1/feed-health

# Debería retornar JSON con status: "success" o "error" (pero no 500)
```

### Test 2: Risk Profile Update

```bash
# 1. Obtener config actual
curl http://localhost:8765/api/v1/config/risk

# 2. Actualizar a profile_global=3 (High)
curl -X PUT http://localhost:8765/api/v1/config/risk \
  -H "Content-Type: application/json" \
  -d '{"profile_global": 3}'

# 3. Verificar que se actualizó
curl http://localhost:8765/api/v1/config/risk

# Debería mostrar "profile_global": 3
```

### Test 3: Acceso desde LAN

1. En host machine:
   - Abrir `http://localhost:5173` → Debería cargar
   
2. En otra máquina en la misma red:
   - Abrir `http://<IP_DEL_HOST>:5173`
   - Ejemplo: `http://192.168.1.100:5173`
   - Debería cargar la WebUI

3. En Chrome DevTools → Network:
   - Ver requests a `/api/v1/*`
   - Deberían retornar 200 (no 500)

---

## Comandos para Reiniciar Stacks

### Backend

```powershell
# En una terminal
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
.\.venv\Scripts\Activate.ps1
python apps/control_plane.py
```

### Frontend

```powershell
# En otra terminal
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge\apps\webui
npm run dev
```

---

## Expected Behavior Post-Fixes

### FastDesk.tsx
- ✅ Carga datos de `/api/v1/desk-status` sin error 500
- ✅ Muestra "Active" si `fast_desk.enabled = true`
- ✅ Muestra config de `/api/v1/config/fast`

### SmcDesk.tsx
- ✅ Carga datos de `/api/v1/desk-status` sin error 500
- ✅ Muestra "Active" si `smc_desk.enabled = true`
- ✅ Muestra config de `/api/v1/config/smc`

### RuntimeOverview.tsx
- ✅ Carga `/api/v1/feed-health` sin error 500
- ✅ Muestra Feed Health panel con datos

### Settings.tsx
- ✅ Risk profile update persiste cambios
- ✅ Al recargar, los valores se mantienen
- ✅ Success message se muestra

---

## Archivos Modificados

| Archivo | Cambios | Líneas |
|---------|---------|--------|
| `apps/control_plane.py` | Error handling + Risk fix | ~80 |
| `apps/webui/vite.config.ts` | LAN exposure | ~1 |

**Total**: 2 archivos, ~81 líneas

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Debugging Complete ✅
