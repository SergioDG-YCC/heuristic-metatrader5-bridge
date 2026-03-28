# Guía para Traders — Heuristic MT5 Bridge

> **Status**: Laboratorio en desarrollo — marzo 2026  
> Este documento explica el sistema de forma clara y práctica para traders de todos los niveles.

---

## El concepto central

Tenemos **un laboratorio de trading asistido** que conecta MetaTrader 5 con un motor heurístico en Python. 

La idea no es "un bot que decide todo". La idea es:
- **Control profesional**: un solo dueño de la conexión MT5, serialización correcta
- **Dos mesas separadas** con lógica diferente, que comparten el mismo motor central
- **Riesgo centralizado**: un solo árbitro de riesgo para toda la cuenta
- **Observabilidad total**: una interfaz web para monitorear y operar en vivo

---

## Las dos mesas: rápida vs lenta

### Mesa Fast: decisiones rápidas

**Perfil**: operación táctica milisegundos, sin IA en el camino crítico.

**Cómo funciona**:
1. **Contexto** — ¿es buen momento para tradear hoy? Se pregunta: ¿sesión abierta? ¿spread normal? ¿feed en vivo?
2. **Setup** — ¿hay un patrón validado en M5? Busca estructuras de mercado (rupturas, retests, barridos de liquidez)
3. **Trigger** — ¿confirmación en M1? Exige un pulso fino en la vela más cercana antes de ejecutar
4. **Ejecución** — ¿pasa el riesgo? Si la casa lo permite, abre la posición
5. **Custodia** — ¿cómo protegemos las ganancias? Break-even, trailing, corte por slippage

**Velocidad**: segundos, máximo. Si toma más, es tarde.

**Riesgo**: automático. Una máquina, sin emociones, sin espera a validación humana.

---

### Mesa SMC: tesis preparadas

**Perfil**: análisis más profundo, zonas estructurales, cierre de confluencias, opcionalmente con validación IA.

**Cómo funciona**:

1. **Detección heurística** — El sistema analiza M5/H1/D1 buscando patrones SMC puros:
   - **Estructura de mercado**: dónde rompió el precio la estructura previa (BOS), dónde invirtió (CHoCH)
   - **Order Blocks**: zonas donde acción institucional dejó huella, potencial rechazo futuro
   - **Gaps de valor justo (FVG)**: espacios entre velas, riesgo de llenarse, potencial mitigación
   - **Barridos de liquidez**: dónde pinchan stops, confirmación de intención institucional
   - **Fibonacci y Elliott**: ratios de retracción y extensión de la estructura
   - **Confluencias**: cuantos señales coinciden en la misma zona

2. **Análisis heurístico fino** — Un validador determinístico revisa:
   - ¿Cuántas confluencias tiene esta zona? (mínimo 2 para pasar)
   - ¿Está orientada con el contexto macroeconómico (D1)? 
   - ¿El stop loss es viable según volatilidad actual?
   - ¿Tiene relación con barridos de liquidez previos?

3. **Validación con IA (opcional)** — Si está habilitada:
   - Gemma 3 (12B local) revisa la tesis preparada por heurística
   - **No inventa el setup desde cero** — solo valida/refina lo que heurística armó
   - Si IA rechaza, la tesis no avanza
   - Si IA valida, la tesis queda lista

4. **Almacenamiento de tesis** — La tesis validada queda grabada:
   - Contexto de la zona
   - Contexto macro
   - Invalidación (qué precio cierra esta idea)
   - Espera: todo está listo, pero no ejecuta automáticamente

5. **Ejecución manual o futura** — El trader (vos) o un executor futuro:
   - Revisa la tesis en la interfaz
   - Ve la zona en el chart, los niveles, las invalidaciones
   - Puede ejecutar *ahora* con un click si el momento es correcto
   - O esperar a que el precio llegue exacto a la zona de entrada

**Velocidad**: minutos a horas. Tiempo para pensar.

**Riesgo**: visible, alineado con estructura, con confluencias reales. No es random.

---

## El motor central: qué sucede bajo el capó

### Conexión MT5: una sola puerta de entrada

MetaTrader 5 es la fuente de verdad. Todo lo que el sistema sabe, lo sabe porque MT5 le dijo.

```
MetaTrader 5 (broker, posiciones, órdenes)
    ↓
MT5Connector (una sola conexión, serializada)
    ↓
ChartRegistry (guarda velas en memoria por símbolo)
    ↓
MarketStateService (estado del mercado: precios, spreads, feeds)
    ↓
CoreRuntimeService (orquestador central)
    ↓
Mesa Fast + Mesa SMC (cada una decide qué hacer)
```

**Por qué "una sola puerta":**
- Sin serialización, dos operaciones simultáneas se pisan
- Sin un solo dueño, no hay autoridad sobre qué órdenes son nuestras
- Sin orden de ejecución, el caos

