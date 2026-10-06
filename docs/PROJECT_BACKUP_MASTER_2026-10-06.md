# OKX Bot Analyzer — Copia maestra de recuperación

Fecha de creación: 2026-10-06

Este documento existe para que el proyecto pueda recuperarse aunque se pierda el historial de un chat. No sustituye el código, Git, Render ni la especificación original; los conecta y documenta.

## Regla principal de recuperación

Antes de modificar producción, leer este documento, revisar la especificación original y comprobar el estado real de GitHub y Render. No reconstruir decisiones de memoria ni inventar requisitos ausentes. Si hay contradicciones entre versiones, preservarlas y resolverlas explícitamente.

## 1. Objetivo del producto

OKX Bot Analyzer es una aplicación web en español para analizar, seguir y evaluar bots de trading usados en OKX. Debe funcionar como sistema de apoyo a decisiones, no como generador compulsivo de operaciones.

Principios centrales:

- No conectarse automáticamente a datos privados de la cuenta de OKX en esta etapa.
- Datos privados del usuario: introducción manual o capturas confirmadas por el usuario.
- Datos públicos: mercado, OHLCV, volumen, volatilidad, indicadores, funding, noticias y documentación pública.
- Recomendaciones explicables y trazables.
- No inventar datos.
- No prometer rentabilidad.
- Priorizar preservación de capital y rendimiento ajustado por riesgo.
- Favorecer continuidad cuando una estrategia sigue siendo válida.
- Penalizar cambios innecesarios mediante switching cost.
- HOLD, WAIT y NO NEW POSITION son decisiones válidas.
- Guardar historial suficiente para evaluar posteriormente si una recomendación fue buena o mala.

Requisitos posteriores añadidos por el usuario:

- Interfaz completamente en español.
- Página pública accesible mediante enlace, sin instalación compleja para quien la use.
- Botón persistente abajo a la derecha para hablar con la IA.
- Usar pocas fuentes, pero de alta calidad y precisión, evitando saturación.
- Mostrar enlaces de las fuentes y explicar en qué se basa cada decisión.
- El usuario expresó preferencia por mantener el 100% del capital asignado a bots. Esto entra en tensión con la especificación original, que permite reserva/WAIT. No cambiar silenciosamente esta política; cualquier nueva política debe quedar documentada y validada.

## 2. Universo V1

Pares:

1. BTC/USDT
2. ETH/USDT
3. SOL/USDT
4. XRP/USDT
5. DOGE/USDT
6. BNB/USDT
7. SUI/USDT
8. LINK/USDT
9. ADA/USDT
10. LTC/USDT

Bots/estrategias contemplados:

- Spot Grid
- Futures Grid
- Spot DCA
- Futures DCA
- Smart Portfolio
- Smart Arbitrage
- Flywheel
- Recurring Buy
- Signal Bot
- Iceberg
- TWAP
- Arbitrage Order

No comparar indiscriminadamente herramientas de ejecución, arbitraje y estrategias direccionales como si persiguieran el mismo objetivo.

## 3. Filosofía cuantitativa

La aplicación debe combinar, cuando haya datos suficientes:

- 15m
- 1H
- 4H
- 1D

Indicadores y variables: EMA20/50/200, RSI, MACD, ADX, ATR, Bollinger, volumen, cambio de volumen, volatilidad histórica, momentum, estructura HH/HL/LH/LL, soportes/resistencias, rango, breakout, compresión/expansión de volatilidad.

El Market Regime Analyzer debe distinguir al menos estados alcistas, bajistas, laterales, breakout/breakdown, expansión/compresión de volatilidad y transición/incertidumbre.

Scores previstos: Market, Technical, Trend, Volatility, Bot/Market Compatibility, Bot Performance, Risk, Capital Efficiency, News/Sentiment, Confidence y Overall Opportunity.

La IA explica y sintetiza; no sustituye cálculos deterministas.

## 4. Persistencia de datos

Históricamente existieron dos esquemas de persistencia:

- V1 local: base SQLite local, con archivos dentro de `data/`.
- Versión pública posterior en Render: la interfaz mostró el aviso `Se guarda únicamente en este navegador`, por lo que datos como capital/configuración pueden estar en almacenamiento local del navegador.

Consecuencia crítica: GitHub y Render respaldan código/despliegues, pero NO garantizan por sí solos conservar los datos locales del navegador del usuario.

Prioridad futura: implementar Exportar copia de seguridad / Importar copia de seguridad dentro de la app, incluyendo capital, bots, historial, snapshots, configuraciones y cualquier localStorage relevante.

No pedir al usuario que borre caché, cookies o almacenamiento del sitio hasta exportar esos datos.

## 5. Cronología recuperada

### 2026-09-10

- V1 local funcional en Windows.
- Python 3.12 y `.venv` instalados.
- Aplicación ejecutada mediante `run.py`.
- Se pasó de DEMO a REAL mediante `activar_modo_real.py`.
- URL local usada: `http://127.0.0.1:8000`.

### Evolución posterior

La aplicación pasó a GitHub + Render y llegó al menos a v1.3/v1.4.

Commit importante de reparación de frontend:

- `50909252fbb30b5dac41e68198e57a4f78c9c72e`
- mensaje: `fix: repair v1.3 frontend patch output`
- función: reparar secuencias `\\n` literales introducidas en `app.js` que rompían el parsing de JavaScript.

Commit de arranque v1.3 reparado:

- `77bee1e6ba1b6f52ab393dae2851e99062636622`
- mensaje: `fix: run frontend repair before app startup`

Commit v1.4:

- `2b7ea3452366b287e05dd9b059589f2d7cae580e`
- mensaje: `feat: activate v1.4 analysis and dynamic allocation`

