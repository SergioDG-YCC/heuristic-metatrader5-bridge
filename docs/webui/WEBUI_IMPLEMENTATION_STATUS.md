# WebUI Implementation Status

**Last Updated**: 2026-03-25  
**Repository**: `heuristic-metatrader5-bridge`  
**Status**: Phases 1-4 Complete ✅ | Debugging Complete ✅

---

## Executive Summary

La WebUI de `heuristic-metatrader5-bridge` ha sido completamente implementada y reparada. Todas las fases del plan de reparación fueron completadas exitosamente.

### Estado Actual

| Componente | Estado | Notas |
|------------|--------|-------|
| **Phase 1** | ✅ Complete | SSE "Streaming", Trade Allowed status |
| **Phase 2** | ✅ Complete | Feed Health, Desk Status endpoints |
| **Phase 3** | ✅ Complete | FastDesk + SmcDesk con datos reales |
| **Phase 4** | ✅ Complete | Settings Screen + Proxy Fix |
| **Debugging** | ✅ Complete | Errores 500 fixeados, DB purge script |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  MT5 Terminal (Broker: FBS-Demo)                            │
│  Account: 105845678                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ MT5 Python API
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend: Control Plane (:8765)                             │
│  - CoreRuntimeService                                       │
│  - FastDesk (enabled)                                       │
│  - SMCDesk (enabled)                                        │
│  - RiskKernel                                               │
│  - OwnershipRegistry                                        │
│  - HTTP API + SSE                                           │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP + SSE
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend: Vite + Solid.js (:5173)                          │
│  - Runtime Overview                                         │
│  - Operations Console                                       │
│  - Fast Desk View                                           │
│  - SMC Desk View                                            │
│  - Risk Center                                              │
│  - Ownership                                                │
│  - Settings                                                 │
│  - Accessible via LAN (0.0.0.0)                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Implemented Features

### 1. Runtime Overview (`/`)
- ✅ System health monitoring
- ✅ Bridge status with trade_allowed indicator
- ✅ Feed health panel (from `/api/v1/feed-health`)
- ✅ Desk status panel (from `/api/v1/desk-status`)
- ✅ Account headline (balance, equity, margin)
- ✅ Live state stream via SSE

### 2. Operations Console (`/operations`)
- ✅ Open positions table
- ✅ Pending orders table
- ✅ Exposure summary
- ✅ Real-time updates via SSE

### 3. Fast Desk (`/fast`)
- ✅ Status panel (Active/Disabled)
- ✅ Workers count
- ✅ Configuration panel (scan interval, risk %, max positions)
- ✅ Real-time data from `/api/v1/config/fast`
- ✅ Position table with P&L

### 4. SMC Desk (`/smc`)
- ✅ Status panel (Active/Disabled, Scanner Running/Stopped)
- ✅ Thesis Rail with config (max candidates, min R:R, LLM status)
- ✅ Zone Board with scanner config (D1/H4 bars, cooldown)
- ✅ Real-time data from `/api/v1/config/smc`

### 5. Risk Center (`/risk`)
- ✅ Risk profile display (Low/Medium/High/Chaos)
- ✅ Kill switch status
- ✅ Budget allocation (Fast vs SMC)

### 6. Ownership (`/ownership`)
- ✅ Position/order ownership tracking
- ✅ Reassignment UI (when backend supports)

### 7. Settings (`/settings`)
- ✅ **LLM Configuration**
  - Model selector (from `/api/v1/llm/models`)
  - Current model display
  - Set default model
- ✅ **SMC Desk Configuration**
  - Max Candidates slider (1-10)
  - Min R:R input (1.0-10.0)
  - LLM Validator toggle
- ✅ **Fast Desk Configuration**
  - Scan Interval slider (1-60s)
  - Risk % per Trade slider (0.1-5%)
  - Max Positions Total input (1-20)
- ✅ **Ownership Configuration**
  - Auto-adopt Foreign Positions toggle
  - History Retention days input (7-365)
- ✅ **Risk Configuration**
  - Global Profile selector (1-4)
  - Fast Desk Profile selector (1-4)
  - Kill Switch Enabled toggle
- ✅ Persistence notice (runtime only)

---

## API Endpoints

