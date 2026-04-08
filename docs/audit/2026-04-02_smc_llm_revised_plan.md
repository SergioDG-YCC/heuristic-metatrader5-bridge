# Revisión del plan de acción — SMC LLM Pipeline

**Fecha**: 2026-04-02
**Precede a**: `2026-04-02_smc_llm_pipeline_audit.md` (auditoría base)
**Sigue a**: Decisiones arquitectónicas sobre reducción semántica, presupuestos dinámicos y ruta LoRA/QLoRA

---

## 1. Qué se mantiene del plan original

- **El diagnóstico estructural es correcto**: 1 llamada LLM por ciclo, validador (no generador), fallback graceful, cooldown por símbolo.
- **H1** (bug config desconectado) es un bug verificado en `heuristic_analyst.py` línea ~781.
- **H3** (connection reuse) sigue vigente.
- **H5** (lectura de prompts de disco) sigue vigente como quick win.
- **La arquitectura pipeline** (scanner → heuristic build → hard validation → LLM validation → persist) está bien y no necesita reestructurarse.
- **`response_format: json_object`** fuerza JSON correctamente.
- **System prompt conciso** con prohibiciones explícitas.

## 2. Qué se corrige del plan original

### 2.1 La reducción de payload fue demasiado agresiva

La propuesta original de reemplazar `heuristic_thesis` por 3-4 campos (`bias`, `candidate_count`, etc.) fue **reducción bruta**, no semántica. El LLM validator necesita evaluar coherencia interna — si se quita `watch_conditions`, `invalidations`, la relación bias/side de candidates y el MTF alignment, pierde capacidad de detectar contradicciones.

**Corrección**: Construir una proyección semántica que preserve las relaciones lógicas sin arrastrar campos operativos irrelevantes.

### 2.2 Los números fijos fueron hardcodes arbitrarios

El plan original decía `max_tokens=200`, `cap a 300`, `bajar .env a 300`. No hay justificación para esos números específicos y no contempla variación por complejidad del caso ni por modelo.

**Corrección**: Política de presupuestos configurables y derivables vía env vars.

### 2.3 El logging fue planteado solo como observabilidad pasiva

El plan original decía "agregar timing log" y "loguear `usage`". Insuficiente para construir un pipeline de especialización futura.

**Corrección**: Dos capas de logging: operativo + trazabilidad semántica para dataset.

### 2.4 La propuesta de eliminar `summary` fue prematura

`summary` alimenta `analyst_notes` y sería dato útil para datasets de entrenamiento. Se mantiene pero acotado.

---

## 3. Relectura de H1 ~ H7

### H1: Bug max_tokens desconectado — **VIGENTE, reformulado**

Bug real. La corrección no es `min(config.llm_max_tokens, 200)`. Es: conectar el cable correctamente, usar `SMC_LLM_MAX_TOKENS` como safety ceiling, y agregar `SMC_LLM_OUTPUT_BUDGET` como presupuesto operativo configurable.

### H2: Payload inflado — **REFORMULADO: proyección semántica**

Campos con valor semántico para validación vs campos sin valor:

| Campo | ¿Útil? | ¿Proyectar? |
|---|---|---|
| `bias`, `bias_confidence` | Sí | Sí |
| `status` | Sí | Sí |
| `multi_timeframe_alignment` | Sí | Sí, compacto |
| `watch_conditions` | Sí | Sí |
| `invalidations` | Sí | Sí |
| `operation_candidates` (side, rr, confluences, entry_model, quality) | Sí | Sí, compacto |
| `operation_candidates` (justificaciones texto) | No | No |
| `operation_candidates` (volume_options, validation_flags) | No | No |
| `prepared_zones` (IDs) | No | No |
| `review_strategy` | No | No |
| `next_review_hint_seconds` | No | No |
| `base_scenario` | Parcial | Opcional |
| `fibo_levels`, `elliott_count` | Parcial | Compacto |
| `watch_levels` | Bajo | No |

### H3: Connection reuse — **SIN CAMBIOS**

### H4: Temperature hardcodeada — **VIGENTE, ampliado** — debe venir del config con default diferente potencial por modelo.

### H5: Lectura de prompts — **VIGENTE + versioning**: cache module-level + hash SHA1 para `prompt_version`.

### H6: Observabilidad — **REFORMULADO: dos capas** (operativo + trazabilidad semántica).

### H7: App latencia evitable — **VIGENTE**, la lista de puntos no cambia.

---

## 4. Nuevo enfoque para payload y presupuesto de tokens

### 4.1 Proyección semántica del input

Función `_build_validator_projection(heuristic_thesis, validation_summary)` en `validator.py`:
- Preserva campos con valor semántico (tabla H2).
- Compacta candidates eliminando campos no semánticos.
- Preserva `watch_conditions`, `invalidations`.
- Incluye MTF alignment.
- Opcionalmente `elliott_count` / `fibo_levels` en forma resumida.

Resultado esperado: ~400-1000 tokens en lugar de ~2000-5000.

### 4.2 Política de presupuesto de tokens

**A. Safety ceiling** (`SMC_LLM_MAX_TOKENS`): Previene runaway decode. Valor operativo en `.env`: 400-600.

**B. Output budget** (`SMC_LLM_OUTPUT_BUDGET`, nueva): Lo que se espera necesitar. Se usa como `max_tokens`. Default: fallback a `SMC_LLM_MAX_TOKENS`, sino 400.

**C. Input budget**: No truncar. La proyección controla tamaño. Medir `len(compact_json)` como proxy. Warning si excede threshold (`SMC_LLM_INPUT_CHARS_WARNING`), sin corte automático.

**D. Degradación progresiva**: Log warning si latencia > threshold configurable. Base para auto-reducción futura (no implementar ahora).

