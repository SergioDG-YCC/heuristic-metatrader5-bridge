# Propuesta concreta de cambios — SMC LLM Pipeline

**Fecha**: 2026-04-02
**Precede a**: `2026-04-02_smc_llm_pipeline_audit.md` + `2026-04-02_smc_llm_revised_plan.md`
**Estado**: PROPUESTA — No implementar sin revisión manual

---

## Matriz de archivos a tocar

| Archivo | Funciones candidatas | Tipo de cambio | Categoría |
|---|---|---|---|
| `src/heuristic_mt5_bridge/smc_desk/llm/validator.py` | `_load_prompt`, `_call_localai_sync`, `call_smc_validator` (nuevo: `_build_validator_projection`) | Quick win + proyección + logging + connection pool | Core |
| `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py` | `SmcAnalystConfig`, `SmcAnalystConfig.from_env`, `run_smc_heuristic_analyst` | Quick win + config + versioning | Config/wiring |
| `src/heuristic_mt5_bridge/infra/storage/runtime_db.py` | `ensure_runtime_db` (nuevo: tabla, nuevo: `log_validator_trace`) | Tabla + función | Habilitante LoRA |
| `.env` | N/A | Ajustar valores, agregar nuevas vars | Config |

---

## Cambio 1 — Conectar config completo al validator [QUICK WIN]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`
### Función: `run_smc_heuristic_analyst` (líneas ~775-785)
### Categoría: Quick win — cierra bug H1, H4

**Cambio exacto — ANTES:**

```python
        validator_step = await call_smc_validator(
            symbol=symbol,
            current_price=float(current_price or 0.0),
            trigger_reason=trigger_reason,
            heuristic_thesis=normalized_thesis,
            validation_summary=validation_summary,
            config={
                "llm_model": config.llm_model,
                "llm_timeout_seconds": config.llm_timeout_seconds,
            },
        )
```

**Cambio exacto — DESPUÉS:**

```python
        validator_step = await call_smc_validator(
            symbol=symbol,
            current_price=float(current_price or 0.0),
            trigger_reason=trigger_reason,
            heuristic_thesis=normalized_thesis,
            validation_summary=validation_summary,
            config={
                "llm_model": config.llm_model,
                "llm_timeout_seconds": config.llm_timeout_seconds,
                "max_tokens": config.llm_max_tokens,
                "temperature": config.llm_temperature,
                "localai_base_url": os.getenv("LOCALAI_BASE_URL", "http://127.0.0.1:8080"),
            },
        )
```

**Riesgo**: Nulo. Solo conecta valores que ya existen en `SmcAnalystConfig`.
**Impacto**: Cierra H1 (max_tokens ahora controlable desde .env) y H4 (temperature configurable).
**Validación manual necesaria**: NO — es un wiring fix directo.

---

## Cambio 2 — Usar temperature del config en HTTP [QUICK WIN]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Función: `_call_localai_sync` (línea ~158)

**Cambio exacto — ANTES:**

```python
def _call_localai_sync(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    localai_base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
```

**Cambio exacto — DESPUÉS:**

```python
def _call_localai_sync(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    localai_base_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
```

**Cambio coordinado** en `call_smc_validator` (línea ~225):

```python
# ANTES:
    max_tokens = int(config.get("max_tokens", 500))

# DESPUÉS (agregar línea):
    max_tokens = int(config.get("max_tokens", 500))
    temperature = float(config.get("temperature", 0.1))
```

Y en la invocación de `_call_localai_sync` (dentro del `asyncio.to_thread`):

```python
# ANTES:
        raw = await asyncio.to_thread(
            _call_localai_sync,
            messages,
            model=model,
            max_tokens=max_tokens,
            localai_base_url=localai_base_url,
            timeout_seconds=timeout,
        )

# DESPUÉS:
        raw = await asyncio.to_thread(
            _call_localai_sync,
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            localai_base_url=localai_base_url,
            timeout_seconds=timeout,
        )
```

**Riesgo**: Nulo.
**Validación manual necesaria**: NO.

