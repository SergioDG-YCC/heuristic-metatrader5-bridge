# WebUI Repair Plan — Heuristic MT5 Bridge

**Fecha**: 2026-03-25  
**Estado**: Audit completo completado  
**Prioridad**: Crítico — WebUI no recibe datos esenciales

---

## 1. Auditoría del Estado Actual

### 1.1 Problemas Críticos Detectados

| # | Problema | Impacto | Severidad |
|---|----------|---------|-----------|
| 1 | **Fast Desk vacío** — Solo muestra posiciones genéricas, no datos específicos de Fast Desk | No se puede operar ni monitorear Fast Desk | 🔴 Crítico |
| 2 | **SMC Desk vacío** — Muestra "Preview" en todo, no hay datos de zonas/tesis | No se puede operar ni monitorear SMC Desk | 🔴 Crítico |
| 3 | **Mensaje SSE confuso** — Dice "Polling" cuando debería decir "Streaming" | Confusión sobre el estado real de conexión | 🟡 Medio |
| 4 | **Trade Allowed desconocido** — Siempre muestra "Unknown" en status strip | No se sabe si se puede operar | 🟡 Medio |
| 5 | **Falta endpoint `/api/v1/config/*`** — No hay forma de cambiar configuración desde UI | No se puede configurar sin restart | 🟡 Medio |
| 6 | **Falta endpoint `/api/v1/llm/*`** — No se puede ver/cambiar modelos LLM | No se puede gestionar LLM | 🟡 Medio |
| 7 | **Operations store no usa SSE** — Polling ineficiente en lugar de SSE | Datos desactualizados, carga innecesaria | 🟡 Medio |
| 8 | **No hay datos de Feed Health** — `feed_status` no se muestra en ningún lado | No se puede diagnosticar problemas de feed | 🟠 Alto |
| 9 | **No hay datos de Desk Status** — Fast/SMC desk status no se consume | No se sabe si los desks están activos | 🟠 Alto |
| 10 | **No hay datos de Ownership** — Endpoint existe pero no se usa | No se puede ver ownership de posiciones | 🟠 Alto |
| 11 | **No hay datos de Risk Kernel** — Endpoint existe pero no se usa | No se puede ver estado de riesgo | 🟠 Alto |
| 12 | **No hay datos de LLM Metrics** — No se puede monitorear performance LLM | No se puede diagnosticar lentitud LLM | 🟢 Bajo |

### 1.2 APIs Backend Disponibles (ya implementadas)

| Endpoint | Método | Estado | Usado en WebUI |
|----------|--------|--------|----------------|
| `/status` | GET | ✅ Implementado | ✅ Sí |
| `/events` | GET (SSE) | ✅ Implementado | ✅ Sí |
| `/account` | GET | ✅ Implementado | ✅ Sí |
| `/positions` | GET | ✅ Implementado | ✅ Sí |
| `/exposure` | GET | ✅ Implementado | ✅ Sí |
| `/catalog` | GET | ✅ Implementado | ❌ No |
| `/specs` | GET | ✅ Implementado | ❌ No |
| `/specs/{symbol}` | GET | ✅ Implementado | ❌ No |
| `/chart/{symbol}/{tf}` | GET | ✅ Implementado | ❌ No |
| `/subscribe` | POST | ✅ Implementado | ❌ No |
| `/unsubscribe` | POST | ✅ Implementado | ❌ No |
| `/ownership` | GET | ✅ Implementado | ❌ No |
| `/ownership/open` | GET | ✅ Implementado | ❌ No |
| `/ownership/history` | GET | ✅ Implementado | ❌ No |
| `/risk/status` | GET | ✅ Implementado | ❌ No |
| `/risk/limits` | GET | ✅ Implementado | ❌ No |
| `/risk/profile` | GET | ✅ Implementado | ❌ No |
| `/api/v1/llm/models` | GET | ✅ Implementado (nuevo) | ❌ No |
| `/api/v1/llm/status` | GET | ✅ Implementado (nuevo) | ❌ No |
| `/api/v1/config/smc` | GET/PUT | ✅ Implementado (nuevo) | ❌ No |
| `/api/v1/config/fast` | GET/PUT | ✅ Implementado (nuevo) | ❌ No |
| `/api/v1/config/ownership` | GET/PUT | ✅ Implementado (nuevo) | ❌ No |
| `/api/v1/config/risk` | GET/PUT | ✅ Implementado (nuevo) | ❌ No |

