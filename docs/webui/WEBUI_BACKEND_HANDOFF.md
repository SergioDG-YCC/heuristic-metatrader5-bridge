# WebUI — Guía de Enganche para el Desarrollador de Backend

> **Audiencia**: desarrollador Python que trabaja en `apps/control_plane.py` o en `src/heuristic_mt5_bridge/`.  
> **Fecha de corte**: 2026-03-24  
> **Estado del frontend**: compilación limpia, dev server verificado.

---

## 1. Cómo arranca el frontend HOY

### Modo desarrollo (el más común — sin compilar)

```powershell
# Terminal 1 — backend
cd E:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
.\.venv\Scripts\python.exe apps\control_plane.py

# Terminal 2 — frontend (NO requiere compilar previamente)
cd apps\webui
npm install        # solo la primera vez
npm run dev
# → http://localhost:5173   ← abrir en el navegador
```

- **Vite sirve en caliente** (HMR). Cualquier cambio en `apps/webui/src/**` recarga
  el navegador automáticamente. No hay paso de compilación manual.
- **El proxy de Vite redirige todas las llamadas API** al backend local:
  - `http://localhost:5173/status` → `http://127.0.0.1:8765/status`
  - `http://localhost:5173/events` → `http://127.0.0.1:8765/events` (SSE)
  - ... todos los demás rutas de la tabla §3.
- **Sin backend activo**, el UI entra en Boot Overlay con el estado
  `degraded_unavailable` y muestra la instrucción de arranque. Esto es intencional.

### Modo producción (compilar una vez, servir estático)

```powershell
cd apps\webui
npm run build
# Genera: apps/webui/dist/  (index.html + assets/)
```

El `dist/` resultante es HTML/CSS/JS puro. Necesita un servidor HTTP; ver §5 para
integrarlo en FastAPI.

---

## 2. Punto de entrada del frontend

| Archivo | Rol |
|---|---|
| `apps/webui/index.html` | HTML raíz — monta `<div id="root">` |
| `apps/webui/src/main.tsx` | Entrada JS — `render(<App />, root)` |
| `apps/webui/src/App.tsx` | Router root — define layout + todas las rutas |
| `apps/webui/src/stores/runtimeStore.ts` | Store global — llama `/status` y `/events` en cuanto monta |
| `apps/webui/vite.config.ts` | Proxy dev → `http://127.0.0.1:8765` |

El **Boot Overlay** (`src/components/BootOverlay.tsx`) bloquea la UI hasta que
`/status` responde. La secuencia de boot states es:

```
launching_ui
  → waiting_for_control_plane   (polling /status cada 500 ms)
    → control_plane_detected_syncing   (primera respuesta recibida)
      → ready   (SSE conectado o polling estable)
```

---

## 3. Endpoints que consume el frontend — inventario completo

Todos existen en `apps/control_plane.py` y están **100% implementados**.
No hay nada roto en esta capa.

| Método | Ruta | Consumidor frontend | Polling |
|---|---|---|---|
| GET | `/status` | `runtimeStore` | 5 s (+ boot a 500 ms) |
| GET | `/events` | `api/sse.ts` | SSE permanente |
| GET | `/account` | `operationsStore`, `terminalStore` | 3–10 s |
| GET | `/positions` | `operationsStore` | 3 s |
| GET | `/exposure` | `operationsStore` | 5 s |
| GET | `/catalog` | `terminalStore` | una vez |
| GET | `/specs` | `terminalStore` | una vez |
| GET | `/specs/{symbol}` | `terminalStore` | bajo demanda |
| GET | `/chart/{symbol}/{tf}?bars=N` | `chartsStore` | bajo demanda |
| POST | `/subscribe` | `api/client.ts` | bajo demanda |
| POST | `/unsubscribe` | `api/client.ts` | bajo demanda |

> **Nota SSE**: `/events` emite `data: <json>\n\n` con el payload completo de
> `build_live_state()` en cada ciclo. El frontend lo trata como snapshot repetido,
> **no** como log de eventos. Esto es correcto con la implementación actual de
> `_sse_generator()`.

---

## 4. Lo que falta — trabajo pendiente explícito

### 4.1 Servir el `dist/` desde FastAPI (producción) — FALTA

Para que el frontend sea accesible sin Vite en producción, hay que añadir a
`apps/control_plane.py`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

WEBUI_DIST = Path(__file__).parent / "webui" / "dist"