Problema encontrado: al activar v1.4 se reemplazó la lógica del archivo que también hacía la reparación del JavaScript; el frontend podía renderizar visualmente pero los botones/navegación dejaban de responder porque el JS no terminaba de parsear.

## 6. Estado de Render al crear esta copia

Servicio original de producción:

- nombre: `okx-bot-analyzer`
- URL: `https://okx-bot-analyzer.onrender.com`
- rama: `main`
- autoDeploy: activado
- start command: `python bootstrap.py`

Servicio temporal de recuperación UI:

- nombre: `okx-recovery-v14-ui-20261006`
- URL: `https://okx-recovery-v14-ui-20261006.onrender.com`
- rama: `recovery-v14-ui-20261006`
- autoDeploy: desactivado
- start command: `python recovery_launcher.py`

Servicio temporal de backtesting:

- nombre: `okx-backtest-v14-20261006`
- URL: `https://okx-backtest-v14-20261006.onrender.com`
- rama: `backtest-v14-20261006`
- autoDeploy: desactivado

## 7. Ramas de recuperación existentes

- `recovery-v13-20261006`: copia de referencia del estado v1.3 reparado.
- `recovery-v14-ui-20261006`: v1.4 con reparación del frontend reintroducida.
- `backtest-v14-20261006`: backtesting aislado de producción.
- `backup-project-context-20261006`: esta copia documental de recuperación.

No fusionar ninguna rama a `main` sin probar primero en staging.

## 8. Estado visible del usuario antes del problema

En una captura de la versión pública se observó, como referencia histórica y no como fuente contable definitiva:

- MODO REAL.
- Capital total aproximado: 111,95 USDT.
- Capital en bots: 0,00 USDT.
- PnL acumulado: 1,95 USDT.
- Recomendaciones visuales hacia ADA/USDT Spot DCA, LTC/USDT Smart Arbitrage, SUI/USDT Spot DCA y SOL/USDT Spot DCA.
- Enlace para ver fuentes del último análisis.
- Aviso de almacenamiento únicamente en el navegador.

Estos datos deben recuperarse desde el navegador original si se pretende preservarlos; no asumir que Render los contiene.

## 9. Backtest v1.4 recuperado

Backtest aproximado de casi 5 años, aislado de producción:

- Periodo: 2021-10-11 a 2026-10-05.
- 260 revisiones semanales.
- Capital inicial: 100 USDT.
- Capital final: 65,36 USDT.
- Rentabilidad total: -34,64%.
- CAGR aproximado: -8,18%.
- Máximo drawdown: -55,51%.
- Semanas positivas: 53,5%.
- BTC buy & hold de referencia: aproximadamente 156,87 USDT finales (+56,87%).

Interpretación: v1.4 no quedó validada para confianza ciega con capital real. La regla de mantener 100% invertido y el exceso de cambios fueron señalados como problemas potenciales.

Limitaciones del backtest:

- No replica exactamente fills privados históricos de OKX.
- Se usó histórico público para OHLCV/funding y un modelo de ejecución con fees/slippage.
- Noticias históricas se neutralizaron para evitar look-ahead bias.
- En la primera versión del replay, 1H actuó como aproximación del componente 15m y 4H/1D se reconstruyeron históricamente.

No presentar estos números como prueba definitiva de rentabilidad futura.

## 10. Protocolo obligatorio de cambios futuros

Antes de cada modificación importante:

1. Crear rama de respaldo desde el estado exacto actual: `backup-YYYYMMDD-HHMM`.
2. Guardar/actualizar un `PROJECT_BACKUP_MASTER` con objetivo, decisiones y estado.
3. Exportar los datos del navegador antes de tocar persistencia o dominio.
4. Hacer cambios en una rama nueva, nunca directamente sobre `main`.
5. Desplegar una copia staging con URL separada.
6. Verificar manualmente navegación, botones, análisis, capital, bots, historial y fuentes.
7. Ejecutar tests y, si cambia el motor, backtest comparable contra el mismo periodo.
8. Solo después promover a producción.
9. Mantener la rama previa durante un periodo de rollback.
10. Registrar commit, fecha, cambio, motivo y resultado de pruebas.

Importante: `main` tiene autoDeploy en Render. Un commit documental en `main` también puede disparar despliegue. Guardar documentación de recuperación en ramas dedicadas salvo que se quiera desplegar deliberadamente.

## 11. Criterio para recuperar el proyecto desde otro chat

Un nuevo asistente debe:

- Pedir o recibir este documento y la especificación original.
- Inspeccionar GitHub antes de afirmar qué versión existe.
- Inspeccionar Render antes de afirmar qué está desplegado.
- No borrar ni reescribir `main` de inmediato.
- Tratar `recovery-v13-20261006` como referencia de v1.3 reparada.
- Tratar `recovery-v14-ui-20261006` como intento de v1.4 con UI reparada.
- Mantener backtesting fuera de producción.
- Proteger datos del navegador antes de migraciones.
- Preguntar al usuario cuando haya conflicto de política financiera en vez de resolverlo silenciosamente.

## 12. Archivos que debe incluir una copia externa

- Este documento.
- `PROMPT_RECUPERACION_CHATGPT.md`.
- Especificación original completa de OKX Bot Analyzer.
- Cualquier exportación de datos del navegador.
- Backtests CSV/reportes/gráficos cuando existan.
- Manifest de ramas/commits/deploys.

## 13. Regla de verdad

Si un dato, requisito, commit, resultado de backtest o decisión no puede verificarse en documentación, GitHub, Render o archivos conservados, marcarlo como `NO VERIFICADO` en vez de inventarlo.