### 1.3 Datos que NO están llegando desde Backend

| Dato | Fuente Esperada | Estado Backend |
|------|-----------------|----------------|
| Fast Desk signals | `/api/v1/fast-desk/signals` (no existe) | ❌ No implementado |
| Fast Desk workers status | `/status` → `fast_desk_workers` | ⚠️ Parcial (solo count) |
| SMC zones | `/api/v1/smc/zones` (no existe) | ❌ No implementado |
| SMC thesis | `/api/v1/smc/thesis` (no existe) | ❌ No implementado |
| SMC scanner status | `/status` → `smc_scanner` | ⚠️ Parcial |
| Trade allowed flag | `/status` → `trade_allowed` | ❌ No expuesto |
| Feed health detallado | `/status` → `feed_status` | ⚠️ Parcial (existe pero no se usa) |
| LLM metrics | `/api/v1/llm/metrics` (no existe) | ❌ No implementado |

---

## 2. Plan de Reparación por Fases

### **Phase 1: Correcciones Críticas Inmediatas** (Día 1)

**Objetivo**: Que Fast Desk y SMC Desk muestren datos reales aunque sean básicos.

#### Step 1.1: Arreglar mensaje SSE "Polling" → "Streaming"

**Archivo**: `apps/webui/src/components/GlobalStatusStrip.tsx`

**Problema**: El texto dice "Polling" cuando está conectado, debería decir "Streaming".

**Cambio**:
```tsx
// ANTES (línea ~67)
<span class="gs-v" style={{ color: runtimeStore.sseConnected ? "var(--cyan-live)" : "var(--amber)" }}>
  {runtimeStore.sseConnected ? "Polling" : "Disconnected"}
</span>

// DESPUÉS
<span class="gs-v" style={{ color: runtimeStore.sseConnected ? "var(--cyan-live)" : "var(--amber)" }}>
  {runtimeStore.sseConnected ? "Streaming" : "Disconnected"}
</span>
```

#### Step 1.2: Agregar Trade Allowed al status

**Archivo Backend**: `apps/control_plane.py`

Agregar campo `trade_allowed` en la respuesta de `/status`:

```python
# En CoreRuntimeService.build_live_state()
def build_live_state(self) -> dict[str, Any]:
    # ... existing code ...
    terminal_info = self.connector.terminal_info()  # Nuevo método
    trade_allowed = bool(getattr(terminal_info, "trade_allowed", False)) if terminal_info else False
    
    return {
        # ... existing fields ...
        "trade_allowed": trade_allowed,  # NUEVO CAMPO
    }
```

**Archivo Frontend**: `apps/webui/src/components/GlobalStatusStrip.tsx`

Agregar indicador de Trade Allowed:

```tsx
// Después del chip de "Trade" (línea ~85)
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

#### Step 1.3: Fast Desk — Mostrar datos reales del backend

**Archivo**: `apps/webui/src/routes/FastDesk.tsx`

**Problema**: Solo muestra posiciones genéricas, no datos específicos de Fast Desk.

**Cambios**:
1. Consumir `/status` para obtener Fast Desk status
2. Mostrar configuración actual de Fast Desk
3. Mostrar signals recientes (si existen)

```tsx
// Agregar import
import { api } from "../api/client";
import { createSignal, onMount } from "solid-js";

// En el componente FastDesk
const [fastConfig, setFastConfig] = createSignal<any>(null);

onMount(async () => {
  // Fetch Fast Desk config
  try {
    const config = await api.get("/api/v1/config/fast");
    setFastConfig(config.config);
  } catch (e) {
    console.error("Failed to fetch Fast Desk config", e);
  }
});

// En el render, agregar panel de configuración
<Show when={fastConfig()}>
  <div class="panel">
    <div class="panel-head">
      <div class="panel-title">Fast Desk Config</div>
      <span class="cap-badge live">Live</span>
    </div>
    <div class="panel-body">
      <div class="sub-row"><span class="k">Scan Interval:</span><span class="v">{fastConfig()?.scan_interval}s</span></div>
      <div class="sub-row"><span class="k">Risk %:</span><span class="v">{fastConfig()?.risk_per_trade_percent}%</span></div>
      <div class="sub-row"><span class="k">Max Positions:</span><span class="v">{fastConfig()?.max_positions_total}</span></div>
    </div>
  </div>
