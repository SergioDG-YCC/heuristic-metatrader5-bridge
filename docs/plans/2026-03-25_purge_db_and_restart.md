# WebUI Repair — Purge DB & Restart Instructions

**Fecha**: 2026-03-25  
**Objetivo**: Resetear DB y reiniciar stacks limpiamente

---

## Paso 1: Purgar Runtime DB

```powershell
# En una terminal
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
.\.venv\Scripts\Activate.ps1

# Ejecutar script de purge
python scripts/purge_runtime_db.py
```

**Output esperado**:
```
Purging database: e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge\storage\runtime.db
Found 15 tables
  ✓ Purged: symbol_catalog_cache
  ✓ Purged: symbol_spec_cache
  ✓ Purged: account_state_cache
  ✓ Purged: position_cache
  ✓ Purged: order_cache
  ✓ Purged: exposure_cache
  ✓ Purged: market_state_cache
  ✓ Purged: smc_zones
  ✓ Purged: smc_thesis_cache
  ✓ Purged: smc_events_log
  ✓ Purged: fast_desk_signals
  ✓ Purged: fast_desk_trade_log
  ✓ Purged: operation_ownership
  ✓ Purged: risk_profile_state
  ✓ Purged: risk_budget_state

Database purged successfully!
Restart backend to reinitialize with clean state.
```

---

## Paso 2: Reiniciar Backend

```powershell
# En la misma terminal (después del purge)
python apps/control_plane.py
```

**Output esperado**:
```
============================================================
  Heuristic MT5 Bridge — Control Plane
============================================================
  broker   : FBS-Demo (FBS-Demo)
  account  : 105845678  10000.0 USD
  symbols  : BTCUSD, EURUSD, GBPUSD, USDJPY, USDCHF
  tf       : M1, M5, H1, H4, D1
  smc_desk : enabled
  db       : storage\runtime.db
  endpoint : http://0.0.0.0:8765
============================================================

[2026-03-25T14:30:00Z] bootstrapping runtime...
[2026-03-25T14:30:05Z] status=up | market=up | indicator=up | account=up | symbols=5 | positions=0 | orders=0
```

**Importante**: Verificar que:
- ✅ `status=up`
- ✅ `market=up`
- ✅ `account=up`
- ✅ No hay errores de inicialización

---

## Paso 3: Reiniciar Frontend

```powershell
# En OTRA terminal
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge\apps\webui
npm run dev
```

**Output esperado**:
```
VITE v6.4.1  ready in 500 ms

➜  Local:   http://localhost:5173/
➜  Network: http://192.168.1.100:5173/
➜  press h + enter to show help
```

**Importante**: 
- ✅ Debería mostrar "Local" y "Network"
- ✅ Puerto 5173
- ✅ Sin errores de compilación

---

## Paso 4: Verificar Endpoints

### Test 1: Desk Status (sin error 500)

```bash
# En browser o curl
curl http://localhost:8765/api/v1/desk-status
```

**Respuesta esperada**:
```json
{
  "status": "success",
  "fast_desk": {
    "enabled": true,
    "workers": 5,
    "config": {
      "scan_interval": 3.0,
      "risk_per_trade_percent": 1.0,
      "max_positions_total": 30
    }
  },
  "smc_desk": {
    "enabled": true,
    "scanner_active": true,
    "config": {
      "llm_model": "gemma-3-4b-it-qat",
      "llm_enabled": true
    }
  }
}
```

### Test 2: Risk Config

```bash
# Obtener config actual
curl http://localhost:8765/api/v1/config/risk

# Actualizar profile_global a 3 (High)
curl -X PUT http://localhost:8765/api/v1/config/risk \
  -H "Content-Type: application/json" \
  -d "{\"profile_global\": 3}"

# Verificar que se actualizó
curl http://localhost:8765/api/v1/config/risk
```

**Respuesta esperada**:
```json
{
  "status": "success",
  "config": {
    "profile_global": 3,
    "profile_fast": 2,
    "profile_smc": 2,
    ...
  }
}
```

### Test 3: Feed Health

```bash
curl http://localhost:8765/api/v1/feed-health
```

**Respuesta esperada**:
```json
{
  "status": "success",
  "feed_status": [
    {
      "symbol": "BTCUSD",
      "timeframe": "M5",
      "bar_age_seconds": 45
    },
    ...
  ]
}
```

---

## Paso 5: Verificar Frontend

### 5.1: Fast Desk

1. Abrir `http://localhost:5173/fast`
2. Verificar:
   - ✅ No hay errores 500 en consola
   - ✅ Panel "Fast Desk Status" muestra "Active"
   - ✅ Panel "Fast Desk Config" muestra datos reales

### 5.2: SMC Desk

1. Abrir `http://localhost:5173/smc`
2. Verificar:
   - ✅ No hay errores 500 en consola
   - ✅ Panel "SMC Desk Status" muestra "Active"
   - ✅ Panel "Thesis Rail" muestra config SMC

### 5.3: Settings — Risk Profile

1. Abrir `http://localhost:5173/settings`
2. Ir a "Risk Configuration"
3. Cambiar "Global Profile" a "High" (3)
4. Guardar
5. **Recargar página (F5)**
6. Verificar:
   - ✅ "Global Profile" sigue en "High" (no vuelve a "Medium")
   - ✅ Success message se muestra

---

## Troubleshooting

### Problema: Backend no inicia

**Síntoma**: Error de conexión o traceback

**Solución**:
```powershell
# Verificar logs del backend
# Debería mostrar el error específico

# Si es error de DB:
python scripts/purge_runtime_db.py

# Si es error de MT5:
# Verificar que MT5 esté abierto con la cuenta correcta
```

### Problema: Error 500 persiste

**Síntoma**: `GET /api/v1/desk-status 500`

**Solución**:
1. Ver logs del backend (terminal donde corre `control_plane.py`)
2. Debería mostrar:
   ```
   [ERROR] /api/v1/desk-status failed: ...
   ```
3. Copiar el error y revisar el traceback

### Problema: Risk Profile no persiste

**Síntoma**: Cambia a "High" pero al recargar vuelve a "Medium"

**Solución**:
```powershell
# 1. Purgar DB
python scripts/purge_runtime_db.py

# 2. Reiniciar backend
python apps/control_plane.py

# 3. Verificar .env tiene las variables:
# RISK_PROFILE_GLOBAL=2
# RISK_PROFILE_FAST=2
# RISK_PROFILE_SMC=2
```

### Problema: Frontend no carga desde LAN

**Síntoma**: `http://<IP>:5173` no carga

**Solución**:
1. Verificar firewall de Windows:
   - Permitir Node.js en puerto 5173
2. Verificar vite.config.ts:
   ```typescript
   server: {
     host: "0.0.0.0", // Debe estar esta línea
     port: 5173,
   }
   ```
3. Reiniciar frontend:
   ```powershell
   npm run dev
   ```

---

## Comandos Rápidos

```powershell
# Purge DB + Restart Backend (una línea)
python scripts/purge_runtime_db.py && python apps/control_plane.py

# Restart Frontend
cd apps/webui && npm run dev

# Test endpoints
curl http://localhost:8765/api/v1/desk-status | ConvertFrom-Json
curl http://localhost:8765/api/v1/config/risk | ConvertFrom-Json
```

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Status**: Ready for Testing
