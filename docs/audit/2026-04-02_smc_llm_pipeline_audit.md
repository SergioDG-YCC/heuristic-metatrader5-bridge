# Auditoría flujo Python ↔ LLM — SMC Desk

**Fecha**: 2026-04-02
**Alcance**: `src/heuristic_mt5_bridge/smc_desk/` — pipeline completo de inferencia LLM
**Entorno**: Python + LocalAI (Docker Desktop) + Gemma 3 4B/12B QAT

---

## Resumen ejecutivo

El diseño del pipeline LLM en SMC Desk **está fundamentalmente bien orientado**: el LLM se usa exclusivamente como **validador semántico** de una tesis construida 100% heurísticamente en Python. No genera precios, no inventa candidatos, no redacta narrativa libre. Hay exactamente **1 llamada HTTP al LLM por ciclo de análisis**, con un prompt de sistema de ~200 tokens y un contrato de salida JSON estricto.

**Sin embargo, hay problemas reales y concretos que agregan latencia evitable:**

| Categoría | Impacto estimado |
|---|---|
| `max_tokens` no se pasa al LLM (bug); `.env` dice 8192 | Riesgo latente alto |
| Payload de input inflado (thesis completa + zonas) | 2000-5000 tokens de prefill innecesarios |
| Sin connection reuse (nuevo TCP por request) | +50-200ms por llamada en Docker |
| `temperature` hardcodeada, no del config | Menor, pero incoherente |
| Lectura de disco de prompts en cada llamada | ~1-5ms, bajo |
| Sin retry con backoff (aceptable hoy) | Trade-off consciente |

**Veredicto**: no es necesario reescribir nada. Hay 3-4 cambios puntuales que pueden reducir la latencia percibida un 30-60% sin tocar la arquitectura.

---

## Mapa del flujo actual

### Paso a paso completo

```
Scanner poll (cada 300s)
    │
    ▼
SmcScannerService.run_forever()  ─[asyncio.to_thread]─► scan_symbol() (CPU)
    │                                                      │
    │  Emite evento: zone_approaching / sweep_detected     │
    ▼                                                      │
SmcDeskService._on_scanner_event()                         │
    │  put_nowait() en asyncio.Queue                       │
    ▼                                                      │
SmcDeskService._dispatch_loop()                            │
    │  Throttle: 300s cooldown por símbolo                 │
    ▼                                                      │
run_smc_heuristic_analyst()     ◄──────────────────────────┘
    │
    ├── [1] build_heuristic_output()          ←  asyncio.to_thread (CPU-bound)
    │       ├── get_candles D1/H4/H1
    │       ├── detect_market_structure × 3 TFs
    │       ├── fibo_levels_for_structure
    │       ├── count_waves (Elliott)
    │       ├── load_active_smc_zones (SQLite)
    │       ├── _derive_bias, _score_zone, _build_operation_candidate
    │       └── Returns: {analyst_input, heuristic_output, active_zones, current_price}
    │
    ├── [2] validate_heuristic_thesis()       ←  asyncio.to_thread (CPU-bound)
    │       ├── Valida precio, side/zone, RR, trazabilidad
    │       └── Returns: {normalized_thesis, validation_summary, issues}
    │
    ├── [3] call_smc_validator()              ←  AQUÍ ENTRA EL LLM
    │       ├── Construye compact_json de (thesis + validation_summary)
    │       ├── Lee system.md y user.md de disco
    │       ├── Arma messages: [system, user]
    │       ├── _call_localai_sync() via asyncio.to_thread
    │       │     ├── urllib.request.Request → POST /v1/chat/completions
    │       │     ├── model, temperature=0.1, max_tokens, response_format=json_object
    │       │     └── Espera respuesta completa (NO streaming)
    │       ├── _extract_json() del content
    │       ├── _normalize_validator_output() → {decision, confidence, issues, adjustments, summary}
    │       └── _apply_validator_result() → modifica thesis según decision
    │
    └── [4] save_smc_thesis()                 ←  asyncio.to_thread (SQLite write)
```

### Archivos involucrados en el pipeline LLM

| Archivo | Rol |
|---|---|
| `smc_desk/runtime.py` | Orquestador: scanner → queue → dispatch → analyst |
| `smc_desk/analyst/heuristic_analyst.py` | Pipeline completo: build → validate → LLM → persist |
| `smc_desk/llm/validator.py` | Único punto de contacto con LocalAI |
| `smc_desk/prompts/system.md` | System prompt (~200 tokens) |
| `smc_desk/prompts/user.md` | User prompt template (4 líneas + JSON) |
| `smc_desk/validators/heuristic.py` | Hard validators (sin LLM) |
| `smc_desk/state/thesis_store.py` | Persistencia SQLite |

---

## Hallazgos

### H1. BUG: `max_tokens` no se pasa al LLM validator [ALTA]

**Archivo**: `heuristic_analyst.py` líneas ~781-785

```python
config={
    "llm_model": config.llm_model,
    "llm_timeout_seconds": config.llm_timeout_seconds,
},
```

El `SmcAnalystConfig` carga `SMC_LLM_MAX_TOKENS=8192` del `.env`, pero **nunca lo pasa** al dict de config del validator. El validator en `validator.py` línea ~227 hace:

```python
max_tokens = int(config.get("max_tokens", 500))
```

**Resultado**: siempre usa 500. El `.env` dice 8192 pero es ignorado.

