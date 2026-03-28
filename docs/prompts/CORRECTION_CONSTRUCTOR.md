# PROMPT: Constructor de Corrección Arquitectónica
**Repo:** `heuristic-metatrader5-bridge`
**Fecha:** 2026-03-23
**Modelo recomendado:** `gpt-5.3-codex` o equivalente de implementación

---

## Rol

Eres un ingeniero de software implementando correcciones sobre una repo existente.

**No es una reescritura desde cero.**

La repo ya tiene infraestructura funcional correcta:
- `SubscriptionManager` — universos catalog/bootstrap/subscribed — correcto
- `ConnectorIngress` — owner único del MT5 API — correcto
- `ChartRegistry` + `ChartWorker` — chart state en RAM — correcto
- `MarketStateService` — deque de velas en RAM — correcto

Tu trabajo es corregir lo que está mal, sin tocar lo que está bien.

---

## Documentos canónicos de referencia

Lee estos documentos en orden antes de proceder:

1. `docs/ARCHITECTURE.md`
2. `docs/plans/2026-03-23_mt5_data_ownership_boundary.md`
3. `docs/plans/2026-03-23_chart_ram_runtime_architecture.md`
4. `docs/plans/2026-03-23_core_runtime_subscription_refactor_plan.md`
5. `docs/plans/2026-03-23_correction_action_plan.md`
6. `docs/audit/2026-03-23_full_audit.md`

El documento `docs/plans/2026-03-23_correction_action_plan.md` es el plan de trabajo que debes seguir paso a paso.

---

## Reglas absolutas — MUST / MUST NOT

### MUST NOT (prohibiciones sin excepción)

1. **MUST NOT** escribir ningún archivo JSON al disco durante operación del runtime. No existe `core_runtime.json`. No existe ningún archivo `live/*.json`. Si necesitas diagnostics externos, eso es trabajo del Control Plane HTTP.

2. **MUST NOT** escribir snapshots de indicadores al disco local. `storage/indicator_snapshots/` no debe existir como destino de escritura. Los indicadores se aplican directamente al `MarketStateService` en RAM.

3. **MUST NOT** incluir `bid`, `ask`, `last_price`, `tick_age_seconds`, `bar_age_seconds`, `feed_status` como columnas en ninguna tabla SQLite. Estos son datos dinámicos de feed, no datos operativos de recuperación.

4. **MUST NOT** usar heurísticas hardcodeadas para `pip_size`, `point` o cualquier especificación de símbolo. Toda especificación de símbolo debe provenir del `SymbolSpecRegistry` que se carga desde el conector MT5 en startup.

5. **MUST NOT** leer `core_runtime.json` desde ningún componente (no debe existir).

6. **MUST NOT** crear un loop periódico de "live publish" que escriba al disco. `CORE_LIVE_PUBLISH_SECONDS` no existe.

7. **MUST NOT** tener tablas SQLite con `symbol` como única clave primaria si los datos son broker-dependientes. Toda tabla con datos de símbolo debe incluir `broker_server` + `account_login` en la clave primaria.

8. **MUST NOT** que un proceso externo (WebUI, Fast Desk, SMC Desk) lea estado de mercado desde disco. Solo RAM via Control Plane HTTP o in-process reference.

### MUST (requisitos sin excepción)

1. **MUST** exponer el estado del runtime exclusivamente via HTTP desde el Control Plane. El endpoint raíz es `/status`.

2. **MUST** normalizar todas las timestamps internas a UTC0 antes de almacenarlas en RAM o SQLite. El `server_time_offset_seconds` se usa solo para normalizar, nunca se propaga como dato.

3. **MUST** particionar por `(broker_server, account_login)` toda tabla SQLite que contenga datos de símbolo, cuenta o mercado.

4. **MUST** purgar datos de broker anterior en SQLite cuando `broker_identity` cambia respecto a la última ejecución.

5. **MUST** que el Control Plane se exponga en `host = CONTROL_PLANE_HOST` (defecto `0.0.0.0`) y `port = CONTROL_PLANE_PORT` (defecto `8765`).

6. **MUST** que la WebUI (si se implementa) sea un frontend separado que consume el Control Plane via HTTP/SSE. Puede ser Node.js, Vite, o cualquier framework web moderno.

---

## Alcance de esta sesión de implementación

Implementa exactamente las fases y pasos especificados en `docs/plans/2026-03-23_correction_action_plan.md`.

**Fase por defecto si no se especifica otra:** comenzar por Fase 0 (documentación) + Fase 1 (purga) + Fase 2 (schema SQLite).

Si el operador especifica una fase concreta, implementa solo esa fase.

---

## Restricciones de implementación

### No añadir lo que no se pide

- No añadir docstrings donde no los hay
- No añadir logging donde no existe
- No añadir type hints a código que no se está modificando
- No generalizar ni crear abstracciones para casos hipotéticos
- No añadir dependencias externas no presentes en `pyproject.toml` sin aprobación explícita

### Conservar lo que está bien

Estos módulos NO deben modificarse a menos que su fase lo indique explícitamente:
- `src/heuristic_mt5_bridge/core/runtime/subscriptions.py`
- `src/heuristic_mt5_bridge/core/runtime/chart_registry.py`
- `src/heuristic_mt5_bridge/core/runtime/chart_worker.py`
- `src/heuristic_mt5_bridge/core/runtime/ingress.py`
- `src/heuristic_mt5_bridge/infra/sessions/service.py`
- `src/heuristic_mt5_bridge/infra/sessions/registry.py`

### Archivos a eliminar (Fase 1)

Elimina estos archivos físicamente durante Fase 1:
```
storage/live/core_runtime.json
storage/indicator_snapshots/indreq_*.json   (todos)
storage/runtime.db
```

Y estas carpetas (si quedan vacías tras la purga):
```
storage/live/
```

---

## Verificación tras cada paso

Después de cada paso de implementación, ejecuta:

```bash
cd e:\GITLAB\Sergio_Privado\heuristic-metatrader5-bridge
python -m pytest tests/ -x -q
```

Si los tests pasan, continúa al siguiente paso.
Si fallan, corrige antes de avanzar.

Después de Fase 1 completa, verifica adicionalmente:

```bash
python apps/core_runtime.py --dry-run-config
```

El comando debe completar sin errores y **sin crear ningún archivo JSON** en `storage/`.

---

## Cómo reportar cuando termines

Al finalizar cada fase, reporta:

1. Lista de archivos modificados con descripción de un párrafo de qué cambió y por qué
2. Lista de archivos eliminados
3. Resultado de los tests
4. Si hay deuda técnica que no se pudo resolver en la fase, listada explícitamente con su hallazgo de auditoría de referencia (Fxx)

---

## Contexto del sistema objetivo

- Python 3.12+
- MetaTrader5 Python connector (solo disponible en Windows)
- El conector MT5 es síncrono; se envuelve en `asyncio.to_thread()`
- El runtime corre como proceso asyncio (`asyncio.run()`)
- SQLite con WAL mode para persistencia operativa
- FastAPI + uvicorn para Control Plane HTTP
- El frontend puede ser cualquier tecnología web moderna
- El sistema está diseñado para correr N instancias en paralelo (una por broker/terminal MT5)
- Escala desde polling por segundos hasta nivel tick
- Se ejecuta en Windows (mismo host que MetaTrader5)
