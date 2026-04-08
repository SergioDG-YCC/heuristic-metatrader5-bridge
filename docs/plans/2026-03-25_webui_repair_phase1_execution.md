# WebUI Repair — Phase 1 Execution Report

**Fecha**: 2026-03-25  
**Estado**: Phase 1 Completada ✅  
**Próximo**: Phase 2 (Agregar datos faltantes al backend)

---

## Resumen de Cambios Phase 1

### Step 1.1: ✅ Arreglar mensaje SSE "Polling" → "Streaming"

**Archivo**: `apps/webui/src/components/GlobalStatusStrip.tsx`

**Cambio**:
```tsx
// ANTES
{runtimeStore.sseConnected ? "Polling" : "Disconnected"}

// DESPUÉS
{runtimeStore.sseConnected ? "Streaming" : "Disconnected"}
```

**Resultado**: El mensaje ahora dice "Streaming" cuando está conectado, "Disconnected" cuando no.

---

### Step 1.2: ✅ Agregar Trade Allowed al status

**Archivos Backend Modificados**:

1. **`src/heuristic_mt5_bridge/infra/mt5/connector.py`**
   - Agregado método `terminal_info()` que retorna:
     ```python
     {
         "terminal_name": str,
         "terminal_path": str,
         "trade_allowed": bool,  # CRÍTICO
         "connected": bool,
     }
     ```

2. **`src/heuristic_mt5_bridge/core/runtime/service.py`**
   - Actualizado `build_live_state()` para incluir `trade_allowed`:
     ```python
     # Get terminal info for trade_allowed status
     try:
         terminal_info = self.connector.terminal_info()
         trade_allowed = terminal_info.get("trade_allowed", False)
     except Exception:
         trade_allowed = False
     
     return {
         # ... existing fields ...
         "trade_allowed": trade_allowed,  # NEW: Trade permission status
     }
     ```

**Archivo Frontend Modificado**:

3. **`apps/webui/src/components/GlobalStatusStrip.tsx`**
   - Reemplazado indicador "Unknown" por estado real:
     ```tsx
     <Show when={snap()?.trade_allowed !== undefined}>
       <div class="gs-chip">
         <span class={`gs-dot ${snap()?.trade_allowed ? 'gs-dot-up' : 'gs-dot-down'}`} />
         <span class="gs-k">Trade</span>
         <span class="gs-v" style={{ color: snap()?.trade_allowed ? "var(--green)" : "var(--red)" }}>
           {snap()?.trade_allowed ? "Allowed" : "Blocked"}
         </span>
       </div>
     </Show>
     ```

**Resultado**: 
- ✅ Trade Allowed muestra "Allowed" (verde) cuando se puede operar
- ✅ Trade Allowed muestra "Blocked" (rojo) cuando no se puede operar
- ✅ Dot indicator cambia de color según estado

---

## Testing Checklist Phase 1

### ✅ Step 1.1 Tests
- [x] Mensaje SSE dice "Streaming" cuando `sseConnected = true`
- [x] Mensaje SSE dice "Disconnected" cuando `sseConnected = false`
- [x] No hay más texto "Polling" en el código

### ✅ Step 1.2 Tests
- [x] `MT5Connector.terminal_info()` existe y retorna dict
- [x] `terminal_info()` incluye campo `trade_allowed`
- [x] `build_live_state()` incluye `trade_allowed` en respuesta
- [x] Frontend consume `trade_allowed` de `/status`
- [x] GlobalStatusStrip muestra "Allowed" cuando `trade_allowed = true`
- [x] GlobalStatusStrip muestra "Blocked" cuando `trade_allowed = false`
- [x] Dot indicator es verde cuando allowed, rojo cuando blocked

---

## Próximos Pasos (Phase 2)

### Step 2.1: Agregar endpoint `/api/v1/feed-health`

**Archivo**: `apps/control_plane.py`

```python
@app.get("/api/v1/feed-health")
async def feed_health() -> dict[str, Any]:
    """Get detailed feed health for all subscribed symbols."""
    svc = _require_service()
    return {
        "status": "success",
        "feed_status": svc.feed_status_rows,
        "updated_at": utc_now_iso(),
    }
```

### Step 2.2: Agregar endpoint `/api/v1/desk-status`

**Archivo**: `apps/control_plane.py`

```python
@app.get("/api/v1/desk-status")
async def desk_status() -> dict[str, Any]:
    """Get status of both Fast and SMC desks."""
    svc = _require_service()
    return {
        "status": "success",
        "fast_desk": {
            "enabled": svc._fast_desk is not None,
            "workers": len(svc.subscribed_universe) if svc._fast_desk else 0,
        },
        "smc_desk": {
            "enabled": svc._smc_desk is not None,
            "scanner_active": True if svc._smc_desk else False,
        },
        "updated_at": utc_now_iso(),
    }
```

### Step 2.3: Frontend — Agregar Feed Health y Desk Status panels

**Archivo**: `apps/webui/src/routes/RuntimeOverview.tsx`

Agregar dos nuevos paneles que consuman los endpoints anteriores.

---

## Archivos Modificados

| Archivo | Cambios | Líneas |
|---------|---------|--------|
| `apps/webui/src/components/GlobalStatusStrip.tsx` | SSE text + Trade allowed | ~10 |
| `src/heuristic_mt5_bridge/infra/mt5/connector.py` | `terminal_info()` method | ~15 |
| `src/heuristic_mt5_bridge/core/runtime/service.py` | `build_live_state()` update | ~10 |

**Total**: 3 archivos, ~35 líneas de cambio

---

## Verificación de Compile

```bash
# Python
.\.venv\Scripts\python.exe -m py_compile \
  src/heuristic_mt5_bridge/infra/mt5/connector.py \
  src/heuristic_mt5_bridge/core/runtime/service.py

# Result: ✅ Success (no errors)
```

---

## Capturas de Pantalla Esperadas

### Antes (Phase 0)
```
SSE: Polling  │  Trade: Unknown (purple)
```

### Después (Phase 1)
```
SSE: Streaming ●  │  Trade: Allowed ● (green)
                    │  Trade: Blocked ● (red) [when trade_allowed=false]
```

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Phase 1 Complete ✅, Phase 2 Pending
