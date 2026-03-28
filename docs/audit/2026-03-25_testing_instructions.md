# Instrucciones de Testing — Post Fixes

**Fecha**: 2026-03-25  
**Estado**: Listo para testing

---

## Cambios Aplicados

### 1. Backend (`apps/control_plane.py`)
- ✅ Endpoints LLM agregados (`/api/v1/llm/*`)
- ✅ Error handling graceful (no 500, retorna error message)
- ✅ Logging de errores LLM

### 2. Frontend (`apps/webui/src/routes/Settings.tsx`)
- ✅ Promise.allSettled (carga independiente de configs)
- ✅ Budget Allocation dinámico (3 sliders)
- ✅ Error handling para respuestas "warning" y "error"
- ✅ Auto-retry cada 3 segundos si falla algún config

---

## Instrucciones de Testing

### Paso 1: Reiniciar Stacks

**Terminal 1 — Backend**:
```powershell
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
.\.venv\Scripts\Activate.ps1
python apps/control_plane.py
```

**Terminal 2 — Frontend**:
```powershell
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge\apps\webui
npm run dev
```

---

### Paso 2: Hard Refresh en Browser

**Importante**: El dev server cachea los archivos source. Necesitás forzar la recarga:

- **Windows**: `Ctrl + Shift + R`
- **Mac**: `Cmd + Shift + R`
- **Chrome DevTools**: Click derecho en botón refresh → "Empty Cache and Hard Reload"

---

### Paso 3: Verificar Settings Screen

Ir a `http://localhost:5173/settings`

#### Verificaciones:

**1. LLM Configuration Panel**
- [ ] Panel carga (no dice "Loading…" permanentemente)
- [ ] "Current Model" muestra `gemma-3-4b-it-qat`
- [ ] "Available Models" muestra lista (si LocalAI está disponible)
- [ ] Si LocalAI NO está disponible, muestra error graceful (no crash)

**2. Cambiar Modelo LLM**
- [ ] Seleccionar otro modelo del dropdown
- [ ] Click para cambiar
- [ ] **Resultado esperado**:
  - ✅ Success: "LLM configuration updated: Default model updated in LocalAI config"
  - ⚠️ Warning: "LLM configuration update: LocalAI responded but model change may not have been applied"
  - ❌ Error (graceful): "LLM configuration update failed: LocalAI unavailable... This is non-critical."

**3. SMC Desk Configuration**
- [ ] Panel carga (no "Loading SMC config…")
- [ ] Muestra "Max Candidates", "Min R:R", "Spread Tolerance"
- [ ] Sliders funcionan

**4. Fast Desk Configuration**
- [ ] Panel carga (no "Loading Fast config…")
- [ ] Muestra "Scan Interval", "Risk %", "Max Positions"
- [ ] Muestra "Allowed Market Sessions" checkboxes
- [ ] Sliders funcionan

**5. Budget Allocation (Risk Panel)**
- [ ] Quick Mode slider muestra Fast% / SMC%
- [ ] Mover Quick Mode → actualiza Advanced Mode weights
- [ ] Mover Fast Weight → actualiza Quick Mode %
- [ ] Mover SMC Weight → actualiza Quick Mode %
- [ ] Computed Allocation muestra porcentajes correctos

---

## Posibles Escenarios

### Escenario A: LocalAI está disponible

```
1. Ir a Settings
2. LLM panel muestra "Available Models (2)"
3. Seleccionar "gemma-3-12b-it-qat"
4. Guardar
5. Ver mensaje: "LLM configuration updated: Default model updated in LocalAI config"
6. Panel recarga con nuevo modelo
```

---

### Escenario B: LocalAI NO está disponible

```
1. Ir a Settings
2. LLM panel muestra error graceful: "LocalAI is not available..."
3. SMC/Fast/Ownership/Risk panels cargan igual (Promise.allSettled fix)
4. Intentar cambiar modelo LLM
5. Ver mensaje: "LLM configuration update failed: LocalAI unavailable... This is non-critical."
6. Error es AMARILLO (warning), no ROJO (critical)
7. Otros panels siguen funcionando
```

---

### Escenario C: Error de carga inicial

```
1. Ir a Settings
2. Algunos panels dicen "Loading..."
3. Después de 3 segundos, auto-retry
4. Si endpoint responde, panel carga
5. Si endpoint sigue fallando, muestra error específico:
   "Failed to load 1 config(s): LLM Models. Retrying..."
```

---

## Debugging

### Si SMC/Fast siguen sin cargar:

**1. Verificar consola del browser**:
```
- ¿Hay errores de red? (404, 500)
- ¿Qué endpoints fallan?
```

**2. Verificar backend logs**:
```
- ¿El backend está corriendo?
- ¿Hay errores de Python?
```

**3. Verificar Promise.allSettled**:
```javascript
// En consola del browser:
fetch('/api/v1/config/smc').then(r => r.json()).then(console.log)
fetch('/api/v1/config/fast').then(r => r.json()).then(console.log)
// ¿Retornan datos?
```

---

### Si LLM endpoint falla 500:

**1. Verificar LocalAI**:
```powershell
# Testear si LocalAI responde:
curl http://127.0.0.1:8080/v1/models
```

**2. Verificar backend logs**:
```
- ¿Hay mensajes "[WARNING] LLM model change failed: ..."?
- ¿Qué error específico reporta?
```

**3. Workaround**:
- El error LLM es **non-critical**
- SMC Desk sigue funcionando con el modelo actual
- El usuario puede ignorar el panel LLM si LocalAI no está disponible

---

## Checklist Final

- [ ] Backend reiniciado
- [ ] Frontend reiniciado
- [ ] Hard refresh en browser (Ctrl+Shift+R)
- [ ] LLM panel carga (con o sin LocalAI)
- [ ] SMC panel carga
- [ ] Fast panel carga
- [ ] Ownership panel carga
- [ ] Risk panel carga
- [ ] Budget sliders son dinámicos
- [ ] Cambiar modelo LLM no crashea (success/warning/error graceful)
- [ ] Auto-retry funciona (si algún config falla)

---

## Reportar Resultados

Por favor reportar:

1. **¿Qué paneles cargan?** (LLM, SMC, Fast, Ownership, Risk)
2. **¿Qué errores ves en consola?** (copiar y pegar)
3. **¿El Budget Allocation es dinámico?** (mover slider → actualiza otros)
4. **¿El cambio de modelo LLM qué retorna?** (success/warning/error)

---

**Document Version**: 1.0.0  
**Last Updated**: 2026-03-25  
**Status**: Ready for Testing ✅