### Estado vivo en memoria RAM

Las velas (OHLC), el estado de la cuenta, los specs del broker... **todo vive en RAM**, no en disco.

¿Por qué? Porque:
- El precio cambia constantemente, grabar en disco cada tick es ridículo
- La lectura es mucho más rápida desde RAM
- Si el sistema se apaga, recupera del broker

**En disco solo** va lo operativo:
- Posiciones abiertas y cerradas (para auditoría)
- Tesis SMC (para que el trader la revise después)
- Eventos de riesgo (para saber qué pasó)
- Historia de ownership (quién debía cada operación)

---

## Manejo de Riesgo: autoridad centralizada

No hay dos jueces. Hay **uno**: el `RiskKernel`.

Sus responsabilidades:
- **Presupuesto global**: ¿cuánto dinero podemos perder hoy en la cuenta?
- **Perfiles**: riesgo conservador (perfil 1) vs agresivo (perfil 4)
- **Asignación por mesa**: Fast puede gastar X%, SMC puede gastar Y%
- **Validación de cada operación**: ¿esta orden respeta nuestros límites?
- **Kill switch**: si algo anda mal, bloquea nuevas entradas al instante

**Propietario claro de cada operación**:
- `fast_owned`: la mesa Fast abrió esto, la mesa Fast lo cuida
- `smc_owned`: SMC lo preparó, SMC lo administra
- `inherited_fast`: Fast heredó una posición vieja (ej: SMC abrió, Fast la cuida temporalmente)

El riesgo no es difuso. No hay sorpresas.

---

## La interfaz web: Solid.js en vivo

Hay una interfaz web (WebUI) construida en Solid.js que corre en `apps/webui/`. 

**Su propósito**: ver y operar el sistema sin entrar al terminal MT5 ni a la línea de comandos.

### Paneles principales

#### 1. **Overview (inicio)**
El dashboard principal. Te muestra:
- Salud general: ¿el bridge está conectado a MT5?
- Cuenta: balance, equity, drawdown
- Símbolos suscritos: cuales estamos monitoreando
- Posiciones abiertas: resumen rápido

#### 2. **Operaciones (Operations)**
Detalle de todo lo que se mueve:
- Posiciones abiertas: símbolo, lado, si está rentable, dónde está el stop y take profit
- Órdenes pendientes: órdenes que esperan confirmación de precio
- Exposición: cuánto dinero tenemos en riesgo por símbolo

#### 3. **Mesa Fast**
Estado de la mesa rápida:
- Señales detectadas hoy: qué setups encontró
- Ejecuciones: qué entró, a qué precio, cómo salió
- Pipeline: visualización de las 5 etapas (contexto → setup → trigger → ejecución → custodia)
- Active trades: dinero en juego ahora mismo en Fast

#### 4. **Mesa SMC**
Estado de la mesa lenta:
- Zonas detectadas: order blocks, FVGs, barridos, confluencias
- Tesis preparadas: análisis heurísticos listos para operar
- Chart interactivo: ve las zonas dibujadas sobre el gráfico
- Estado de cada zona: ¿activa? ¿mitigada? ¿invalidada?

#### 5. **Riesgo (Risk)**
Control central de límites:
- Perfil activo: conservador, moderado, agresivo, custom
- Límites globales: drawdown máximo permitido hoy
- Asignación por mesa: cuánto puede gastar Fast vs SMC
- Kill switch: botón para bloquear nuevas entradas si algo anda mal

#### 6. **Ownership**
Quién debe qué:
- Operación actual: abierta, owner, status
- Historia: qué pasó con ella, cuándo cambió de manos
- Reasignación: si algo salió mal, puede reasignarse manualmente

Otros paneles:
- **Terminal**: datos crudos del broker (account info, specs por símbolo)
- **Catalogo de símbolos**: qué ofrece el broker, cuáles están subscritos, en qué mesa tradea cada uno
- **Configuración**: ajusta parámetros vivos sin reiniciar

---

## Flujo típico de una operación Fast

```
T+0s    contexto evalúa: ¿hay sesión? ¿spread ok? ¿feed vivo?
        ✓ contexto valida

T+1s    setup busca en M5: ¿hay ruptura? ¿hay retest? ¿hay barrido de liquidez?
        ✓ setup encontrado, setup_confidence = 0.72

T+2s    trigger busca en M1: ¿hay reclamación? ¿hay breakout micro?
        ✓ trigger confirmado, trigger_confidence = 0.75

T+3s    entrada: pasa RiskKernel, pasa entry policy
        ✓ ejecuta: 0.5 lotes a market, SL a X, TP a Y
        
T+4s    custodia comienza
        posición flotante en ganancia
        
T+15s   floating P&L ≥ 2× risk → SL a breakeven + 1 pip
        
T+45s   floating P&L ≥ 3× risk → cierra 50% de la posición
        
T+120s  orden pendiente expirada (TTL), se cancela
        
T+300s  posición cerrada por TP manual o custodia automática
        ✓ operación finalizada
```