</Show>
```

#### Step 1.4: SMC Desk — Mostrar datos reales del backend

**Archivo**: `apps/webui/src/routes/SmcDesk.tsx`

**Problema**: Muestra "Preview" en todo, no consume datos reales.

**Cambios**:
1. Consumir `/status` para obtener SMC Desk status
2. Consumir `/api/v1/config/smc` para configuración
3. Mostrar estado del scanner

```tsx
// Similar a FastDesk, agregar:
const [smcConfig, setSmcConfig] = createSignal<any>(null);
const [smcStatus, setSmcStatus] = createSignal<any>(null);

onMount(async () => {
  try {
    const [config, status] = await Promise.all([
      api.get("/api/v1/config/smc"),
      api.status(), // Del status sacamos smc_scanner status
    ]);
    setSmcConfig(config.config);
    setSmcStatus(status);
  } catch (e) {
    console.error("Failed to fetch SMC Desk data", e);
  }
});
```

---

### **Phase 2: Agregar Datos Faltantes al Backend** (Día 2-3)

**Objetivo**: Exponer datos que el backend tiene pero no está exponiendo.

#### Step 2.1: Agregar endpoint `/api/v1/feed-health`

**Archivo Backend**: `apps/control_plane.py`

```python
@app.get("/api/v1/feed-health")
async def feed_health() -> dict[str, Any]:
    """Get detailed feed health for all subscribed symbols."""
    svc = _require_service()
    return {
        "status": "success",
        "feed_status": svc.feed_status_rows,  # Ya existe en CoreRuntimeService
        "updated_at": utc_now_iso(),
    }
```

#### Step 2.2: Agregar endpoint `/api/v1/desk-status`

**Archivo Backend**: `apps/control_plane.py`

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
            "config": svc.fast_desk_config.to_dict() if hasattr(svc, "fast_desk_config") and svc.fast_desk_config else None,
        },
        "smc_desk": {
            "enabled": svc._smc_desk is not None,
            "scanner_active": True if svc._smc_desk else False,
            "config": svc.smc_desk_config.to_dict() if hasattr(svc, "smc_desk_config") and svc.smc_desk_config else None,
        },
        "updated_at": utc_now_iso(),
    }
```

#### Step 2.3: Exponer `trade_allowed` en `/status`

**Archivo Backend**: `apps/control_plane.py` o `src/heuristic_mt5_bridge/core/runtime/service.py`

En `CoreRuntimeService.build_live_state()`:

```python
def build_live_state(self) -> dict[str, Any]:
    # ... existing code ...
    
    # Get terminal info for trade_allowed
    try:
        terminal_info = self.connector.terminal_info()
        trade_allowed = bool(getattr(terminal_info, "trade_allowed", False)) if terminal_info else False
    except Exception:
        trade_allowed = False
    
    return {
        # ... existing fields ...
        "trade_allowed": trade_allowed,
    }
```

---

### **Phase 3: Consumir Datos en Frontend** (Día 4-5)

**Objetivo**: Que la WebUI consuma todos los datos disponibles.

#### Step 3.1: Agregar Feed Health Panel en RuntimeOverview

**Archivo**: `apps/webui/src/routes/RuntimeOverview.tsx`

Agregar nuevo panel que consuma `/api/v1/feed-health`:

```tsx
const [feedHealth, setFeedHealth] = createSignal<any>(null);

onMount(async () => {
  try {
    const health = await api.get("/api/v1/feed-health");
    setFeedHealth(health);
  } catch (e) {
    console.error("Failed to fetch feed health", e);
  }
});

// En el render
<Show when={feedHealth()}>
  <div class="panel">
    <div class="panel-head">
      <div class="panel-title">Feed Health</div>
      <span class="cap-badge live">Live</span>
    </div>
    <div class="panel-body">
      <For each={feedHealth()?.feed_status}>
        {(row) => (
          <div class="sub-row">
            <span class="k">{row.symbol} {row.timeframe}</span>
            <span class={`v ${row.bar_age_seconds < 60 ? 'text-green' : 'text-amber'}`}>
              {row.bar_age_seconds}s ago
            </span>
          </div>
        )}
      </For>
    </div>
  </div>
</Show>
```

