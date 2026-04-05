# Correlation Engine — Design Plan

> **Status**: design draft v2 — April 2026 (revisado con peer review)
> **Scope**: motor de correlación entre símbolos activos del catálogo, consumido por Fast Desk y SMC Desk
> **Principio rector**: el core entrega cálculo puro + caché; la interpretación operativa vive en cada mesa

---

## 1. Propósito

Construir una tabla de correlación dinámica entre los **símbolos activos del catálogo** (activables/desactivables desde WebUI, persistidos en DB, además de `MT5_WATCH_SYMBOLS`), en las temporalidades configuradas, que permita a las dos mesas de trading tomar mejores decisiones:

| Mesa | Uso esperado |
|------|-------------|
| **Fast Desk** | Gate de entrada: la *policy* del desk decide si bloquear o reducir convicción según el coeficiente |
| **Fast Desk** | Confirmación de tesis: si EURUSD dispara señal buy y GBPUSD tiene correlación alta, la policy puede alinearlas |
| **SMC Desk** | Enriquecimiento de contexto LLM: la capa de formateo SMC agrega bloque de correlación al prompt |
| **SMC Desk** | Filtro de concentración: reducir exposición implícita a través de instrumentos correlados |

> **Diseño clave**: el `CorrelationService` (core) entrega solo datos. La interpretación operativa (bloqueos, labels, snippets LLM) vive en capas de policy separadas por mesa.

---

## 2. Fuente de Datos

### 2.1 Ya disponible — sin cambios en infra

La fuente primaria son los **arrays de cierre** (`ohlc[].close`) que viven en `MarketStateService`, alimentados por el loop de polling del `ConnectorIngress`.

```
MarketStateService
  └── key: (symbol, timeframe)
        └── candles: [{timestamp, open, high, low, close, volume}, ...]   ← close series
```

- Se actualiza cada `MT5_POLL_SECONDS` (default 5s)
- Reside 100% en RAM; sin acceso a disco en hot path
- Los timestamps de las velas son strings ISO UTC, normalizados (offset de servidor corregido)

### 2.2 Restricciones de la fuente actual

| Restricción | Impacto en correlación |
|-------------|----------------------|
| Solo `copy_rates_from_pos` (velas OHLCV) — no `copy_ticks_from` | Correlación solo a nivel de cierre de vela, no tick-a-tick |
| Hasta `MT5_BARS_PER_PULL` velas (default 200) | Ventana histórica máxima limitada por configuración |
| Cada (symbol, timeframe) tiene su propio array de timestamps | Requiere alineación temporal antes de calcular coeficiente |
| No hay coherencia de cierre garantizada entre símbolos distintos | EURUSD/M5 y XAUUSD/M5 pueden tener velas con offsets distintos si el broker difiere |

---

## 3. Qué Calcular

### 3.1 Coeficiente de Pearson — rolling window

El coeficiente canónico para correlación de retornos de precio:

$$
r_{A,B} = \frac{\sum_{i=1}^{n}(r_A^i - \bar{r}_A)(r_B^i - \bar{r}_B)}{\sqrt{\sum_{i=1}^{n}(r_A^i - \bar{r}_A)^2} \cdot \sqrt{\sum_{i=1}^{n}(r_B^i - \bar{r}_B)^2}}
$$

Donde $r^i = \frac{close_i - close_{i-1}}{close_{i-1}}$ (retorno logarítmico o simple — **por definir en parametrización**).

### 3.2 Estructura de salida

Una **matriz cuadrada** por temporalidad:

```
CorrelationMatrix {
  timeframe: "M30"
  computed_at: "2026-04-05T12:00:00Z"
  window_bars: 50          ← parámetro configurable
  symbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
  matrix: {
    "EURUSD": {"EURUSD": 1.0,  "GBPUSD": 0.87, "USDJPY": -0.61, "XAUUSD": 0.12},
    "GBPUSD": {"EURUSD": 0.87, "GBPUSD": 1.0,  "USDJPY": -0.55, "XAUUSD": 0.08},
    ...
  }
  stale: false
  bars_available: 48       ← cuántas velas coincidentes se encontraron
  coverage_ok: true        ← bars_available >= min_coverage_bars
}
```

### 3.3 Clasificación del coeficiente (por definir umbrales exactos)

| Rango `|r|` | Etiqueta | Acción sugerida |
|------------|----------|----------------|
| 0.85 – 1.0 | `high_direct` / `high_inverse` | Bloquear entrada duplicada; usar como confirmación |
| 0.60 – 0.84 | `moderate` | Advertencia; reducir size o pasar a revisión |
| 0.30 – 0.59 | `weak` | Informativo solamente |
| 0.00 – 0.29 | `negligible` | Sin restricción |

> ⚠️ **Pendiente**: umbrales exactos, lógica directa vs. inversa, y política de bloqueo dura vs. suave — a definir con documentación externa.

