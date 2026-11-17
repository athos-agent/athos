# Athos

*English: [README.md](README.md)*

![Un mosquetero camina por un camino soleado desde la puerta abierta de una torre, con un cuaderno abierto cuyas páginas brillantes se elevan en un checklist flotante: dos pasos tildados, uno en curso, dos por delante. A lo largo del camino, otras torres con las puertas abiertas muestran el mismo checklist, tildándose en el mismo orden.](docs/athos-banner.jpg)

Tu know-how con IA. Libre para moverse, rápido para correr.

**Athos guarda cómo trabaja una persona (sus pasos, sus criterios y sus checklists) como archivos markdown en su propia
computadora, para que cualquier agente de IA trabaje con sus reglas sin que se las repita.** Un modelo frontier aprende
una forma de trabajar una vez; cualquier otro modelo, hasta uno chico y local, la reusa.

**Para instalarlo paso a paso, con o sin terminal: [docs/INSTALACION.md](docs/INSTALACION.md)
([in English](docs/INSTALL.md)).**

Esta página está escrita para un agente de IA que tiene que usar, instalar o cambiar Athos. Cómo funciona por dentro:
[docs/DESIGN.es.md](docs/DESIGN.es.md). Cada comando y cada archivo: [docs/REFERENCE.es.md](docs/REFERENCE.es.md). Por
qué existe: [WHY.es.md](WHY.es.md). Para personas: [profesionales](docs/PROFESIONALES.md)
([in English](docs/PROFESSIONALS.md)), [Claude Desktop](docs/guides/claude-desktop.md),
[la galería](https://athos-agent.github.io/athos/).

## Qué hace, en cinco líneas

1. **Carga.** Con cada pedido, un router elige las piezas de know-how que corresponden, solo de este proyecto y del
   perfil de la persona. La pieza de otro proyecto entra solo cuando la persona nombra ese proyecto.
2. **Aprende solo, en un modelo frontier.** Una tarea cuyo trabajo quedó probado por una comprobación objetiva (una
   corrida de tests, un build, un commit) puede guardarse como pieza *candidata* sin preguntarle a la persona.
3. **Verifica.** Un segundo modelo frontier, con herramientas de solo lectura, revisa la candidata. Después, los reusos
   limpios suben su confianza; las fallas la retiran. Solo el know-how probado así llega a un modelo más débil.
4. **Reusa.** Un modelo apply (más barato, o local) recibe las piezas que corresponden y las sigue. Nunca aprende.
5. **Registra.** Cada decisión (qué se cargó y por qué, qué modelo respondió, qué se guardó) es un evento en un
   registro local que un agente puede volver a leer: `athos audit`.

## Modelos

| Nivel | Qué hace | Modelos por defecto |
|---|---|---|
| `frontier` | aprende y reusa; recibe un índice de piezas y abre las que necesita | `claude-fable-*`, `claude-mythos-*`, `claude-opus-*` |
| `apply` | solo reusa; recibe completas las piezas que corresponden | `claude-sonnet-*`, `claude-haiku-*`, y **cualquier modelo que ningún patrón nombra** |

Un modelo que Athos no conoce es `apply`: un modelo desconocido nunca aprende. Las listas se cambian con
`athos tiers add frontier '<patrón>'`; `athos tiers which <model-id>` responde para un modelo.

**Modelos locales y abiertos.** `athos delegate <piece-id> "<pedido>"` corre una tarea que sigue una pieza en un modelo
servido por Ollama en esta computadora (`--model <nombre>`), o en un modelo abierto en la nube
(`--backend openrouter|baseten|meta`). Cualquier modelo que sirva Ollama funciona así sin cambiar nada de Athos,
incluso uno recién publicado: lo bajás y pasás su nombre. `athos bench` y `athos shadow` miden si está a la altura de
las respuestas que la persona aprobó.

## Instalar

**Claude Code** (y la pestaña Code de Claude Desktop):

```
/plugin install athos --marketplace athos-agent/athos
```

**El comando `athos`** (lo necesitan OpenCode, la terminal y `delegate`), Python 3.11+ y nada más:

```sh
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start          # language, profession, example ways of working
```

**El chat de Claude Desktop:** [INSTALACION](docs/INSTALACION.md#1-claude-desktop-el-chat-de-siempre-sin-terminal).
**Codex, Muse Code, OpenCode:** [REFERENCE, Instalar](docs/REFERENCE.es.md#instalar). Actualizá el comando y el plugin
juntos: un Athos más viejo lee solo la parte reciente de un historial que uno más nuevo ya archivó (`athos doctor` dice
qué agente quedó atrasado).

## Lo que tiene que saber un agente que trabaja con Athos

- **Una pieza es una página markdown** en `~/.athos/know-how/`, con frontmatter (`title`, `when`, y opcionalmente
  `projects`, `visibility`, `status`) y un enunciado por paso: `**When:**`, `**Do:**`, `**Check:**`, `**Because:**`,
  `**Links:**`. Un `Check` es un comando o un hecho observable que prueba el paso; sin uno, una pieza nunca se
  verifica.
- **Seguí una pieza que se cargó para el pedido; abrí una del índice con `athos show <id>`.** `athos show` no escribe
  nada.
- **Guardá con `athos save` (stdin).** En un modelo frontier, el inicio de la sesión dice cuándo usar
  `athos save --auto`; un guardado automático con secretos, emails, rutas absolutas de esta computadora o nombres de
  otros proyectos se rechaza.
- **Estado:** `candidate` (aprendida, no probada), `verified` (el verificador aprobó ese texto exacto), `retired` (no
  se carga nunca). Una página sin `status` es de la persona: Athos nunca la reescribe si no se lo piden.
- **Un repositorio marcado como público** (`athos public on` escribe `.athos.toml`) carga y nombra solo las piezas de
  ese proyecto, y no guarda ninguna palabra de los pedidos de la persona. Si el marcador no se puede leer, Athos trata
  la carpeta como pública.
- **Las piezas `visibility: private`** nunca se nombran fuera de su proyecto y Athos nunca se las manda por su cuenta a
  un modelo.
- **Nada sale de la máquina** salvo que la persona lo pida. Sin telemetría.

## Los comandos que usa un agente

```
athos status            the store and this folder's session, in one line
athos list              every piece; ● marks the ones allowed to load here
athos show <id>         print one piece (no side effects)
athos save [--auto]     store the piece written on stdin
athos audit             what Athos decided in this session, and what it got wrong
athos report            what each piece and each model adds to the person's work
athos tiers             which models learn and which reuse
athos verify <id>       run the independent verifier on a candidate
athos memory check      the archive of old events against its manifest
athos public [on|off]   mark this repository public or not
athos profile           the few pieces that load in every project
athos delegate          hand a mastered task to a smaller or local model
athos doctor            which Athos each agent runs
```

## Lo que ve la persona

Una marca a la derecha del pie del cuadro de texto en Claude Code: un ■ rojo «Athos está aprendiendo» mientras un
modelo frontier hace trabajo real o corre el verificador, un ■ verde «Athos está colaborando» mientras se usa una de
sus piezas, y nada en otro caso. `ATHOS_UI=classic` trae de vuelta la interfaz anterior (el panel de la trayectoria,
la línea de estado, la banda).

## Dónde está cada cosa

| Ruta | Qué |
|---|---|
| `~/.athos/know-how/` | las piezas (markdown), con `.history/` de las versiones anteriores |
| `~/.athos/events.jsonl` | el registro vivo de eventos; los más viejos pasan a un archivo comprimido |
| `~/.athos/log.md` | las mismas decisiones, una línea cada una, para que las lea un agente |
| `~/.athos/config.json` | niveles, interfaz, topes del verificador, ajustes de la memoria |
| `.athos.toml` en un repositorio | su nombre para Athos y si es público |
| `athos/` en este repo | la CLI (Python, solo la biblioteca estándar) |
| `hooks/` | los hooks de Claude Code y el único módulo de UI (`ui.tsx`) |
| `athos/adapters/`, `codex/`, `opencode/` | los otros agentes |

## Trabajar en este repositorio

```sh
HOME=$(mktemp -d) python3 -m unittest discover -s tests -t .   # never against the real ~/.athos
claude plugin test . && claude plugin validate .
```

El código de los hooks tiene que correr en Python 3.9 (el que trae macOS). Todo cambio es un pull request; nada se
commitea directo a `main`. El repositorio es público: ni nombres de proyectos reales, ni personas, ni texto de pedidos
en el código, los tests o los mensajes de commit.

## Qué está medido y qué no

- Con el know-how de una persona, Muse Spark de Meta hizo bien 25 de 25 corridas del bench, y 2 de 25 sin él; el de
  pesos abiertos, Muse Spark Open, 35 de 35 y 0 de 35 ([las corridas, y qué le faltó a cada una](docs/bench/README.es.md)).
  Son casos chicos escritos para el bench.
- El aprendizaje autónomo se probó en vivo: el verificador rechazó dos veces una pieza, que pasó en su tercera versión
  y quedó verificada después de tres reusos limpios.
- Todavía sin medir: cuánto ayuda una pieza verificada a un modelo débil en una tarea que no puede hacer solo. En una
  tarea fácil, una comparación chica con y sin la pieza no mostró diferencia.

## Licencia

Apache License 2.0: [LICENSE](LICENSE), [NOTICE](NOTICE). Agradecimientos: [WHY.es.md](WHY.es.md#agradecimientos).