#### Step 3.2: Agregar Desk Status Panel en RuntimeOverview

```tsx
const [deskStatus, setDeskStatus] = createSignal<any>(null);

onMount(async () => {
  try {
    const status = await api.get("/api/v1/desk-status");
    setDeskStatus(status);
  } catch (e) {
    console.error("Failed to fetch desk status", e);
  }
});

// En el render
<Show when={deskStatus()}>
  <div class="panel">
    <div class="panel-head">
      <div class="panel-title">Desk Status</div>
      <span class="cap-badge live">Live</span>
    </div>
    <div class="panel-body">
      <div class="sub-row">
        <span class="k">Fast Desk:</span>
        <span class={`v ${deskStatus()?.fast_desk?.enabled ? 'text-green' : 'text-muted'}`}>
          {deskStatus()?.fast_desk?.enabled ? `Active (${deskStatus()?.fast_desk?.workers} workers)` : 'Disabled'}
        </span>
      </div>
      <div class="sub-row">
        <span class="k">SMC Desk:</span>
        <span class={`v ${deskStatus()?.smc_desk?.enabled ? 'text-green' : 'text-muted'}`}>
          {deskStatus()?.smc_desk?.enabled ? 'Active' : 'Disabled'}
        </span>
      </div>
    </div>
  </div>
</Show>
```

#### Step 3.3: Operations Store — Usar SSE en lugar de polling

**Archivo**: `apps/webui/src/stores/operationsStore.ts`

**Problema**: Hace polling cada 3s y 5s cuando podría usar SSE.

**Cambio**: Suscribirse a SSE para actualizaciones:

```tsx
import { onSnapshot } from "../api/sse";

export function initOperationsStore() {
  // Poll inicial
  void pollPositions();
  void pollAccount();

  // Suscribirse a SSE para actualizaciones
  const offSnapshot = onSnapshot((snap) => {
    // Actualizar posiciones desde SSE
    if (snap.open_positions) {
      setState("positions", snap.open_positions);
    }
    if (snap.open_orders) {
      setState("orders", snap.open_orders);
    }
    if (snap.exposure_state) {
      setState("exposure", snap.exposure_state);
    }
    if (snap.account_summary) {
      setState("account", {
        account_state: snap.account_summary,
        exposure_state: snap.exposure_state,
      });
    }
    setState("lastUpdated", new Date().toISOString());
  });

  // Poll de fallback cada 30s (no 3s)
  _positionsPollId = setInterval(pollPositions, 30_000);
  _accountPollId = setInterval(pollAccount, 30_000);

  onCleanup(() => {
    offSnapshot();
    if (_positionsPollId !== null) clearInterval(_positionsPollId);
    if (_accountPollId !== null) clearInterval(_accountPollId);
  });
}
```

---

### **Phase 4: Settings Screen** (Día 6-7)

**Objetivo**: Crear pantalla de configuración para modificar valores runtime.

#### Step 4.1: Crear ruta `/settings`

**Archivo**: `apps/webui/src/App.tsx`

Agregar ruta:
```tsx
import Settings from "./routes/Settings";

// En routes
<Route path="/settings" component={Settings} />
```

#### Step 4.2: Crear componente Settings

**Archivo**: `apps/webui/src/routes/Settings.tsx` (nuevo)