---

## 4. Arquitectura del Motor (Core Puro)

### 4.1 Separación motor / policy

```
core/correlation/          ← cálculo puro, caché, snapshots — SIN lógica de mesa
  service.py               ← CorrelationService
  models.py                ← CorrelationPairValue, CorrelationMatrixSnapshot
  aligner.py               ← alineación de series temporales
  __init__.py

fast_desk/correlation/     ← interpretación para Fast Desk (NUEVA CAPA)
  policy.py                ← FastCorrelationPolicy (gate, bucketing, bloqueo)

smc_desk/correlation/      ← interpretación para SMC Desk (NUEVA CAPA)
  formatter.py             ← SmcCorrelationFormatter (snippet LLM, contexto)

control_plane/             ← presentación para WebUI/API
  correlation_presenter.py ← CorrelationApiPresenter (serialización JSON)
```

**Regla**: nada de `buy/sell`, `check_entry_conflict`, `high_direct`, ni snippet LLM dentro de `core/correlation/`.

### 4.2 Integración en CoreRuntimeService

```
CoreRuntimeService
  ├── ConnectorIngress      (polling MT5 — sin cambios)
  ├── MarketStateService    (RAM state — sin cambios)
  ├── CorrelationService    ← NUEVO (core, cálculo puro)
  │    ├── lee MarketStateService (read-only)
  │    ├── lee catálogo activo desde SubscriptionManager
  │    ├── produce CorrelationMatrixSnapshot por timeframe
  │    └── swap atómico cada CORRELATION_REFRESH_SECONDS
  ├── FastDeskRuntime  → instancia FastCorrelationPolicy(correlation_service)
  └── SmcDeskRuntime   → instancia SmcCorrelationFormatter(correlation_service)
```

### 4.3 Ciclo de actualización — con optimizaciones

```
loop (cada CORRELATION_REFRESH_SECONDS):
    para cada timeframe en watch_timeframes:

        # Saltar si ninguna serie del timeframe cambió desde el último cómputo
        if not _source_updated_since_last_compute(timeframe):
            continue

        symbols = correlation_service.active_symbols()  # del catálogo activo
        new_snapshot = {}

        para cada par (sym_a, sym_b) en combinations(symbols, 2):
            # Simetría: A,B == B,A → solo calcular triángulo superior
            series_a, series_b, meta = aligner.align(sym_a, sym_b, timeframe)
            if meta.aligned_count < MIN_COVERAGE_BARS:
                pair_value = CorrelationPairValue(coefficient=None, ...)
            else:
                r = pearson(returns(series_a), returns(series_b), window_bars)
                pair_value = CorrelationPairValue(coefficient=r, ...)

            new_snapshot[sym_a][sym_b] = pair_value
            new_snapshot[sym_b][sym_a] = pair_value  # simetría, no recalcular

        # Swap atómico — nunca mutar la matriz activa en sitio
        self._snapshots[timeframe] = new_snapshot
        self._last_compute_success_at[timeframe] = utc_now()
```

**No bloquea el loop de polling** — corre en su propio task asyncio, desacoplado.

### 4.4 Configuración propuesta (`.env`)

```bash
CORRELATION_ENABLED=true
CORRELATION_REFRESH_SECONDS=30        # cada cuánto recalcula
CORRELATION_WINDOW_BARS=50            # velas para rolling window
CORRELATION_MIN_COVERAGE_BARS=30      # mínimo de velas alineadas para considerar el par válido
CORRELATION_RETURN_TYPE=simple        # "simple" o "log" — global, no por caller
```

> Los umbrales operativos (0.85, 0.60, etc.) **no van aquí** — pertenecen a la configuración de cada policy layer.

---

## 5. API del Motor — Solo Cálculo Puro

El `CorrelationService` expone solo tres métodos públicos. **No toma decisiones operativas.**

### 5.1 Consulta por par

```python
pair = correlation_service.get_pair(
    symbol_a="EURUSD",
    symbol_b="GBPUSD",
    timeframe="M30",
)
# → CorrelationPairValue(coefficient=0.87, bars_used=48, coverage_ok=True,
#                        source_stale=False, compute_stale=False)
# → CorrelationPairValue(coefficient=None, ...) si cobertura insuficiente
```

### 5.2 Matriz completa por temporalidad

```python
snapshot = correlation_service.get_matrix(timeframe="M30")
# → CorrelationMatrixSnapshot | None (None si aún no hay primer cómputo)
```

### 5.3 Relaciones de exposición (raw, sin interpretación)

```python
relations = correlation_service.get_exposure_relations(
    symbol="GBPUSD",
    timeframe="M30",
)
# → list[CorrelationPairValue] de todos los pares que incluyen "GBPUSD"
# → ordenados por abs(coefficient) descendente
# → la policy del desk decide qué hacer con estos datos
```