**Impacto**: Hoy es **accidentalmente benigno** — 500 es razonable para la salida esperada (~50-150 tokens). Pero si alguien "corrige" el bug y conecta los 8192, la latencia podría explotar si el modelo se desvía. Además, incluso 500 es generoso para un JSON de 5 campos.

**Severidad**: Alta (bug real, impacto latente).
**Afecta**: 4B y 12B igualmente.

---

### H2. Payload de input inflado: se envía la thesis completa al LLM [MEDIA]

**Archivo**: `validator.py` líneas ~240-247

```python
validator_input = {
    "symbol": ...,
    "current_price": ...,
    "trigger_reason": ...,
    "heuristic_thesis": heuristic_thesis,    # ← COMPLETA
    "validation_summary": validation_summary,
}
```

`heuristic_thesis` contiene:
- `operation_candidates` (cada uno con ~20 campos incluyendo justificaciones de texto)
- `watch_conditions`, `invalidations` (listas de frases)
- `prepared_zones` (lista de IDs)
- `multi_timeframe_alignment`, `elliott_count`, `fibo_levels`
- `base_scenario` (frase de texto)
- `review_strategy`

**Estimación**: El `compact_json` puede alcanzar **2000-5000 tokens** de input dependiendo del número de candidates y zonas.

**Severidad**: Media.
**Afecta**: Más a 12B (prefill es más lento).

---

### H3. Sin connection reuse — nueva conexión TCP por cada llamada [MEDIA]

**Archivo**: `validator.py` líneas ~163-180

Se usa `urllib.request.urlopen()` sin session, sin keep-alive. Cada llamada paga ~50-200ms extra en Docker Desktop por establecimiento de conexión TCP.

**Severidad**: Media.
**Afecta**: 4B y 12B igualmente.

---

### H4. `temperature` hardcodeada en HTTP, no del config [BAJA]

**Archivo**: `validator.py` línea ~158

```python
"temperature": 0.1,
```

El `SmcAnalystConfig` carga `llm_temperature` del `.env` pero el validator ignora el config y hardcodea 0.1.

**Severidad**: Baja.

---

### H5. Lectura de prompts desde disco en cada llamada [BAJA]

**Archivo**: `validator.py` líneas ~36-40

```python
def _load_prompt(name: str, *, compact_json: str = "") -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
```

**Severidad**: Baja (~2-20ms total).

---

### H6. No hay observabilidad de latencia del LLM [MEDIA]

No se mide ni se loguea: tiempo de respuesta del LLM, tokens de input/output, modelo.

**Severidad**: Media (impide diagnosticar).

---

### H7. Puntos donde la app agrega latencia evitable [RESUMEN]

| Punto | Costo estimado |
|---|---|
| TCP sin reuse | 50-200ms |
| Lectura disco prompts | 2-20ms |
| Payload inflado (prefill tokens) | 20-40% del prefill time |
| `max_tokens` desconectado | Riesgo latente |
| Ausencia de métricas | Costo indirecto |

---

## Costos inevitables vs evitables

| Capa | Tipo | Estimación |
|---|---|---|
| Prefill tokens (input → modelo) | **Inevitable** (proporcional al tamaño del prompt) | 1-10s |
| Decode tokens (output) | **Inevitable** (dominado por tamaño de output) | 0.5-3s |
| Red Docker → LocalAI | **Inevitable** pero reducible | 10-50ms |
| TCP handshake nuevo | **Evitable** | 50-200ms |
| Tokens input innecesarios | **Evitable** | 20-40% del prefill |
| Lectura disco prompts | **Evitable** | 2-20ms |
| Falta de métricas | **Evitable** | costo indirecto |

---

## Riesgos de diseño

### Lo que está BIEN hecho

1. El LLM NO genera precios, ni candidatos, ni decide side. Todo es heurístico.
2. Una sola llamada HTTP por ciclo de análisis.
3. `response_format: json_object` fuerza JSON.
4. System prompt conciso con prohibiciones explícitas.
5. Fallback graceful: si LLM falla, se acepta la thesis heurística.
6. Separación clara: scanner → analyst → validator → persist.
7. Cooldown de 300s por símbolo.

### Riesgos identificados

| Riesgo | Severidad |
|---|---|
| Payload inflado al LLM | Media |
| `max_tokens` desconectado del config | Alta (latente) |
| Sin métricas de latencia LLM | Media |
| `summary` en output contract invita a redactar | Baja-Media |

---

## Validación de hipótesis

| # | Hipótesis | Veredicto |
|---|---|---|
| H1 | El sistema genera más tokens de los que necesita | **Parcialmente válida** — `summary` y `max_tokens=500` permiten más output, pero `response_format=json_object` limita divagación |
| H2 | El prompt mezcla decisión con redacción | **Falsa** — system prompt es claro; solo `summary` tiene componente narrativo |
| H3 | Se piden explicaciones donde bastaría JSON corto | **Parcialmente válida** — solo por `summary` e `issues/adjustments` como strings |
| H4 | Latencia por esperar respuesta larga innecesaria | **Falsa en output, válida en input** — output es ~100 tokens, input es innecesariamente largo |
| H5 | Diseño asume costo en "pensamiento" cuando prefill domina | **Parcialmente válida** — thesis completa implica prefill innecesario |
| H6 | Deberían haber diferencias entre 4B y 12B | **Válida** — hoy no hay distinción |
| H7 | App agrega latencia evitable | **Válida** — TCP sin reuse, disco, payload inflado, max_tokens desconectado |