```tsx
import type { Component } from "solid-js";
import { createSignal, onMount, For } from "solid-js";
import { api } from "../api/client";

const Settings: Component = () => {
  const [llmModels, setLlmModels] = createSignal<any[]>([]);
  const [smcConfig, setSmcConfig] = createSignal<any>(null);
  const [fastConfig, setFastConfig] = createSignal<any>(null);
  const [ownershipConfig, setOwnershipConfig] = createSignal<any>(null);
  const [riskConfig, setRiskConfig] = createSignal<any>(null);
  const [saving, setSaving] = createSignal<string | null>(null);
  const [error, setError] = createSignal<string | null>(null);

  onMount(async () => {
    await loadAllConfigs();
  });

  async function loadAllConfigs() {
    try {
      const [llm, smc, fast, ownership, risk] = await Promise.all([
        api.get("/api/v1/llm/models"),
        api.get("/api/v1/config/smc"),
        api.get("/api/v1/config/fast"),
        api.get("/api/v1/config/ownership"),
        api.get("/api/v1/config/risk"),
      ]);
      setLlmModels(llm.models || []);
      setSmcConfig(smc.config);
      setFastConfig(fast.config);
      setOwnershipConfig(ownership.config);
      setRiskConfig(risk.config);
    } catch (e) {
      setError("Failed to load configs");
    }
  }

  async function saveConfig(section: string, data: any) {
    setSaving(section);
    setError(null);
    try {
      await api.put(`/api/v1/config/${section}`, data);
      await loadAllConfigs(); // Recargar
    } catch (e) {
      setError(`Failed to save ${section} config`);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div style={{ padding: "20px", "overflow-y": "auto" }}>
      <h1 style={{ "font-size": "20px", "margin-bottom": "20px" }}>Settings</h1>
      
      <Show when={error()}>
        <div class="alert alert-error" style={{ margin: "10px 0" }}>{error()}</div>
      </Show>

      {/* LLM Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">LLM Configuration</div>
        </div>
        <div class="panel-body">
          <div class="form-group">
            <label>Model:</label>
            <select
              style={{ width: "100%", padding: "8px" }}
              onChange={(e) => saveConfig("smc", { llm_model: e.currentTarget.value })}
              value={smcConfig()?.llm_model}
            >
              <For each={llmModels()}>
                {(model) => (
                  <option value={model.id}>{model.name} ({model.parameter_size})</option>
                )}
              </For>
            </select>
          </div>
          <div class="form-group">
            <label>Max Tokens: {smcConfig()?.llm_max_tokens}</label>
            <input
              type="range"
              min="100"
              max="2000"
              step="100"
              value={smcConfig()?.llm_max_tokens || 500}
              onChange={(e) => saveConfig("smc", { llm_max_tokens: Number(e.currentTarget.value) })}
            />
          </div>
          <div class="form-group">
            <label>Temperature: {smcConfig()?.llm_temperature}</label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={smcConfig()?.llm_temperature || 0.1}
              onChange={(e) => saveConfig("smc", { llm_temperature: Number(e.currentTarget.value) })}
            />
          </div>
        </div>
      </div>

      {/* SMC Desk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">SMC Desk Configuration</div>
        </div>
        <div class="panel-body">
          <div class="form-group">
            <label>Max Candidates:</label>
            <input
              type="number"
              min="1"
              max="10"
              value={smcConfig()?.max_candidates || 3}
              onChange={(e) => saveConfig("smc", { max_candidates: Number(e.currentTarget.value) })}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
          <div class="form-group">
            <label>Min R:R:</label>
            <input
              type="number"
              min="1"
              max="10"
              step="0.5"
              value={smcConfig()?.min_rr || 2.0}
              onChange={(e) => saveConfig("smc", { min_rr: Number(e.currentTarget.value) })}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
        </div>
      </div>

      {/* Fast Desk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">Fast Desk Configuration</div>
        </div>
        <div class="panel-body">
          <div class="form-group">
            <label>Scan Interval (s): {fastConfig()?.scan_interval}</label>
            <input
              type="range"
              min="1"
              max="60"
              step="1"
              value={fastConfig()?.scan_interval || 5}
              onChange={(e) => saveConfig("fast", { scan_interval: Number(e.currentTarget.value) })}
            />
          </div>
          <div class="form-group">
            <label>Risk % per Trade: {fastConfig()?.risk_per_trade_percent}%</label>
            <input
              type="range"
              min="0.1"
              max="5"
              step="0.1"
              value={fastConfig()?.risk_per_trade_percent || 1.0}
              onChange={(e) => saveConfig("fast", { risk_per_trade_percent: Number(e.currentTarget.value) })}
            />
          </div>
          <div class="form-group">
            <label>Max Positions Total:</label>
            <input
              type="number"
              min="1"
              max="20"
              value={fastConfig()?.max_positions_total || 4}
              onChange={(e) => saveConfig("fast", { max_positions_total: Number(e.currentTarget.value) })}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
        </div>
      </div>

      {/* Ownership Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">Ownership Configuration</div>
        </div>
        <div class="panel-body">
          <div class="form-group">
            <label>
              <input
                type="checkbox"
                checked={ownershipConfig()?.auto_adopt_foreign ?? true}
                onChange={(e) => saveConfig("ownership", { auto_adopt_foreign: e.currentTarget.checked })}
              />
              Auto-adopt Foreign Positions
            </label>
          </div>
          <div class="form-group">
            <label>History Retention (days):</label>
            <input
              type="number"
              min="7"
              max="365"
              value={ownershipConfig()?.history_retention_days || 30}
              onChange={(e) => saveConfig("ownership", { history_retention_days: Number(e.currentTarget.value) })}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
        </div>
      </div>

      {/* Risk Configuration */}
      <div class="panel" style={{ margin: "10px 0" }}>
        <div class="panel-head">
          <div class="panel-title">Risk Configuration</div>
        </div>
        <div class="panel-body">
          <div class="form-group">
            <label>Global Profile:</label>
            <select
              style={{ width: "100%", padding: "8px" }}
              value={riskConfig()?.profile_global || 2}
              onChange={(e) => saveConfig("risk", { profile_global: Number(e.currentTarget.value) })}
            >
              <option value="1">1 - Low</option>
              <option value="2">2 - Medium</option>
              <option value="3">3 - High</option>
              <option value="4">4 - Chaos</option>
            </select>
          </div>
          <div class="form-group">
            <label>Fast Desk Profile:</label>
            <select
              style={{ width: "100%", padding: "8px" }}
              value={riskConfig()?.profile_fast || 2}
              onChange={(e) => saveConfig("risk", { profile_fast: Number(e.currentTarget.value) })}
            >
              <option value="1">1 - Low</option>
              <option value="2">2 - Medium</option>
              <option value="3">3 - High</option>
              <option value="4">4 - Chaos</option>
            </select>
          </div>
          <div class="form-group">
            <label>
              <input
                type="checkbox"
                checked={riskConfig()?.kill_switch_enabled ?? true}
                onChange={(e) => saveConfig("risk", { kill_switch_enabled: e.currentTarget.checked })}
              />
              Kill Switch Enabled
            </label>
          </div>
        </div>
      </div>

      <div style={{ margin: "20px 0", padding: "10px", background: "var(--bg-panel)", "border-radius": "6px" }}>
        <p style={{ "font-size": "11px", color: "var(--text-muted)" }}>
          ⚠️ Changes are runtime only. To persist across restarts, update .env file manually.
        </p>
      </div>
    </div>
  );
};

export default Settings;
```