---

## 5b. Policy Layers — Interpretación por Mesa

Todo lo que implique lógica operativa vive aquí, **fuera del core**.

### `fast_desk/correlation/policy.py` — `FastCorrelationPolicy`

```python
class FastCorrelationPolicy:
    HIGH_DIRECT_THRESHOLD = 0.80    # configurable por env
    HIGH_INVERSE_THRESHOLD = -0.80
    MODERATE_THRESHOLD = 0.60

    def check_entry_conflict(
        self,
        new_symbol: str,
        new_side: str,
        open_positions: list[dict],
        timeframe: str,
    ) -> tuple[bool, str]:
        """Consulta CorrelationService y aplica reglas del Fast Desk."""
        ...

    def classify(self, coefficient: float | None) -> str:
        """Clasifica en high_direct / moderate / weak / negligible / high_inverse."""
        ...
```

### `smc_desk/correlation/formatter.py` — `SmcCorrelationFormatter`

```python
class SmcCorrelationFormatter:
    def build_context_snippet(self, symbol: str, timeframe: str) -> str:
        """Formatea la fila de correlación del símbolo para insertar en prompt LLM."""
        ...

    def top_correlations(self, symbol: str, timeframe: str, n: int = 5) -> list[CorrelationPairValue]:
        """Devuelve los N pares más correlados (sin labels operativos)."""
        ...
```

### `control_plane/correlation_presenter.py` — `CorrelationApiPresenter`

Convierte `CorrelationMatrixSnapshot` al schema JSON del endpoint WebUI. Sin lógica de correlación.

---

## 6. Consumo por Mesa

### 6.1 Fast Desk

**Punto de integración**: `FastContextService` + `FastCorrelationPolicy`

Flujo:
```
FastContextService.build(symbol, timeframe)
  → FastCorrelationPolicy.check_entry_conflict(...)   ← llama al core read-only
  → si conflict: gate dura o soft según umbral configurado
  → resultado: flag en FastContext, no en CorrelationService
```

Umbrales (en `FastCorrelationPolicy`, no en el motor):
- Gate dura sugerida: `abs(r) >= HIGH_DIRECT_THRESHOLD` con posición abierta en mismo lado (directa) o lado contrario (inversa)
- Gate suave: `abs(r) >= MODERATE_THRESHOLD` → reducir convicción del setup
- Timeframe de referencia: M30 (contexto activo del Fast Desk)

### 6.2 SMC Desk

**Punto de integración**: `SmcCorrelationFormatter` inyectado en el prompt builder de `smc_desk/analyst/`

Flujo:
```
SmcAnalyst.build_prompt(symbol, timeframe)
  → SmcCorrelationFormatter.build_context_snippet(symbol, timeframe)
  → agrega bloque "## Correlation Context" al prompt
  → el LLM razona sobre confluencia; la decisión es del LLM, no del formatter
```

Gate de concentración: decidida por la policy SMC, no por el formatter.

---

## 7. Elasticidad del Universo de Símbolos

El universo de símbolos **no es estático**. Los símbolos se activan/desactivan desde el WebUI, se persisten en la runtime DB, y son leídos por el `SubscriptionManager`. El motor debe tolerarlo sin estado corrupto.

### 7.1 Fuente del universo activo

El `CorrelationService` consulta el universo de símbolos activos desde el `SubscriptionManager` (la misma fuente que usa el `ConnectorIngress`), **no** desde `MT5_WATCH_SYMBOLS` directamente. Esto asegura que el motor trabaja siempre con el mismo conjunto que está siendo polleado.

### 7.2 Comportamiento ante cambios en runtime

| Evento | Comportamiento del motor |
|--------|-------------------------|
| Nuevo símbolo activado | Se incluye en el próximo ciclo de cómputo; snapshots previos no incluyen ese símbolo |
| Símbolo desactivado | Se excluye del próximo ciclo; clave eliminada del snapshot siguiente |
| Universe vacío | Motor en standby, no calcula ni publica snapshots |
| Universe con 1 símbolo | Sin pares posibles; snapshot vacío con `matrix: {}` |

### 7.3 Invariante de consistencia

Cada `CorrelationMatrixSnapshot` incluye el campo `symbols` que refleja exactamente los símbolos usados en ese ciclo. Nunca hay celdas en `matrix` para símbolos no listados en `symbols`.

El swap atómico garantiza que el snapshot sea siempre internamente consistente, aunque el universo cambie entre ciclos.

---

## 7b. Persistencia

### 7b.1 RAM (obligatorio)

Los snapshots activos viven en RAM dentro de `CorrelationService` como `dict[timeframe, CorrelationMatrixSnapshot]`. Zero latencia en consulta. El swap atómico (`self._snapshots[tf] = new_snapshot`) garantiza que ningún caller vea un snapshot en estado intermedio.