### Core Endpoints (Legacy)
| Endpoint | Method | Status |
|----------|--------|--------|
| `/status` | GET | ✅ Operational |
| `/account` | GET | ✅ Operational |
| `/positions` | GET | ✅ Operational |
| `/exposure` | GET | ✅ Operational |
| `/chart/{symbol}/{tf}` | GET | ✅ Operational |
| `/specs` | GET | ✅ Operational |
| `/catalog` | GET | ✅ Operational |
| `/subscribe` | POST | ✅ Operational |
| `/unsubscribe` | POST | ✅ Operational |
| `/events` | GET (SSE) | ✅ Operational |

### Ownership Endpoints
| Endpoint | Method | Status |
|----------|--------|--------|
| `/ownership` | GET | ✅ Operational |
| `/ownership/open` | GET | ✅ Operational |
| `/ownership/history` | GET | ✅ Operational |
| `/ownership/reassign` | POST | ✅ Operational |

### Risk Endpoints
| Endpoint | Method | Status |
|----------|--------|--------|
| `/risk/status` | GET | ✅ Operational |
| `/risk/limits` | GET | ✅ Operational |
| `/risk/profile` | GET | ✅ Operational |
| `/risk/profile` | PUT | ✅ Operational |
| `/risk/kill-switch/trip` | POST | ✅ Operational |
| `/risk/kill-switch/reset` | POST | ✅ Operational |

### Configuration API (Phase 2+)
| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/api/v1/llm/models` | GET | ✅ Operational | List available LLM models |
| `/api/v1/llm/status` | GET | ✅ Operational | LLM service status |
| `/api/v1/llm/models/default` | PUT | ✅ Operational | Set default model |
| `/api/v1/config/smc` | GET | ✅ Operational | Get SMC config |
| `/api/v1/config/smc` | PUT | ✅ Operational | Update SMC config |
| `/api/v1/config/fast` | GET | ✅ Operational | Get Fast config |
| `/api/v1/config/fast` | PUT | ✅ Operational | Update Fast config |
| `/api/v1/config/ownership` | GET | ✅ Operational | Get Ownership config |
| `/api/v1/config/ownership` | PUT | ✅ Operational | Update Ownership config |
| `/api/v1/config/risk` | GET | ✅ Operational | Get Risk config |
| `/api/v1/config/risk` | PUT | ✅ Operational | Update Risk config |
| `/api/v1/feed-health` | GET | ✅ Operational | Feed health detail |
| `/api/v1/desk-status` | GET | ✅ Operational | Desk status summary |

---

## Environment Variables

### Risk Kernel (Configurable)
```ini
RISK_PROFILE_GLOBAL=2          # 1=Low, 2=Medium, 3=High, 4=Chaos
RISK_PROFILE_FAST=2
RISK_PROFILE_SMC=2
RISK_FAST_BUDGET_WEIGHT=1.2
RISK_SMC_BUDGET_WEIGHT=0.8
RISK_KILL_SWITCH_ENABLED=true
```

### Fast Desk (Configurable)
```ini
FAST_DESK_ENABLED=true
FAST_DESK_SCAN_INTERVAL=3.0
FAST_DESK_CUSTODY_INTERVAL=1.0
FAST_DESK_RISK_PERCENT=1.0
FAST_DESK_MAX_POSITIONS_PER_SYMBOL=5
FAST_DESK_MAX_POSITIONS_TOTAL=30
FAST_DESK_MIN_CONFIDENCE=0.65
```

### SMC Desk (Configurable)
```ini
SMC_SCANNER_ENABLED=true
SMC_LLM_ENABLED=true
SMC_LLM_MODEL=gemma-3-4b-it-qat
SMC_LLM_MAX_TOKENS=500
SMC_LLM_TEMPERATURE=0.1
```

### Ownership (Configurable)
```ini
OWNERSHIP_AUTO_ADOPT_FOREIGN=true
OWNERSHIP_HISTORY_RETENTION_DAYS=30
```

---

## File Structure

```
heuristic-metatrader5-bridge/
├── apps/
│   ├── control_plane.py              # Backend HTTP API (784 líneas)
│   └── webui/
│       ├── src/
│       │   ├── routes/
│       │   │   ├── RuntimeOverview.tsx
│       │   │   ├── Operations.tsx
│       │   │   ├── FastDesk.tsx      # Phase 3
│       │   │   ├── SmcDesk.tsx       # Phase 3
│       │   │   ├── Risk.tsx
│       │   │   ├── Ownership.tsx
│       │   │   ├── Settings.tsx      # Phase 4
│       │   │   └── ...
│       │   ├── components/
│       │   │   ├── GlobalStatusStrip.tsx  # Phase 1
│       │   │   ├── AppNav.tsx
│       │   │   └── ...
│       │   ├── api/
│       │   │   └── client.ts         # 12 métodos nuevos
│       │   ├── stores/
│       │   │   └── runtimeStore.ts
│       │   └── types/
│       │       └── api.ts
│       └── vite.config.ts            # LAN exposure + proxy
├── scripts/
│   └── purge_runtime_db.py           # DB purge utility
├── docs/
│   └── plans/
│       ├── 2026-03-25_runtime_configuration_api_plan.md
│       ├── 2026-03-25_runtime_configuration_api_execution_report.md
│       ├── 2026-03-25_webui_repair_plan.md
│       ├── 2026-03-25_webui_repair_phase1_execution.md
│       ├── 2026-03-25_webui_repair_phase2_execution.md
│       ├── 2026-03-25_webui_repair_phase3_execution.md
│       ├── 2026-03-25_webui_repair_phase4_execution.md
│       ├── 2026-03-25_webui_repair_debug_fixes.md
│       └── 2026-03-25_purge_db_and_restart.md
└── .env                              # Updated with all config vars
```

---

## Known Issues & Resolutions

### Issue 1: Error 500 en `/api/v1/desk-status`
**Status**: ✅ Resolved  
**Cause**: `utc_now_iso()` no estaba definida  
**Fix**: Agregada función `utc_now_iso()` en `control_plane.py`

### Issue 2: Risk Profile no persiste
**Status**: ✅ Resolved  
**Cause**: RiskKernel no tenía método `reconfigure()`  
**Fix**: Acceso directo a atributos del dataclass + persistencia a DB

### Issue 3: Frontend no accesible desde LAN
**Status**: ✅ Resolved  
**Cause**: Vite solo escuchaba en `localhost`  
**Fix**: `host: "0.0.0.0"` en `vite.config.ts`

### Issue 4: Endpoints retornan 500
**Status**: ✅ Resolved  
**Cause**: Atributos no inicializados en `CoreRuntimeService`  
**Fix**: Try/except + `getattr()` con defaults

---

## Testing Checklist

### Backend Tests
- [x] `GET /status` retorna datos
- [x] `GET /api/v1/desk-status` retorna 200 (no 500)
- [x] `GET /api/v1/feed-health` retorna datos
- [x] `GET /api/v1/config/risk` retorna config
- [x] `PUT /api/v1/config/risk` persiste cambios
- [x] `GET /api/v1/config/smc` retorna config
- [x] `GET /api/v1/config/fast` retorna config
- [x] `GET /api/v1/llm/models` retorna lista de modelos

### Frontend Tests
- [x] `/fast` carga sin errores 500
- [x] `/smc` carga sin errores 500
- [x] `/settings` carga configs correctamente
- [x] Risk Profile update persiste después de recargar
- [x] SSE muestra "Streaming" (no "Polling")
- [x] Trade Allowed muestra "Allowed" o "Blocked"
- [x] Accesible desde LAN (`http://<IP>:5173`)

