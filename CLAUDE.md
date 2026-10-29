# Athos — contexto maestro

## Qué es
Athos hace que el know-how operativo de una persona al trabajar con IA sea suyo. Lo captura mientras trabaja (en Claude Code, Codex, Muse Code y OpenCode), lo mejora, lo lleva de una plataforma a otra y permite delegar las tareas que ya domina a modelos chicos o locales, mucho más rápidos.

## Las dos ideas
- Libertad: el know-how es del usuario, no de la plataforma.
- Tiempo: lo que ya se domina corre en modelos chicos, rápido.

## El diferencial
Athos le muestra a cada usuario qué le aporta cada modelo en su propio trabajo. Los benchmarks miden pruebas ajenas; Athos mide las tuyas.

## Dos productos
- Local, open source, Apache 2: plugin de Claude Code, Codex, Muse Code y OpenCode. Este repo.
- Cloud, privado y pago: sincronización entre dispositivos, visualización de la memoria, control diario de qué se comparte y agente de mejora como servicio. Repo aparte (athos-cloud), nunca comparte código con este.

## Reglas
- El know-how se guarda en un formato legible por humanos (markdown con frontmatter). El usuario siempre puede leerlo, editarlo y exportarlo.
- Ningún dato sale de la máquina del usuario sin una acción explícita suya.
- Sin telemetría por ahora. Las métricas quedan en local.

## Hackathon
- Todo cambio entra por PR con la etiqueta `hackathon`; nada se commitea directo a main.
- Cada PR agrega su línea en `HACKATHON.md`, en "During the hackathon".
- Lo específico de Meta vive en `athos/adapters/meta/` y la evaluación contra modelos de Meta en `athos/eval/meta/`.