### 7b.2 Runtime DB (Fase 3 — opcional)

Persistir el último snapshot por timeframe en SQLite (`runtime_db.py`) para:
- Disponibilidad desde WebUI sin esperar primer ciclo de cómputo
- Diagnóstico post-mortem

> Por ahora: RAM únicamente. La reincorporación en DB es parte de Fase 3.

---

## 8. Stale Detection — Dos Dimensiones Separadas

La staleness tiene dos causas distintas que no deben mezclarse:

| Dimensión | Campo | Definición |
|-----------|-------|------------|
| `source_stale` | Por par | La fuente (`MarketStateService`) no actualizó candles del símbolo en > `STALE_SOURCE_SECONDS` |
| `compute_stale` | Por timeframe | El task de cómputo no corrió exitosamente en > `2 × CORRELATION_REFRESH_SECONDS` |

**Metadata adicional por snapshot:**
```python
snapshot.snapshot_age_seconds   # segundos desde computed_at
snapshot.last_source_bar_time   # timestamp de la vela más reciente usada
snapshot.last_compute_success_at  # timestamp del último swap atómico exitoso
```

**Casos especiales a no confundir con stale:**
- Mercado cerrado (fin de semana, feriado) → velas no cambian, pero no es anomalía
- Un solo timeframe stale no implica los demás — cada snapshot tiene su propio estado

---

## 8b. Alineador de Series (`aligner.py`)

La alineación **no es por string de timestamp**, sino por epoch UTC canonical:

```python
def align(
    sym_a: str,
    sym_b: str,
    timeframe: str,
    market_state: MarketStateService,
) -> AlignmentResult:
    ...
```

**`AlignmentResult`:**
```python
@dataclass
class AlignmentResult:
    returns_a: np.ndarray | None    # retornos ya calculados, listos para Pearson
    returns_b: np.ndarray | None
    aligned_count: int              # velas donde ambos tienen dato
    left_missing: int               # velas en A sin contraparte en B
    right_missing: int              # velas en B sin contraparte en A
    coverage_ratio: float           # aligned_count / window_bars
    last_common_bar: str            # ISO UTC — timestamp más reciente alineado
```

Normalización de timestamps antes del join:
1. Parsear string ISO UTC a `int` epoch seconds (ya normalizados por el conector)
2. Inner join por epoch
3. Tomar últimas `window_bars` velas del resultado alineado
4. Calcular retornos sobre el array resultante (no antes)

---

## 8c. Consideraciones Técnicas Resueltas

| # | Tema | Decisión |
|---|------|----------|
| 1 | Tipo de retorno | Simple por default; log opcional vía env; **global, no por caller** |
| 2 | Tamaño de ventana | `window_bars=50` — único valor global para el motor |
| 3 | Alineación | Por epoch int UTC, no por string — `AlignmentResult` incluye metadata completa |
| 4 | Umbral de cobertura | `CORRELATION_MIN_COVERAGE_BARS=30` — configurable, aplicado por par |
| 5 | Umbrales operativos | Fuera del motor — en `FastCorrelationPolicy` y `SmcCorrelationFormatter` |
| 6 | Multi-timeframe | Calcular para todos los timeframes en `watch_timeframes` — policy elige cuál usar |
| 7 | numpy/scipy | Pearson con `numpy` puro: `np.corrcoef(a, b)[0,1]`; sin dependencia a scipy |
| 8 | Optimización | Solo recalcular timeframes cuya fuente cambió; cachear simetría A,B == B,A |
| 9 | Snapshot atomicidad | Swap completo por referencia — nunca mutar `_snapshots[tf]` en sitio |

---

## 9. Lo que NO hace este motor

- No hace correlación de ticks raw (no hay `copy_ticks_from` implementado actualmente).
- No hace causalidad (Granger) — solo correlación lineal de Pearson.
- No hace clustering de instrumentos automático — solo consulta puntual o matriz completa.
- No ingiere datos externos (Bloomberg, Reuters) — solo precios internos del broker MT5.
- No reemplaza el análisis fundamental — es un filtro cuantitativo complementario.

---

## 10. Fases de Implementación

### Fase 1 — Motor puro + tests

Objetivo: validar que el motor produce datos correctos y confiables.

```
src/heuristic_mt5_bridge/core/correlation/
  __init__.py
  models.py          ← CorrelationPairValue, CorrelationMatrixSnapshot, AlignmentResult
  aligner.py         ← align(sym_a, sym_b, tf, market_state) → AlignmentResult
  service.py         ← CorrelationService (refresh_timeframe, get_pair, get_matrix,
                                           get_exposure_relations, active_symbols)

tests/core/
  test_correlation_aligner.py     ← cobertura normal, gaps, varianza cero, timestamps
  test_correlation_service.py     ← cómputo Pearson, stale lógica, swap atómico, universe change
  test_correlation_numerical.py   ← NaN, inf, close repetidos, warm-up insuficiente
```