---

## Cambio 3 — Cache de prompts + prompt_version hash [QUICK WIN]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Función: `_load_prompt` (líneas ~36-40)

**Cambio exacto — ANTES:**

```python
# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def _load_prompt(name: str, *, compact_json: str = "") -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    if compact_json:
        text = text.replace("{{compact_json}}", compact_json)
    return text
```

**Cambio exacto — DESPUÉS:**

```python
# ---------------------------------------------------------------------------
# Prompt loading + versioning
# ---------------------------------------------------------------------------

_PROMPT_CACHE: dict[str, str] = {}
_PROMPT_VERSION: str = ""


def _ensure_prompt_cache() -> None:
    """Load and cache prompts on first use. Compute prompt_version hash."""
    global _PROMPT_VERSION
    if _PROMPT_CACHE:
        return
    import hashlib
    hasher = hashlib.sha1()
    for name in ("system", "user"):
        path = _PROMPTS_DIR / f"{name}.md"
        content = path.read_text(encoding="utf-8")
        _PROMPT_CACHE[name] = content
        hasher.update(content.encode("utf-8"))
    _PROMPT_VERSION = hasher.hexdigest()[:12]


def _load_prompt(name: str, *, compact_json: str = "") -> str:
    _ensure_prompt_cache()
    text = _PROMPT_CACHE[name]
    if compact_json:
        text = text.replace("{{compact_json}}", compact_json)
    return text


def get_prompt_version() -> str:
    """Return short hash of loaded prompts (for trace logging)."""
    _ensure_prompt_cache()
    return _PROMPT_VERSION
```

**Riesgo**: Nulo. Prompts se leen una vez y se cachean. El hash se usa para trazabilidad.
**Impacto**: H5 cerrado. `prompt_version` disponible para logging de trazabilidad (habilitante LoRA).
**Validación manual necesaria**: NO.

---

## Cambio 4 — Logging operativo: elapsed + usage + print estructurado [QUICK WIN]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Funciones: `_call_localai_sync` (devolver usage) + `call_smc_validator` (timing)

### 4a. `_call_localai_sync` — devolver usage junto con el JSON

**Cambio exacto:** La función hoy retorna `dict[str, Any]` (el JSON extraído). Cambiar para devolver una tupla `(extracted_json, usage_dict)`.

**ANTES (final de `_call_localai_sync`):**

```python
    result = json.loads(body)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices missing in LocalAI response")

    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty validator content from LocalAI")

    return _extract_json(content)
```

**DESPUÉS:**

```python
    result = json.loads(body)
    usage = result.get("usage") or {}
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("choices missing in LocalAI response")

    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty validator content from LocalAI")

    return _extract_json(content), content, usage
```

**Nota**: El tipo de retorno cambia a `tuple[dict[str, Any], str, dict[str, Any]]` — (parsed JSON, raw response text, usage dict).
El `raw response text` (content) se preserva porque será necesario para el logging de trazabilidad semántica (capa B, habilitante LoRA).

### 4b. `call_smc_validator` — timing + log

**ANTES (dentro del try):**

```python
    try:
        raw = await asyncio.to_thread(
            _call_localai_sync,
            messages,
            model=model,
            max_tokens=max_tokens,
            localai_base_url=localai_base_url,
            timeout_seconds=timeout,
        )
        normalized = _normalize_validator_output(raw)
        validated = _apply_validator_result(dict(heuristic_thesis), normalized)
        return {
            "used_llm": True,
            "validator_result": normalized,
            "validated_thesis": validated,
        }
```

**DESPUÉS:**

