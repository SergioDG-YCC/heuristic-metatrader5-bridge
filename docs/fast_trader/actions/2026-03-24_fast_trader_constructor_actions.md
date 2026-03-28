# Fast Trader Constructor Actions

Fecha: 2026-03-24

## Secuencia inmediata obligatoria

1. Auditar el `fast_desk` actual y confirmar qué piezas se preservan.
2. Habilitar `M1` para Fast sin romper el runtime actual.
3. Introducir `FastTraderService` separado del scanner simple actual.
4. Extraer o adaptar heurísticas necesarias para:
   - order block retest
   - liquidity sweep + reclaim
   - breakout + retest
5. Agregar gates:
   - session
   - spread
   - slippage
6. Reforzar custody:
   - BE
   - ATR trailing
   - structural trailing
   - hard cut
   - no passive underwater
7. Integrar Fast con `OwnershipRegistry` y `RiskKernel` como autoridades.
8. Validar con tests y regresión del conector.

## Checklist técnico

- [ ] `M1` disponible en runtime
- [ ] context service Fast
- [ ] setup engine Fast
- [ ] trigger engine Fast
- [ ] pending order policy Fast
- [ ] custody engine profesional
- [ ] ownership integration
- [ ] risk integration
- [ ] DB audit trail suficiente
- [ ] tests unitarios
- [ ] tests integración
- [ ] regresión conector verde

## Atajos prohibidos

- usar LLM en Fast
- llamar scanners SMC pesados dentro del hot path
- copiar `live_execution_trader_runtime.py` entero
- meter toda la lógica en `symbol_worker.py`
- abrir operaciones sólo por EMA cross
- trailing “mágico” sin política explícita

## Señales de que el constructor se está desviando

- empieza a tocar `SmcTraderService`
- mete `paper mode`
- cambia `BridgeSupervisor`
- intenta rediseñar `RiskKernel`
- agrega runtime lento o colas innecesarias
- usa docs viejos como justificación para copiar código sin adaptación

## Cierre esperado del constructor

Debe entregar:

- código
- tests
- documentación mínima de Fast
- lista explícita de gaps dejados para la siguiente fase