Integración mínima en `CoreRuntimeService`:
- Instanciar `CorrelationService`
- Correr task asyncio de refresh
- Endpoint debug `/api/correlation/matrix?timeframe=M30` (JSON crudo, sin UI)

### Fase 2 — Policy layers + integración por mesa

```
src/heuristic_mt5_bridge/fast_desk/correlation/
  __init__.py
  policy.py          ← FastCorrelationPolicy (check_entry_conflict, classify, thresholds)

src/heuristic_mt5_bridge/smc_desk/correlation/
  __init__.py
  formatter.py       ← SmcCorrelationFormatter (build_context_snippet, top_correlations)
```

Modificaciones en archivos existentes:
- `fast_desk/context/service.py` — inyectar `FastCorrelationPolicy`, agregar resultado en `FastContext`
- `smc_desk/analyst/` — inyectar `SmcCorrelationFormatter` en el prompt builder

### Fase 3 — Endpoint HTTP + WebUI

```
src/heuristic_mt5_bridge/control_plane/
  correlation_presenter.py   ← CorrelationApiPresenter (serializa snapshot a JSON para WebUI)

apps/webui/src/
  routes/Correlation.tsx     ← página de heatmap (ver Sección 11)
  api/client.ts              ← agregar getCorrelationMatrix()
  types/api.ts               ← agregar CorrelationMatrixResponse, CorrelationPairCell
  App.tsx                    ← agregar <Route path="/correlation">
  components/AppNav.tsx      ← agregar nav item
```

---

## 11. WebUI — Página de Correlación

### 11.1 Descripción general

> **Esta sección corresponde a Fase 3.** No bloquea Fase 1 ni Fase 2. Solo implementar tras validar motor y policy con tests.

Nueva ruta `/correlation` dentro del WebUI (SolidJS). Muestra la **heatmap matrix** de todos los símbolos activos del catálogo, con tabs por temporalidad y colorizado dinámico verde/rojo igual a la referencia visual adjunta.

**No requiere dependencias nuevas**: la tabla se construye con CSS puro sobre el sistema de variables ya existente (`--bg-panel`, `--green`, `--red`, etc.).

Los símbolos mostrados son exactamente los del universo activo en ese momento — si cambia el catálogo, la página refleja el snapshot más reciente (que puede tener distinta cantidad de símbolos que el anterior).

---

### 11.2 Endpoint HTTP requerido (backend Python)

El frontend consume un único endpoint GET:

```
GET /api/correlation/matrix?timeframe=M30
```

**Response schema** (a agregar en `types/api.ts`):

```typescript
export interface CorrelationPairCell {
  coefficient: number;       // -1.0 a 1.0
  pct: number;               // coefficient × 100, entero redondeado
  label: string;             // "high_direct" | "high_inverse" | "moderate" | "weak" | "negligible"
  bars_used: number;
  coverage_ok: boolean;
}

export interface CorrelationMatrixResponse {
  timeframe: string;
  computed_at: string;       // ISO UTC
  window_bars: number;
  symbols: string[];         // orden de filas y columnas
  stale: boolean;
  matrix: Record<string, Record<string, CorrelationPairCell>>;
  // matrix["EURUSD"]["GBPUSD"] → celda del par
}
```

Agregar `getCorrelationMatrix(timeframe: string)` en `apps/webui/src/api/client.ts`.

---

### 11.3 Estructura de archivos WebUI

```
apps/webui/src/
  routes/
    Correlation.tsx         ← página principal (NUEVO)
  api/
    client.ts               ← agregar getCorrelationMatrix() (modificar)
  types/
    api.ts                  ← agregar CorrelationMatrixResponse, CorrelationPairCell (modificar)
  App.tsx                   ← agregar <Route path="/correlation"> (modificar)
  components/
    AppNav.tsx              ← agregar nav item (modificar)
```

---

### 11.4 Diseño de `Correlation.tsx`

#### Layout general

```
┌─────────────────────────────────────────────────────────────────┐
│  ◈ Correlation Matrix                    [stale badge] [UTC ts] │  ← header strip
├─────────────────────────────────────────────────────────────────┤
│  [M1] [M5] [M15] [M30] [H1] [H4] [D1]   window: 50 bars        │  ← timeframe tabs
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌────────┬────────┬────────┬────────┬────────┬────────┐       │
│   │        │ EURUSD │ GBPUSD │ USDJPY │ XAUUSD │ USDCAD │       │  ← header row (col labels)
│   ├────────┼────────┼────────┼────────┼────────┼────────┤       │
│   │ EURUSD │   —    │  +87   │  -61   │  +12   │  -42   │       │  ← row
│   │ GBPUSD │  +87   │   —    │  -55   │  +08   │  -38   │       │
│   │ USDJPY │  -61   │  -55   │   —    │  -22   │  +44   │       │
│   │ XAUUSD │  +12   │  +08   │  -22   │   —    │  -09   │       │
│   │ USDCAD │  -42   │  -38   │  +44   │  -09   │   —    │       │
│   └────────┴────────┴────────┴────────┴────────┴────────┘       │
│                                                                  │
│  [leyenda de color]   [coverage warning si stale]                │
└─────────────────────────────────────────────────────────────────┘
```

