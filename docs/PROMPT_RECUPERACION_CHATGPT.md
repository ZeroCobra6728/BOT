# Prompt de recuperación — OKX Bot Analyzer

Copia y pega este texto al iniciar un chat nuevo si necesitas continuar el proyecto después de perder contexto.

---

Quiero que continúes un proyecto existente llamado **OKX Bot Analyzer**. Antes de proponer cambios, debes reconstruir el estado real del proyecto con evidencia y no asumir nada de memoria.

## Fuentes de verdad que debes revisar

1. Repositorio GitHub: `ZeroCobra6728/BOT`.
2. Rama documental de respaldo: `backup-project-context-20261006`.
3. Archivo: `docs/PROJECT_BACKUP_MASTER_2026-10-06.md`.
4. Rama `recovery-v13-20261006` como referencia del último estado v1.3 reparado.
5. Rama `recovery-v14-ui-20261006` como intento de v1.4 con reparación del frontend.
6. Rama `backtest-v14-20261006` para el backtest aislado.
7. Render original: `https://okx-bot-analyzer.onrender.com`.
8. Render de recuperación: `https://okx-recovery-v14-ui-20261006.onrender.com`.
9. La especificación original completa que adjuntaré junto con este prompt.

## Qué pasó antes

El proyecto nació como una app local y luego se publicó en Render. Llegó al menos a v1.3 y después v1.4. En la transición a v1.4 se perdió una reparación de JavaScript que corregía secuencias `\\n` literales dentro de `app.js`; por eso la interfaz podía verse, pero los botones y navegación podían dejar de responder.

Commits importantes:

- `50909252fbb30b5dac41e68198e57a4f78c9c72e` — `fix: repair v1.3 frontend patch output`.
- `77bee1e6ba1b6f52ab393dae2851e99062636622` — `fix: run frontend repair before app startup`.
- `2b7ea3452366b287e05dd9b059589f2d7cae580e` — `feat: activate v1.4 analysis and dynamic allocation`.

No sustituyas producción por una rama de recuperación sin probarla primero.

## Requisitos centrales del producto

La aplicación debe estar en español, ser pública mediante enlace, usar datos públicos fiables y no conectarse automáticamente a información privada de la cuenta OKX en esta etapa. Debe explicar cada recomendación, mostrar fuentes, evitar inventar datos, aplicar riesgo y switching cost, analizar varias temporalidades, conservar historial y permitir HOLD/WAIT/NO NEW POSITION cuando corresponda.

Universo V1: BTC, ETH, SOL, XRP, DOGE, BNB, SUI, LINK, ADA y LTC frente a USDT.

La IA debe explicar y sintetizar, pero los cálculos de indicadores, régimen, riesgo y scoring deben ser deterministas y auditables.

## Persistencia y seguridad de datos

La versión pública mostró el texto `Se guarda únicamente en este navegador`. Por tanto, antes de borrar caché, cambiar dominio, cambiar almacenamiento o migrar la app, debes proteger/exportar los datos locales del navegador. GitHub y Render respaldan código/despliegues, pero no necesariamente esos datos del usuario.

Una prioridad próxima es implementar **Exportar copia de seguridad / Importar copia de seguridad** dentro de la app.

## Política de capital — conflicto que NO debes resolver silenciosamente

La especificación original permite mantener reserva y WAIT. Más adelante el usuario expresó que prefería tener el 100% del capital en bots. Un backtest posterior sugirió que forzar el 100% podía aumentar mucho el riesgo. No cambies esta política sin documentarlo y hablarlo explícitamente con el usuario.

## Backtest v1.4 recuperado

Backtest aproximado 2021-10-11 a 2026-10-05, 260 semanas, 100 USDT iniciales:

- final: 65,36 USDT;
- retorno: -34,64%;
- CAGR aprox.: -8,18%;
- max drawdown: -55,51%;
- semanas positivas: 53,5%;
- referencia BTC buy & hold: 156,87 USDT aprox.

Este backtest tiene limitaciones documentadas y no reproduce fills privados exactos de OKX. No lo presentes como garantía ni como simulación perfecta.

## Cómo debes trabajar conmigo

Soy usuario no técnico. Dame instrucciones simples, paso a paso, y no me hagas ejecutar muchas cosas de golpe. Antes de cualquier cambio en producción:

1. crea una rama de respaldo;
2. conserva el estado anterior;
3. prueba en staging;
4. verifica botones/navegación/datos/análisis;
5. haz backup de datos del navegador;
6. solo después despliega a producción.

Nunca digas que algo está recuperado, desplegado o guardado sin comprobarlo realmente.

Ahora empieza leyendo `docs/PROJECT_BACKUP_MASTER_2026-10-06.md` y la especificación original. Después inspecciona GitHub y Render y dime, sin modificar producción todavía:

- qué versión está activa;
- qué partes están sanas;
- qué partes están rotas;
- qué datos pueden estar en riesgo;
- cuál es el plan más seguro para continuar.

---