---

## 5. Diseño de logging

### 5.1 Capa operativa

Print estructurado + opcionalmente insert en `smc_events_log`:

| Campo | Tipo | Obligatorio |
|---|---|---|
| `timestamp` | ISO8601 | Sí |
| `symbol` | str | Sí |
| `model` | str | Sí |
| `elapsed_seconds` | float | Sí |
| `prompt_tokens` | int | Sí |
| `completion_tokens` | int | Sí |
| `decision` | str | Sí |
| `confidence` | str | Sí |
| `used_llm` | bool | Sí |
| `error_type` | str\|null | Sí |
| `output_budget` | int | Sí |
| `input_chars` | int | Opcional |

### 5.2 Capa trazabilidad semántica (dataset future-proof)

Nueva tabla `smc_validator_traces`:

| Campo | Tipo | Para qué |
|---|---|---|
| `trace_id` | TEXT PK | UUID del caso |
| `timestamp` | TEXT | ISO8601 |
| `broker_server` | TEXT | particionamiento |
| `account_login` | INTEGER | particionamiento |
| `symbol` | TEXT | dominio |
| `trigger_reason` | TEXT | contexto |
| `model` | TEXT | modelo usado |
| `prompt_version` | TEXT | hash SHA1 de system+user prompt |
| `heuristic_rules_version` | TEXT | versión código heurístico |
| `validator_projection_json` | TEXT | proyección enviada al LLM |
| `validation_summary_json` | TEXT | output hard validators |
| `llm_raw_response` | TEXT | respuesta raw pre-normalización |
| `llm_normalized_result_json` | TEXT | resultado normalizado |
| `heuristic_decision_pre` | TEXT | status pre-LLM |
| `final_decision` | TEXT | validator_decision aplicado |
| `elapsed_seconds` | REAL | latencia |
| `prompt_tokens` | INTEGER | tokens input |
| `completion_tokens` | INTEGER | tokens output |
| `outcome_label` | TEXT | null; etiquetar después |
| `outcome_updated_at` | TEXT | cuándo se etiquetó |
| `outcome_source` | TEXT | manual/auto |

---

## 6. Ruta evolutiva hacia LoRA / QLoRA

### Etapa actual: Prompting + validación semántica

### Etapa siguiente: Logging + dataset curado
- Implementar `smc_validator_traces`
- Implementar `prompt_version`
- Implementar `heuristic_rules_version`
- Registrar cada llamada exitosa

### Etapa futura: Fine-tuning ligero
Prerrequisitos: ≥500 trazas etiquetadas, proceso de etiquetado, distribución razonable de clases, infra de fine-tuning (Colab/Unsloth + ≥16GB VRAM).

### Lo que NO hacer todavía
- No entrenar sin dataset etiquetado
- No abstraer `ValidatorEngine` con plugins
- No intentar LoRA con <200 ejemplos

---

## 7. Plan de acción priorizado

### Prioridad 1: Quick wins

| # | Acción | Archivo |
|---|---|---|
| 1.1 | Conectar max_tokens, temperature, localai_base_url al validator | `heuristic_analyst.py` |
| 1.2 | Usar temperature del config en HTTP | `validator.py` |
| 1.3 | Cache prompts + hash SHA1 | `validator.py` |
| 1.4 | Ajustar .env (max_tokens razonable, nueva var output_budget) | `.env` |

### Prioridad 2: Logging operativo + timing

| # | Acción | Archivo |
|---|---|---|
| 2.1 | Medir elapsed time | `validator.py` |
| 2.2 | Extraer y loguear `usage` | `validator.py` |
| 2.3 | Print estructurado | `validator.py` |

### Prioridad 3: Proyección semántica del input

| # | Acción | Archivo |
|---|---|---|
| 3.1 | Escribir `_build_validator_projection()` | `validator.py` |
| 3.2 | Reemplazar thesis cruda en validator_input | `validator.py` |
| 3.3 | Loguear len(compact_json) con warning | `validator.py` |

### Prioridad 4: Connection pool

| # | Acción | Archivo |
|---|---|---|
| 4.1 | urllib3 PoolManager con keep-alive | `validator.py` |

### Prioridad 5: Logging trazabilidad semántica

| # | Acción | Archivo |
|---|---|---|
| 5.1 | Tabla smc_validator_traces | `runtime_db.py` |
| 5.2 | Función log_validator_trace() | `runtime_db.py` o `validator.py` |
| 5.3 | Invocar desde call_smc_validator | `validator.py` |
| 5.4 | Definir HEURISTIC_VERSION | `heuristic_analyst.py` |

### Prioridad 6: Política presupuesto dinámico

| # | Acción | Archivo |
|---|---|---|
| 6.1 | Agregar SMC_LLM_OUTPUT_BUDGET a SmcAnalystConfig | `heuristic_analyst.py` |
| 6.2 | Warning si completion_tokens > 80% budget | `validator.py` |
| 6.3 | Warning si input_chars > threshold | `validator.py` |

---

## 8. Riesgos y trade-offs

| Riesgo | Mitigación |
|---|---|
| Reducir demasiado contexto | Loguear decisiones antes/después de proyección |
| Registrar ruido inusable | Solo traces con `used_llm=True`; outcome_label para filtrar |
| Sobreingenierizar LoRA sin dataset | Solo logging ahora; infra de training cuando ≥500 trazas |
| Más contexto no siempre mejora | Una sola proyección; medir; parametrizar si hay evidencia |
| Menos tokens no siempre es mejor | No quitar watch_conditions/invalidations (clave para coherencia) |
| Hardcodear presupuestos | Todo configurable vía .env; código solo tiene default de emergencia |