#### Comportamiento de columnas rotadas

Los **labels de columna** (`EURUSD`, `GBPUSD`, etc.) se rotan 45° o 90° para acomodar muchos símbolos sin overflow horizontal — idéntico a la imagen de referencia.

```css
.corr-col-header {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  white-space: nowrap;
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 4px 2px;
}
```

#### Colorizado de celdas

Se interpola entre `--green` y `--red` usando el valor `pct` (-100 a +100):

```typescript
function cellBackground(pct: number): string {
  if (pct > 0) {
    // verde con opacidad proporcional: 0 → transparent, 100 → var(--green) full
    const alpha = Math.abs(pct) / 100;
    return `rgba(34, 197, 94, ${(alpha * 0.75).toFixed(2)})`;   // --green
  } else if (pct < 0) {
    const alpha = Math.abs(pct) / 100;
    return `rgba(239, 68, 68, ${(alpha * 0.75).toFixed(2)})`;   // --red
  }
  return "transparent";
}

function cellTextColor(pct: number): string {
  // texto siempre legible: blanco sobre rojo/verde oscuro, gris en neutro
  return Math.abs(pct) > 40 ? "var(--text-primary)" : "var(--text-secondary)";
}
```

Celda diagonal (mismo símbolo): mostrar `—` con fondo `var(--bg-elevated)`.

#### Tabs de temporalidad

```typescript
// Tabs reutilizan el patrón ya existente en FastDesk/SmcDesk
const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const [activeTimeframe, setActiveTimeframe] = createSignal("M30");
```

El tab activo sigue el estilo de accent `var(--cyan-live)` ya establecido en el sistema.

#### Polling / refresh

```typescript
// Recarga cada CORRELATION_REFRESH_SECONDS (leído del response o hardcoded 30s)
const [matrix, { refetch }] = createResource(
  activeTimeframe,
  (tf) => api.getCorrelationMatrix(tf)
);
setInterval(refetch, 30_000);
onCleanup(() => clearInterval(intervalId));
```

#### Estado `stale`

Si `matrix().stale === true` → mostrar badge rojo `STALE` junto al timestamp, y overlay semitransparente sobre la tabla con texto `"Recalculating..."`.

#### Coverage warning

Si alguna celda tiene `coverage_ok === false` → mostrar `⚠` en superíndice sobre el número, con tooltip `"Insufficient bars (N aligned)"`.

---

### 11.5 Modificaciones en archivos existentes

#### `App.tsx` — agregar ruta

```tsx
import Correlation from "./routes/Correlation";
// ...dentro del Router:
<Route path="/correlation" component={Correlation} />
```

#### `AppNav.tsx` — agregar nav item

El item va en `deskItems` (sección Desks), entre SMC Desk y Risk:

```typescript
const deskItems: NavItem[] = [
  { path: "/fast",          icon: "⚡", title: "Fast Desk",    accent: "var(--teal)" },
  { path: "/fast/pipeline", icon: "▸", title: "Pipeline",     accent: "var(--teal)" },
  { path: "/smc",           icon: "◆", title: "SMC Desk",     accent: "var(--blue)" },
  { path: "/correlation",   icon: "⊞", title: "Correlation",  accent: "var(--cyan-live)" },  // ← NUEVO
  { path: "/risk",          icon: "⊘", title: "Risk Center",  accent: "var(--amber)" },
];
```

---

### 11.6 Leyenda visual (pie de tabla)

```
  ██ Alto directo (≥85)    ██ Moderado (60–84)    □ Débil (<60)    ██ Alto inverso (≤-85)
```

Implementada como una fila de `div` con los mismos colores interpolados de `cellBackground()`.

---

### 11.7 Consideraciones de performance en el frontend

| Síntoma | Causa | Solución |
|---------|-------|---------|
| Render lento con >20 símbolos | `N×N` celdas recalculando estilos inline | Usar `createMemo` para precomputar colores; no recalcular en cada render |
| Tabla desborda en pantallas pequeñas | Muchos símbolos | `overflow-x: auto` en el contenedor; sticky primera columna (row labels) |
| Flash de stale data al cambiar tab | Fetch async sin fallback | Mostrar datos previos con overlay `"Loading..."` mientras llega nueva temporalidad |

---

### 11.8 Archivos a crear / modificar (WebUI)