```python
    input_chars = len(compact_json)
    try:
        import time as _time
        t0 = _time.monotonic()
        raw, raw_content, usage = await asyncio.to_thread(
            _call_localai_sync,
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            localai_base_url=localai_base_url,
            timeout_seconds=timeout,
        )
        elapsed = _time.monotonic() - t0

        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        print(
            f"[smc-validator] {symbol} model={model} "
            f"elapsed={elapsed:.1f}s prompt_tok={prompt_tokens} "
            f"compl_tok={completion_tokens} input_chars={input_chars} "
            f"budget={max_tokens}"
        )
        if max_tokens > 0 and completion_tokens > int(max_tokens * 0.8):
            print(f"[smc-validator] WARNING {symbol}: completion_tokens={completion_tokens} near budget={max_tokens}")

        normalized = _normalize_validator_output(raw)
        validated = _apply_validator_result(dict(heuristic_thesis), normalized)
        return {
            "used_llm": True,
            "validator_result": normalized,
            "validated_thesis": validated,
        }
```

**Riesgo**: Nulo. Solo agrega información, no modifica flujo.
**Impacto**: Cierra H6. Visibilidad inmediata de latencia, tokens, presupuesto.
**Validación manual necesaria**: NO.

---

## Cambio 5 — Ajustar `.env` [QUICK WIN]

### Archivo: `.env`

**ANTES (líneas ~54-56):**

```env
SMC_LLM_TIMEOUT_SECONDS=120
SMC_LLM_MAX_TOKENS=8192
SMC_LLM_TEMPERATURE=0.1
```

**DESPUÉS:**

```env
SMC_LLM_TIMEOUT_SECONDS=120
SMC_LLM_MAX_TOKENS=500
SMC_LLM_TEMPERATURE=0.1
# SMC_LLM_INPUT_CHARS_WARNING=4000
```

**Nota**: `SMC_LLM_MAX_TOKENS=500` es un safety ceiling razonable para el output contract actual (~5 campos JSON). No es un hardcode de optimización — es el safety ceiling configurable que antes estaba desconectado. Si el output contract cambia, se ajusta aquí.

**Riesgo**: Nulo (baja de 8192 que nunca se usaba a 500 que es lo que ya se aplicaba por fallback).
**Validación manual necesaria**: NO.

---

## Cambio 6 — Proyección semántica del input [REQUIERE VALIDACIÓN]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Función nueva: `_build_validator_projection`
### Función modificada: `call_smc_validator` (líneas ~240-247)

### 6a. Nueva función `_build_validator_projection`

**Ubicación**: después de `_normalize_validator_output`, antes de `_apply_validator_result`.

```python
def _build_validator_projection(
    heuristic_thesis: dict[str, Any],
    validation_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a semantic projection of the thesis for LLM validation.

    Preserves fields with semantic value for coherence validation.
    Excludes purely operational/traceability fields.
    """
    candidates = heuristic_thesis.get("operation_candidates", [])
    compact_candidates = []
    for c in candidates[:5]:
        if not isinstance(c, dict):
            continue
        compact_candidates.append({
            "side": c.get("side"),
            "rr_ratio": c.get("rr_ratio"),
            "confluences": c.get("confluences", []),
            "entry_model": c.get("entry_model"),
            "quality": c.get("quality"),
            "trigger_type": c.get("trigger_type"),
        })

    mtf = heuristic_thesis.get("multi_timeframe_alignment")
    if isinstance(mtf, dict):
        mtf_compact = {
            "d1_structure": mtf.get("d1_structure"),
            "h4_structure": mtf.get("h4_structure"),
            "h1_structure": mtf.get("h1_structure"),
            "aligned": mtf.get("aligned"),
            "conflict_note": mtf.get("conflict_note"),
        }
    else:
        mtf_compact = None

    elliott = heuristic_thesis.get("elliott_count")
    if isinstance(elliott, dict):
        elliott_compact = {
            "pattern_type": elliott.get("pattern_type"),
            "current_wave": elliott.get("current_wave"),
            "confidence": elliott.get("confidence"),
        }
    else:
        elliott_compact = None

    return {
        "bias": heuristic_thesis.get("bias"),
        "bias_confidence": heuristic_thesis.get("bias_confidence"),
        "status": heuristic_thesis.get("status"),
        "multi_timeframe_alignment": mtf_compact,
        "watch_conditions": heuristic_thesis.get("watch_conditions", []),
        "invalidations": heuristic_thesis.get("invalidations", []),
        "operation_candidates": compact_candidates,
        "elliott_count": elliott_compact,
        "validation_summary": validation_summary,
    }
```