---

## Flujo típico de una operación SMC

```
T+0m        scanner corre cada 5 minutos
            busca en D1/H4: estructuras, order blocks, liquidez, confluencias

T+0m:30     zone_detected: OB en EURUSD H4 con 2.8 confluencias
            → grabada en thesis_store

T+0m:45     analyst valida: ¿contexto macro ok? ¿volatilidad viable?
            ✓ tesis lista, esperando

T+5m        IA valida opcionalmente (si está habilitada)
            Gemma 3 revisa: ¿hace sentido esta tesis?
            ✓ IA valida, tesis queda "approved"

T+5m:10     trader (vos) miras el gráfico SMC en la interfaz
            ves la zona marcada, los invalidators, el SL y TP sugeridos
            precio está acercándose...

T+15m       precio toca la zona exacta
            ¿ahora? ✓ click en "ejecutar"
            → orden enviada a MT5

T+16m       Fast desk también ve la zona y la opera si está "fast-enabled"
            ambas mesas pueden coexistir

T+30m       custodia: misma lógica que Fast, pero con más paciencia
            sin trailing agresivo
            focus en preserve profit de largo plazo
```

---

## Arquitectura sin sorpresas

### Control Plane: la API central

Todos los desks, la WebUI, cualquier observador externo hablan con **una sola API HTTP**.

```
Fast Desk -> JSON
SMC Desk  -> JSON  -> Control Plane (:8765) -> WebUI / Observer
Account   -> JSON
Positions -> JSON
Risk      -> JSON
```

No hay archivos JSON en disco "runtime.json" que la WebUI lea directamente. 

No hay canal de comunicación privado entre WebUI y SMC.

Todo pasa por Control Plane. Así no hay surprises.

### El stack completo

```
┌─────────────────────────────────────────────────────┐
│             WebUI (Solid.js)                        │
│     apps/webui/src: componentes + rutas             │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────────────┐
│          Control Plane API (:8765)                  │
│     apps/control_plane.py: FastAPI                  │
└──────────────────┬──────────────────────────────────┘
                   │
       ┌───────────┼───────────┐
       │           │           │
   ┌───▼──┐   ┌────▼────┐  ┌──▼───┐
   │ Fast │   │ CoreRT  │  │ SMC  │
   │ Desk │   │ Service │  │ Desk │
   └──────┘   └────┬────┘  └──────┘
              │
       ┌──────▼────────┬──────────┬──────────┐
       │               │          │          │
   ┌───▼──┐    ┌──────▼──┐   ┌───▼────┐  ┌─▼──┐
   │Chart │    │MT5Conn. │   │Account │  │Risk│
   │Regs  │    │(serial) │   │ State  │  │Ker.│
   └──────┘    └────┬────┘   └────────┘  └────┘
                    │
             ┌──────▼──────────┐
             │  MT5 Terminal   │
             │  (broker)       │
             └─────────────────┘
```

---

## Configuración: variables de entorno

Sin código, solo variables. Ejemplos prácticos:

```ini
# --- MT5 (obligatorio) ---
MT5_TERMINAL_PATH=C:\Program Files\FBS MetaTrader 5\terminal64.exe # Ruta exacta de instalación MT5
MT5_WATCH_SYMBOLS=BTCUSD,EURUSD,GBPUSD,USDJPY,USDCHF,VIX,UsDollar
MT5_WATCH_TIMEFRAMES=M1,M5,H1,H4,D1
MT5_POLL_SECONDS=1
MT5_BARS_PER_PULL=200
MT5_MAGIC_NUMBER=20260315
ACCOUNT_MODE=live

# --- Mesa Fast (si quieres operar rápido) ---
FAST_TRADER_ENABLED=true
FAST_TRADER_RISK_PERCENT=1.0              # 1% por operación
FAST_TRADER_RR_RATIO=3.0                  # min 3 a 1
FAST_TRADER_MAX_POSITIONS_TOTAL=4         # máx 4 abiertas
FAST_TRADER_SCAN_INTERVAL=5               # chequea cada 5 seg

# --- Mesa SMC (si quieres tesis preparadas) ---
SMC_SCANNER_ENABLED=true
SMC_LLM_ENABLED=true                      # validación con IA
SMC_LLM_MODEL=gemma3:12b                  # Gemma local
SMC_LLM_URL=http://127.0.0.1:11434        # URL de LocalAI

# --- Risk global ---
RISK_PROFILE_GLOBAL=2                     # 1=conservador, 2=moderado, 3=agresivo
RISK_MAX_DRAWDOWN_PCT=5.0                 # máx 5% de pérdida
RISK_KILL_SWITCH_ENABLED=true             # activar botón de emergencia

# --- Control Plane API ---
CONTROL_PLANE_HOST=0.0.0.0
CONTROL_PLANE_PORT=8765
```

