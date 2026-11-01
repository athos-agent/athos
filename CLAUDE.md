# Athos: contexto para trabajar en este repo

## Para qué existe
Athos hace que el know-how operativo de una persona al trabajar con IA sea suyo. Lo captura mientras trabaja (en Claude Code, Codex, Muse Code y OpenCode), lo mejora, lo lleva de una plataforma a otra y permite delegar las tareas que ya domina a modelos chicos o locales, mucho más rápidos.

## Lo que defiende
- Libertad: lo que la persona sabe hacer con IA le pertenece a ella y no a la plataforma donde lo aprendió.
- Tiempo: una tarea que ya se domina puede correr rápido en un modelo chico.

## En qué se distingue
Cada usuario ve qué le aporta cada modelo en su propio trabajo. Un benchmark mide las pruebas de otros; Athos mide las tareas de quien lo usa.

## Qué hay acá y qué no
- Local, open source, Apache 2: plugin de Claude Code, Codex, Muse Code y OpenCode. Este repo.
- Athos Cloud es otro producto, privado y pago (sincronizar entre dispositivos, ver la memoria, decidir cada día qué se comparte, el agente de mejora como servicio). Vive en su propio repo (athos-cloud) y no comparte código con este.

## Reglas que no se negocian
- El know-how se guarda como markdown con frontmatter, legible por una persona: siempre se puede leer, editar y exportar.
- Nada sale de la máquina del usuario si él no lo pide explícitamente.
- No hay telemetría por ahora: las métricas se quedan en local.

## Tests
- Python: `HOME=$(mktemp -d) python3 -m unittest discover -s tests -t .` (con un HOME descartable, para no tocar `~/.athos`).
- El módulo de hooks de Claude Code (`hooks/ui.tsx` y `hooks/ui.test.tsx`): `claude plugin test .`; `claude plugin validate .` revisa el manifiesto.

## Hackathon
- Todo cambio entra por PR con la etiqueta `hackathon`; nada se commitea directo a main.
- Cada PR agrega su línea en `HACKATHON.md`, en "During the hackathon".
- Lo específico de Meta vive en `athos/adapters/meta/` y la evaluación contra modelos de Meta en `athos/eval/meta/`.