# Después de declarar todas las rutas API:
if WEBUI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEBUI_DIST), html=True), name="webui")
```

**Requisito**: que `npm run build` se haya ejecutado antes de arrancar el backend.  
**Sin esto**, `dist/` solo es accesible vía `npm run dev` (Vite) o un servidor externo.  
**CORS**: no hace falta CORS si backend y frontend sirven desde el mismo origen.

### 4.2 CORS para desarrollo cruzado — OPCIONAL

Solo necesario si el backend y el frontend se sirven desde orígenes distintos
(e.g., frontend en otra máquina o puerto). El proxy de Vite en dev lo evita.
Si se necesita:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 4.3 Renderizado de velas (chart component) — FALTA en el frontend

El backend ya expone `/chart/{symbol}/{timeframe}`. El store `chartsStore.ts` ya
llama y cachea el endpoint. **Lo que falta** es un componente React/Solid que
renderice las velas (eje de tiempo, OHLC, volumen).

El backend **no necesita cambios** para esto — es trabajo 100% frontend.
Cuando esté listo, la ruta `/operations/symbol/:symbol/chart/:timeframe` ya existe
en el router y el store de datos está conectado.

### 4.4 Endpoints de ejecución (FastDesk / SMCDesk) — FUTUROS

Las pantallas FastDesk y SMCDesk están en estado **Preview/Planned** con un
`DisabledActionLane`. Cuando se activen, necesitarán endpoints de escritura en el
backend. Los contratos preliminares esperados son:

| Método | Ruta sugerida | Descripción |
|---|---|---|
| POST | `/order/market` | Abrir posición a mercado |
| POST | `/order/limit` | Colocar orden límite |
| DELETE | `/order/{ticket}` | Cancelar orden pendiente |
| DELETE | `/position/{ticket}` | Cerrar posición abierta por ticket |

**Estos no existen en el backend todavía**. El frontend los muestra deshabilitados
precisamente porque aún no hay contrato definido. **No implementar** hasta que el
contrato de payload esté validado con el FastDesk / SMCDesk.

### 4.5 Parámetros de ruta en pantallas Operations y Terminal — FALTA en el frontend

Las rutas `/operations/symbol/:symbol` y `/terminal/spec/:symbol` están definidas
en el router pero los componentes todavía no leen `useParams()`. Es trabajo
exclusivamente del frontend; el backend no necesita cambios.

---

## 5. Checklist rápido para el desarrollador de backend

```
[ ] ¿Está el backend corriendo en http://127.0.0.1:8765?
    → .\.venv\Scripts\python.exe apps\control_plane.py

[ ] ¿Responde /status con un dict que incluye "health", "broker_identity",
    "account_state", "market_state"?
    → curl http://127.0.0.1:8765/status

[ ] ¿Emite /events con data: <json>\n\n al menos 1 vez/segundo?
    → curl -N http://127.0.0.1:8765/events

[ ] ¿Quieres servir el UI sin Vite (producción)?
    → cd apps/webui && npm run build
    → Añadir StaticFiles mount en control_plane.py (ver §4.1)
    → http://127.0.0.1:8765/  ya sirve la UI
```

---

## 6. Estructura de archivos relevante del frontend

```
apps/webui/
├── index.html                  ← HTML raíz
├── package.json                ← dependencias (solid-js, vite, typescript)
├── vite.config.ts              ← proxy dev → 127.0.0.1:8765
├── tsconfig.json
└── src/
    ├── main.tsx                ← render(<App />, #root)
    ├── App.tsx                 ← Router root={AppLayout} + todas las rutas
    ├── types/
    │   └── api.ts              ← Tipos TypeScript de todos los payloads del backend
    ├── api/
    │   ├── client.ts           ← fetch wrapper tipado para cada endpoint
    │   └── sse.ts              ← EventSource sobre /events
    ├── stores/
    │   ├── runtimeStore.ts     ← boot, SSE, alerts derivados
    │   ├── operationsStore.ts  ← positions/orders/exposure/account
    │   ├── terminalStore.ts    ← catalog/specs/account
    │   ├── chartsStore.ts      ← cache de chart data
    │   └── uiStore.ts          ← estado local UI
    ├── components/             ← 13 componentes (badges, grids, overlays, nav)
    ├── routes/                 ← 9 pantallas
    └── styles/
        └── global.css          ← tokens de diseño, tema oscuro
```

---

## 7. No hacer (restricciones de diseño)

- **No añadir endpoints que el MT5 real no soporte**. El frontend refleja solo lo
  que el bridge puede exponer de forma fiable.
- **No añadir `trade_allowed` como booleano confiable** hasta que el backend lo
  derive correctamente del estado real de la cuenta. Hoy se muestra como
  `Unknown State`.
- **No modificar el shape de `/status`** sin actualizar `src/types/api.ts`
  (`LiveStateSnapshot`) — el frontend tipea contra ese contrato.
- **No implementar autenticación** en el frontend sin que el backend la requiera.
  Actualmente el control plane no tiene auth; cualquier adición debe ser coordinada.