#### Step 4.3: Agregar link a Settings en AppNav

**Archivo**: `apps/webui/src/components/AppNav.tsx`

Agregar item de navegación:
```tsx
<a href="/settings" class="nav-item">
  <span class="nav-icon">⚙️</span>
  <span class="nav-label">Settings</span>
</a>
```

---

## 3. Testing Checklist

### Phase 1 Tests
- [ ] Mensaje SSE dice "Streaming" cuando está conectado
- [ ] Trade Allowed muestra "Allowed" o "Blocked" correctamente
- [ ] Fast Desk muestra configuración real
- [ ] SMC Desk muestra configuración real

### Phase 2 Tests
- [ ] `GET /api/v1/feed-health` retorna datos
- [ ] `GET /api/v1/desk-status` retorna datos
- [ ] `/status` incluye `trade_allowed`

### Phase 3 Tests
- [ ] Feed Health panel muestra datos en RuntimeOverview
- [ ] Desk Status panel muestra datos en RuntimeOverview
- [ ] Operations store usa SSE (verificar menos polling en Network tab)

### Phase 4 Tests
- [ ] Settings screen carga
- [ ] LLM models se listan
- [ ] Cambios de configuración se guardan
- [ ] Changes persisten hasta restart

---

## 4. Cronograma Estimado

| Fase | Días | Entregable |
|------|------|------------|
| Phase 1 | 1 | Fast/SMC Desk muestran datos básicos |
| Phase 2 | 2 | Backend expone datos faltantes |
| Phase 3 | 2 | Frontend consume todos los datos |
| Phase 4 | 2 | Settings screen funcional |
| **Total** | **7** | **WebUI completamente funcional** |

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Ready for Implementation