### 6b. Modificar `call_smc_validator` para usar proyección

**ANTES (líneas ~240-247):**

```python
    validator_input = {
        "symbol": str(symbol).upper(),
        "current_price": float(current_price),
        "trigger_reason": str(trigger_reason),
        "heuristic_thesis": heuristic_thesis,
        "validation_summary": validation_summary,
    }
    compact_json = json.dumps(validator_input, ensure_ascii=True, separators=(",", ":"))
```

**DESPUÉS:**

```python
    projection = _build_validator_projection(heuristic_thesis, validation_summary)
    validator_input = {
        "symbol": str(symbol).upper(),
        "current_price": float(current_price),
        "trigger_reason": str(trigger_reason),
        "thesis": projection,
    }
    compact_json = json.dumps(validator_input, ensure_ascii=True, separators=(",", ":"))
```

**Riesgo**: MEDIO. El modelo podría comportarse diferente con menos contexto.
**Impacto**: Reducción de ~50-80% de tokens de prefill → reducción proporcional de latencia de prefill.
**Validación manual necesaria**: SÍ.
- Comparar decisiones del validator con y sin proyección usando los logs de Cambio 4.
- Correr al menos 10-20 ciclos de análisis con logging antes y después.
- Verificar que la tasa de reject/adjust no cambia de forma anómala.

---

## Cambio 7 — Connection pool con urllib3 [BAJO RIESGO]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Función: `_call_localai_sync`

**ANTES (imports + función):**

```python
import urllib.error
import urllib.request
```

```python
    request = urllib.request.Request(
        url=f"{localai_base_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LocalAI HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LocalAI connection failed: {exc.reason}") from exc
```

**DESPUÉS:**

```python
import urllib3
```

(module-level pool):

```python
_HTTP_POOL: urllib3.PoolManager | None = None


def _get_http_pool() -> urllib3.PoolManager:
    global _HTTP_POOL
    if _HTTP_POOL is None:
        _HTTP_POOL = urllib3.PoolManager(num_pools=1, maxsize=2, retries=False)
    return _HTTP_POOL
```

(dentro de `_call_localai_sync`, reemplazar el bloque urllib.request):

```python
    pool = _get_http_pool()
    try:
        resp = pool.request(
            "POST",
            f"{localai_base_url}/v1/chat/completions",
            body=data,
            headers={"Content-Type": "application/json"},
            timeout=urllib3.Timeout(total=timeout_seconds),
        )
        if resp.status >= 400:
            raise RuntimeError(f"LocalAI HTTP {resp.status}: {resp.data[:200]}")
        body = resp.data.decode("utf-8")
    except urllib3.exceptions.MaxRetryError as exc:
        raise RuntimeError(f"LocalAI connection failed: {exc}") from exc
    except urllib3.exceptions.TimeoutError as exc:
        raise RuntimeError(f"LocalAI timeout after {timeout_seconds}s") from exc
```

**Riesgo**: Bajo. Verificar que `urllib3` está disponible en el entorno.
**Prerequisito**: Verificar `pip list | Select-String urllib3` — probablmente ya está como dep transitiva. Si no, agregar a `pyproject.toml`.
**Impacto**: -50-200ms por llamada (TCP keep-alive en Docker Desktop).
**Validación manual necesaria**: SÍ — verificar que urllib3 está disponible y que el pool funciona con LocalAI.

---

## Cambio 8 — Tabla `smc_validator_traces` [HABILITANTE LoRA]

### Archivo: `src/heuristic_mt5_bridge/infra/storage/runtime_db.py`
### Función: `ensure_runtime_db` (insertar después del bloque `smc_events_log`, antes de `# -- Fast desk`)

**Ubicación exacta**: línea ~387, justo antes de `# ------------------------------------------------------------------ Fast desk`

**Código nuevo a insertar:**