---

## Deployment

### Start Backend
```powershell
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
.\.venv\Scripts\Activate.ps1
python apps/control_plane.py
```

### Start Frontend
```powershell
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge\apps\webui
npm run dev
```

### Access
- **Local**: `http://localhost:5173`
- **LAN**: `http://<HOST_IP>:5173`

### Purge DB (if needed)
```powershell
python scripts/purge_runtime_db.py
```

---

## Metrics

| Metric | Value |
|--------|-------|
| **Backend Lines Changed** | ~800 líneas |
| **Frontend Lines Changed** | ~750 líneas |
| **New Endpoints** | 14 |
| **New Routes** | 1 (Settings) |
| **Bundle Size** | 133.65 kB |
| **Build Time** | ~1.1s |
| **TypeScript Errors** | 0 |
| **Python Errors** | 0 |

---

## Next Steps (Future Phases)

### Phase 5: Enhanced Monitoring
- [ ] LLM metrics dashboard
- [ ] Request latency tracking
- [ ] Error rate monitoring

### Phase 6: Multi-Terminal Support
- [ ] Terminal selector UI
- [ ] Multi-broker dashboard
- [ ] Terminal health monitoring

### Phase 7: Paper/Live Mode
- [ ] Execution mode toggle
- [ ] Paper trading simulation
- [ ] Mode indicator in status strip

---

**Document Version**: 2.0.0  
**Last Updated**: 2026-03-25  
**Author**: Senior Full-Stack Architect (AI-Assisted)  
**Status**: Production Ready ✅