| Archivo | Acción |
|---------|--------|
| `apps/webui/src/routes/Correlation.tsx` | Crear |
| `apps/webui/src/api/client.ts` | Modificar — agregar `getCorrelationMatrix()` |
| `apps/webui/src/types/api.ts` | Modificar — agregar `CorrelationMatrixResponse`, `CorrelationPairCell` |
| `apps/webui/src/App.tsx` | Modificar — agregar `<Route path="/correlation">` |
| `apps/webui/src/components/AppNav.tsx` | Modificar — agregar nav item |

---

## 12. Guía de Consumo por Mesa

> Esta sección documenta la integración **ya implementada** del motor de correlación con cada mesa de trading y el runtime central.

---

### 12.1 Wiring en `CoreRuntimeService`

#### Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `CORRELATION_ENABLED` | `false` | Activa el motor. En `false` no se crea ningún objeto ni tarea. |
| `CORRELATION_TIMEFRAMES` | `M5,H1` | Timeframes a computar (CSV, case-insensitive). |
| `CORRELATION_WINDOW_BARS` | `50` | Ventana de barras para cada cálculo Pearson. |
| `CORRELATION_MIN_COVERAGE_BARS` | `30` | Mínimo de barras alineadas para marcar `coverage_ok=True`. |
| `CORRELATION_RETURN_TYPE` | `simple` | Tipo de retornos: `simple` o `log`. |
| `CORRELATION_REFRESH_SECONDS` | `60` | Periodicidad del loop de refresh. |
| `CORRELATION_STALE_SOURCE_SECONDS` | `300` | Segundos sin update para marcar `source_stale=True`. |

#### Acceso programático

```python
from heuristic_mt5_bridge.core.runtime.service import CoreRuntimeService

# Acceso al servicio (None si CORRELATION_ENABLED=false)
core: CoreRuntimeService = ...
svc = core.correlation_service  # CorrelationService | None

if svc is not None:
    pair = svc.get_pair("EURUSD", "GBPUSD", "M5")
    # pair.coefficient: float | None
    # pair.coverage_ok: bool
    # pair.source_stale: bool
```

#### Loop de lifecycle

`CorrelationService.refresh_loop()` se añade como `asyncio.Task` dentro del `TaskGroup` de `run_forever()`. Se cancela limpiamente cuando `CoreRuntimeService.shutdown()` dispara el `_stop_event`.

---

### 12.2 Fast Desk — `FastCorrelationPolicy`

#### Instanciación

```python
from heuristic_mt5_bridge.fast_desk.correlation import FastCorrelationPolicy
from heuristic_mt5_bridge.core.correlation import CorrelationService

policy = FastCorrelationPolicy(
    correlation_service,        # CorrelationService del core runtime
    high_threshold=0.80,        # default
    moderate_threshold=0.60,    # default
    timeframe="M5",             # default
)
```

#### Inyección en `FastContextService`

```python
from heuristic_mt5_bridge.fast_desk.context.service import FastContextService

context_service = FastContextService(
    config=fast_context_config,
    correlation_policy=policy,   # opcional — None desactiva silenciosamente
)
```

#### Llamada con posiciones abiertas

```python
context = context_service.build_context(
    symbol="EURUSD",
    candles_m1=m1,
    candles_m5=m5,
    pip_size=0.0001,
    point_size=0.00001,
    open_positions=[              # lista de dicts de ownership_registry.list_open()
        {"symbol": "GBPUSD", "side": "sell", ...},
    ],
)
```

#### Salida en `FastContext`

`FastContext.details["correlation"]` contiene:

```json
{
  "timeframe": "M5",
  "pairs": [
    {
      "symbol": "GBPUSD",
      "coefficient": 0.91,
      "classification": "high",
      "coverage_ok": true,
      "coverage_ratio": 0.96,
      "bars_used": 48,
      "source_stale": false
    }
  ],
  "matrix_computed_at": "2026-04-05T10:30:00Z",
  "all_pairs_coverage_ok": true
}
```

Un conflicto de correlación (e.g. hedge implícito con GBPUSD) se registra como warning en `FastContext.warnings`:

```
"correlation_conflict:implicit_hedge:EURUSD-GBPUSD(r=+0.91,new=buy,open=sell)"
```

#### Clasificaciones de `classify(coefficient)`

| Resultado | Condición |
|---|---|
| `"high"` | `\|r\| ≥ 0.80` |
| `"moderate"` | `0.60 ≤ \|r\| < 0.80` |
| `"low"` | `0 < \|r\| < 0.60` |
| `"none"` | `r == 0.0` |
| `"unavailable"` | `coefficient is None` |

#### Conflictos detectados por `check_entry_conflict`

| Caso | Condición | Flag |
|---|---|---|
| Hedge implícito | r ≥ 0.80, nuevaSide ≠ posiciónAbiertaSide | `True` |
| Concentración inversa | r ≤ −0.80, nuevaSide == posiciónAbiertaSide | `True` |
| Sin conflicto | cualquier otro caso | `False` |