```python
        # ------------------------------------------------- SMC validator traces
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS smc_validator_traces (
                trace_id TEXT PRIMARY KEY,
                broker_server TEXT NOT NULL,
                account_login INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                trigger_reason TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                heuristic_rules_version TEXT NOT NULL DEFAULT 'unknown',
                validator_projection_json TEXT NOT NULL,
                validation_summary_json TEXT NOT NULL,
                llm_raw_response TEXT,
                llm_normalized_result_json TEXT NOT NULL,
                heuristic_decision_pre TEXT NOT NULL,
                final_decision TEXT NOT NULL,
                elapsed_seconds REAL NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                input_chars INTEGER,
                outcome_label TEXT,
                outcome_updated_at TEXT,
                outcome_source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_vt_symbol ON smc_validator_traces(broker_server, account_login, symbol, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_vt_model ON smc_validator_traces(model, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smc_vt_outcome ON smc_validator_traces(outcome_label) WHERE outcome_label IS NOT NULL"
        )
```

### Función nueva: `log_validator_trace`

**Ubicación**: después de las funciones existentes de smc (e.g., después de `log_smc_event`).

```python
def log_validator_trace(db_path: Path, *, trace: dict[str, Any]) -> None:
    """Append a validator trace for future dataset curation."""
    with runtime_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO smc_validator_traces (
                trace_id, broker_server, account_login, symbol,
                trigger_reason, model, prompt_version, heuristic_rules_version,
                validator_projection_json, validation_summary_json,
                llm_raw_response, llm_normalized_result_json,
                heuristic_decision_pre, final_decision,
                elapsed_seconds, prompt_tokens, completion_tokens, input_chars,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(trace["trace_id"]),
                str(trace["broker_server"]),
                int(trace["account_login"]),
                str(trace["symbol"]),
                str(trace["trigger_reason"]),
                str(trace["model"]),
                str(trace["prompt_version"]),
                str(trace.get("heuristic_rules_version", "unknown")),
                json_text(trace["validator_projection"]),
                json_text(trace["validation_summary"]),
                str(trace.get("llm_raw_response") or ""),
                json_text(trace["llm_normalized_result"]),
                str(trace["heuristic_decision_pre"]),
                str(trace["final_decision"]),
                float(trace["elapsed_seconds"]),
                trace.get("prompt_tokens"),
                trace.get("completion_tokens"),
                trace.get("input_chars"),
                trace["created_at"],
            ),
        )
        conn.commit()
```

**Riesgo**: Nulo. Solo escritura append-only, no modifica flujo existente.
**Impacto**: Habilita recolección de datos para futura curación de dataset LoRA/QLoRA.
**Validación manual necesaria**: NO — pero requiere verificar que `json_text` y `runtime_db_connection` ya están definidas (sí lo están en el archivo actual).

---

## Cambio 9 — Versión heurística [HABILITANTE LoRA]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/analyst/heuristic_analyst.py`
### Ubicación: después de los imports, antes de `_utc_now_iso`

**Código nuevo a insertar:**

```python
# Bump when heuristic logic changes materially (bias derivation, scoring, candidate gates).
HEURISTIC_VERSION = "2026.04"
```

**Riesgo**: Nulo. Constante pasiva.
**Validación manual necesaria**: NO — pero requiere disciplina de bump al cambiar lógica heurística.

---

## Cambio 10 — Invocar trace logging desde validator [HABILITANTE LoRA]

### Archivo: `src/heuristic_mt5_bridge/smc_desk/llm/validator.py`
### Función: `call_smc_validator`

Este cambio depende de: Cambio 4 (timing/usage), Cambio 6 (proyección), Cambio 8 (tabla/función).

**Insertar después del bloque de logging operativo (print), antes del return:**