Lee el `.env.example` si quieres todos los detalles. Pero con estos arrancas.

---

## ¿Cómo corremos el sistema?

### Requisitos mínimos
- Python 3.10+
- MetaTrader 5 terminal abierto, autenticado
- (Opcional) LocalAI o Ollama con Gemma para SMC-LLM

### Pasos para empezar

1. **Crea el virtual environment (si no existe)**
```powershell
python -m venv .venv
```

2. **Activa el virtual environment**
```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell te rechaza el comando, ejecuta primero:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

3. **Instala las dependencias**
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Copia el archivo de configuración**
```powershell
cp configs/base.env.example .env
# Edita .env con TUS datos de cuenta MT5
```

5. **Inicia el sistema**
```powershell
python apps/control_plane.py
```

Eso es. Debería imprimir un banner así:

```
============================================================
  Heuristic MT5 Bridge — Control Plane
============================================================
  broker   : FBS-Demo (FBS-Demo)
  account  : 105845678
  balance  : $10,000 USD
  endpoint : http://0.0.0.0:8765
============================================================
```

6. **Inicia la WebUI (en una nueva terminal PowerShell)**

```powershell
.\.venv\Scripts\Activate.ps1
cd apps\webui
npm install   # solo la primera vez
npm run dev
```

7. **Abre la WebUI en el navegador**
```
http://localhost:5173
```

---

## Auditoría vs. Desarrollo

### Qué está **cerrado** (listo, certificado)

✅ **Control Plane API** — todas las rutas funcionan  
✅ **MT5 Connector — lectura** — acceso confiable a MT5  
✅ **MT5 Connector — escritura** — 5 métodos implementados y testeados  
✅ **Fast Desk execution** — pipeline completo funcionando  
✅ **SMC heurística** — 7 detectores + scanner funcionando  
✅ **WebUI base** — paneles principales implementados en Solid.js  

### Qué está **en desarrollo**

⏳ **SMC Trader** — aún integración de ejecución automática desde tesis  
⏳ **Multi-terminal** — múltiples MT5 en paralelo  
⏳ **Paper mode** — simulador para testing sin riesgo  
⏳ **IA mejorada** — modelos más grandes, mejor validación  

### Qué cambió recientemente (marzo 2026)

- Fast Desk: 8 gates estratégicas nuevas (market phase, exhaustion risk, BOS impulse, etc.)
- SMC: auditoría de doctrina (mitigation lifecycle, weighted confluences, sweep-CHoCH correlation)
- WebUI: Symbol Catalog + per-symbol desk assignment
- Slippage: ahora derivado del spec del broker, no hardcoded

---

## Palabra final: qué NO es este sistema

❌ **No es un bot que decide solo si operar o no**  
→ Tú controlas el dinero. El sistema sugiere.

❌ **No es un copiador de traders famosos**  
→ Es heurística pura. Estructura real, no ML cajas negras.

❌ **No es compatible con cualquier broker**  
→ Requiere MT5 y acceso API. Funciona en FBS, ICMarkets, etc.

❌ **No es set-and-forget**  
→ Requiere observación, ajuste de parámetros, comprensión de lo que el sistema hace.

---

## ¿Dónde ir si necesito más detalles?

- **Técnica pura**: lee `docs/ARCHITECTURE.md`
- **Code walkthrough**: ve `src/heuristic_mt5_bridge/` — estructura por carpeta es clara
- **Auditorías recientes**: `docs/audit/` — evidencia de qué se probó
- **Prompts + constructores**: `docs/prompts/` — contexto educativo

**Pero empieza por acá**. Si algo de esta guía no queda claro, es un bug de documentación.

---

## Resumen ejecutivo para traders

| Aspecto | Fast Desk | SMC Desk | Sistema |
|---------|-----------|---------|---------|
| Latencia | segundos | minutos | N/A |
| LLM | no | sí (opcional) | N/A |
| Análisis | escalping + heurística | estructura + confluencia | N/A |
| Custodia | trailing automático | preservación larga | N/A |
| Riesgo | centralizado en RiskKernel | centralizado en RiskKernel | ✅ |
| Control | la máquina | vos | ✓ WebUI + API |

**El sistema no decide por ti. Te da herramientas.**

Usa Fast para decisiones rápidas confiables.  
Usa SMC para tesis pensadas.  
Usa Risk para nunca perder más de lo que decidiste.

Que disfrutes el laboratorio. 🚀

---

*Documento actualizado a marzo 2026.*  
*Para preguntas sobre features específicas, revisa CHANGELOG.md.*