---

### 12.3 SMC Desk — `SmcCorrelationFormatter`

#### Instanciación

```python
from heuristic_mt5_bridge.smc_desk.correlation import SmcCorrelationFormatter

formatter = SmcCorrelationFormatter(
    correlation_service,   # CorrelationService del core runtime
    timeframe="H1",        # default — SMC usa contexto estructural de largo plazo
    top_n=5,               # default
)
```

#### Inyección en `build_heuristic_output` / `run_smc_heuristic_analyst`

```python
from heuristic_mt5_bridge.smc_desk.analyst.heuristic_analyst import run_smc_heuristic_analyst

result = await run_smc_heuristic_analyst(
    symbol="EURUSD",
    trigger_reason="sweep_detected",
    trigger_payload={...},
    service=market_state,
    db_path=db_path,
    broker_server=broker_server,
    account_login=account_login,
    spec_registry=spec_registry,
    config=smc_config,
    correlation_formatter=formatter,  # opcional — None omite el bloque
)
```

#### Salida en `analyst_input`

`result["analyst_input"]["correlation_context"]` contiene:

```json
{
  "timeframe": "H1",
  "top_pairs": [
    {"symbol": "GBPUSD", "coefficient": 0.91, "bars_used": 48, "coverage_ratio": 0.96, "source_stale": false},
    {"symbol": "USDJPY", "coefficient": -0.84, "bars_used": 47, "coverage_ratio": 0.94, "source_stale": false}
  ],
  "snippet": "CORRELATION (H1):\n  GBPUSD: r=+0.91 [high]  coverage=48 bars\n  USDJPY: r=-0.84 [high]  coverage=47 bars\n[matrix computed 2026-04-05T10:30:00Z]",
  "matrix_computed_at": "2026-04-05T10:30:00Z",
  "symbols_in_universe": 8
}
```

El campo `snippet` está pensado para incluirlo directamente en el prompt del LLM validator. El validator de SMC puede incorporarlo al contexto estructural antes de evaluar los candidatos.

---

### 12.4 Flujo end-to-end con CORRELATION_ENABLED=true

```
Boot
  └─ CoreRuntimeService.__init__
       └─ CorrelationService(market_state, subscription_manager, ...)
            └─ self._snapshots = {}  ← vacío hasta primer refresh

run_forever (TaskGroup)
  ├─ market_state loop  (poll MT5 → MarketStateService)
  ├─ ...otros loops...
  └─ correlation loop   (CorrelationService.refresh_loop)
       └─ cada 60s:
            └─ por cada timeframe en ["M5", "H1"]:
                 └─ SubscriptionManager.subscribed_universe()  ← universo elástico
                 └─ por cada par (sym_a, sym_b):
                      └─ MarketStateService.get_candles(sym_a, tf, bars=50)
                      └─ MarketStateService.get_candles(sym_b, tf, bars=50)
                      └─ align_and_returns(...)   ← inner join por epoch
                      └─ _pearson(returns_a, returns_b)  ← pure Python
                      └─ CorrelationPairValue(coefficient, coverage_ok, ...)
                 └─ CorrelationMatrixSnapshot  ← swap atómico

Fast Desk cycle (por símbolo)
  └─ FastContextService.build_context(..., open_positions=[...])
       ├─ FastCorrelationPolicy.build_details(symbol)
       │    └─ FastContext.details["correlation"] = {...}
       └─ FastCorrelationPolicy.check_entry_conflict(symbol, htf_bias, open_positions)
            └─ si conflicto: FastContext.warnings += ["correlation_conflict:..."]

SMC Desk cycle (por trigger)
  └─ run_smc_heuristic_analyst(..., correlation_formatter=formatter)
       └─ build_heuristic_output(..., correlation_formatter=formatter)
            └─ SmcCorrelationFormatter.build_context_dict(symbol)
                 └─ analyst_input["correlation_context"] = {top_pairs, snippet, ...}
            └─ → LLM validator recibe analyst_input con bloque de correlación
```

---

### 12.5 Acceso directo desde control plane / WebUI (futuro — Fase 3)

El `CoreRuntimeService` expone `self.correlation_service` públicamente. Cuando se implemente el endpoint HTTP (Fase 3), bastará con:

```python
# En el router FastAPI
@router.get("/correlation/{timeframe}")
async def get_correlation_matrix(timeframe: str):
    svc = runtime.correlation_service
    if svc is None:
        raise HTTPException(503, "Correlation engine disabled")
    matrix = svc.get_matrix(timeframe)
    if matrix is None:
        raise HTTPException(503, "Matrix not yet computed")
    return matrix  # serializable con orjson
```

---

*Sección 12 añadida post-implementación — Abril 2026.*