```python
        # --- Trace logging for future dataset curation ---
        try:
            import uuid
            from heuristic_mt5_bridge.infra.storage.runtime_db import log_validator_trace
            log_validator_trace(
                config.get("db_path") or _DEFAULT_DB_PATH,  # needs db_path in config
                trace={
                    "trace_id": f"vt_{uuid.uuid4().hex}",
                    "broker_server": config.get("broker_server", ""),
                    "account_login": config.get("account_login", 0),
                    "symbol": symbol,
                    "trigger_reason": trigger_reason,
                    "model": model,
                    "prompt_version": get_prompt_version(),
                    "heuristic_rules_version": config.get("heuristic_rules_version", "unknown"),
                    "validator_projection": projection,  # from Cambio 6
                    "validation_summary": validation_summary,
                    "llm_raw_response": raw_content,  # from Cambio 4a
                    "llm_normalized_result": normalized,
                    "heuristic_decision_pre": str(heuristic_thesis.get("status", "")),
                    "final_decision": normalized.get("decision", "accept"),
                    "elapsed_seconds": elapsed,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "input_chars": input_chars,
                    "created_at": _utc_now_iso(),
                },
            )
        except Exception as exc:
            print(f"[smc-validator] trace logging failed: {exc}")
```

**Nota**: Requiere que `call_smc_validator` reciba `db_path`, `broker_server`, `account_login` en el dict de config. Esto implica un cambio adicional coordinado en `run_smc_heuristic_analyst` (agregar esas claves al dict de config que se pasa).

**Helper necesario** en validator.py:

```python
def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
```

**Riesgo**: Bajo. Está envuelto en try/except; si falla el trace, no afecta el flujo principal.
**Validación manual necesaria**: SÍ — verificar que db_path llega correctamente al validator.

---

## Resumen de clasificación

### Quick wins (Cambios 1-5) — implementar sin revisión adicional

| # | Qué | Cierra hallazgo |
|---|---|---|
| 1 | Conectar config completo | H1, H4 |
| 2 | Temperature del config en HTTP | H4 |
| 3 | Cache prompts + prompt_version | H5, prep LoRA |
| 4 | Logging operativo (elapsed + usage) | H6 |
| 5 | Ajustar .env | H1 safety |

### Prepara camino LoRA/QLoRA (Cambios 8, 9, 10)

| # | Qué | Para qué |
|---|---|---|
| 8 | Tabla smc_validator_traces | Almacenar pares input/output etiquetables |
| 9 | HEURISTIC_VERSION | Vincular trazas a versión de reglas |
| 10 | Invocar trace logging | Escribir trazas desde el validator |

### Requiere validación manual antes de implementar (Cambios 6, 7)

| # | Qué | Por qué |
|---|---|---|
| 6 | Proyección semántica | Puede cambiar comportamiento del modelo; requiere comparar antes/después con logs |
| 7 | Connection pool urllib3 | Requiere verificar disponibilidad de urllib3 en el entorno |

---

## Orden de implementación recomendado

```
Fase 1 (Quick wins, sin dependencias):
    Cambio 5 (.env)
    Cambio 1 (config wiring)
    Cambio 2 (temperature)
    Cambio 3 (prompt cache + hash)

Fase 2 (Logging operativo, depende de 1+2):
    Cambio 4 (timing + usage + print)

Fase 3 (Infraestructura LoRA, sin dependencia del flujo):
    Cambio 8 (tabla SQLite)
    Cambio 9 (HEURISTIC_VERSION)

Fase 4 (Validación requerida, depende de Fases 1-3):
    Cambio 7 (urllib3 pool)
    Cambio 6 (proyección semántica)
    Cambio 10 (trace logging — depende de 4+6+8+9)
```

---

## Archivos que NO se tocan

| Archivo | Por qué no |
|---|---|
| `smc_desk/runtime.py` | Orquestación está bien; no hay cambios |
| `smc_desk/scanner/scanner.py` | No involucra LLM |
| `smc_desk/validators/heuristic.py` | Hard validators están bien |
| `smc_desk/state/thesis_store.py` | Persistencia está bien |
| `smc_desk/detection/*` | Detección heurística no cambia |
| `smc_desk/prompts/system.md` | System prompt es correcto (cambio futuro opcional: eliminar/opcionalizar `summary`) |
| `smc_desk/prompts/user.md` | Template está bien |
