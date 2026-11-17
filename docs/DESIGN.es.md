# Athos: diseño técnico

*English: [DESIGN.md](DESIGN.md)*

Para un agente de IA que tiene que razonar sobre Athos o cambiarlo. Corto a propósito: los formatos, flags y límites
exactos están en [REFERENCE.es.md](REFERENCE.es.md); esta página dice cómo encajan las partes y qué reglas no se pueden
romper.

## La idea en un párrafo

La forma de trabajar de una persona se guarda como páginas markdown (*piezas*). Un modelo fuerte aprende una pieza una
vez, de una tarea cuyo trabajo quedó probado por algo objetivo. Un segundo modelo fuerte la revisa. Desde ahí, cualquier
modelo, incluso uno chico y local, recibe la pieza y la sigue. Todo lo que Athos decide es un evento en un registro
local, así que un agente puede auditarlo. Nada sale de la máquina.

## Partes

```
agent (Claude Code, Codex, Muse Code, OpenCode, Claude Desktop)
   │  hooks: session-start, prompt, tool-start, tool, tool-failed, stop
   ▼
bin/athos hook <moment>            Python, standard library only, must run on 3.9
   ├─ load/        router: which pieces this request gets
   ├─ tiers.py     which models learn (frontier) and which reuse (apply)
   ├─ evidence.py  what each tool call proved (tests, builds, commits)
   ├─ autolearn.py whether this task may be saved without asking
   ├─ verify.py    the independent verifier (detached, another frontier model)
   ├─ grade.py     candidate → verified → retired, from verdicts and reuses
   ├─ memory/      live log → compressed archive → rollups (the dream cycle)
   ├─ audit.py     reads the log back and flags what Athos did wrong
   └─ indicator.py the one state the UI shows: learning, collaborating, idle
~/.athos/                          the person's store (the only state)
```

Los hooks son procesos cortos: cada uno lee un poco, agrega eventos y termina. Nada en un hook espera a un modelo. El
trabajo largo (el verificador, el ciclo de sueño) lo arranca desacoplado el hook Stop.

## Datos

| Qué | Dónde | Notas |
|---|---|---|
| Una pieza | `know-how/<id>.md` | frontmatter + un enunciado por paso (`When`, `Do`, `Check`, `Because`, `Links`); las versiones anteriores en `.history/` |
| Números que cambian de una pieza aprendida | `piece-meta.json` | confianza, última verificación, evidencia; nunca se escriben en el archivo de la pieza |
| Eventos | `events.jsonl` | solo se agrega, una línea JSON cada uno, agregada bajo un lock |
| Eventos viejos | `memory/archive/events-NNNNN.jsonl.gz` + `manifest.json` | segmentos comprimidos, nunca se borran, cada uno con su sha256 |
| Vistas derivadas | `memory/ledger.json`, `memory/rollups.json` | se reconstruyen desde el archivo en cualquier momento (`athos memory rebuild`) |
| Registro legible | `log.md` | una línea por decisión |
| Configuración | `config.json` | `tiers`, `autolearn`, `memory`, `ui` |
| El marcador de un repositorio | `<repo>/.athos.toml` | `name`, `public` |

Los archivos que escribe más de un proceso se reemplazan en un solo paso (se escriben al lado y después se mueven) y,
cuando se leen, cambian y se escriben, se cambian bajo un lock. Un archivo de estado que no se puede leer es un error,
nunca un valor vacío que se vuelve a escribir.

## Un pedido, paso a paso

1. **Inicio de sesión.** El hook registra la sesión y una suposición provisoria del modelo. Un modelo frontier recibe un
   índice corto de las piezas a su alcance, más la instrucción para guardar solo. Un modelo apply no recibe instrucción
   para guardar.
2. **Prompt.** El router puntúa las piezas en alcance contra las palabras del pedido. El alcance son las piezas de este
   proyecto y el perfil (las pocas piezas que la persona marcó como generales). Un proyecto sin piezas propias ve solo
   el perfil. Las piezas de otro proyecto entran solo cuando el pedido nombra ese proyecto; un proyecto que se llama
   como una palabra común necesita una frase que se refiera a él como proyecto. Dos márgenes dejan afuera una
   coincidencia débil. La entrega depende del nivel: un modelo apply recibe las páginas que coinciden (con tope); un
   modelo frontier recibe un índice y abre las páginas con `athos show`. Un evento `route` registra qué se eligió y
   por qué, sin las palabras del pedido en un repositorio público.
3. **Modelo observado.** El modelo se toma del primer pedido a la API de la sesión, no de la configuración. Hasta que se
   observa, no se guarda nada: un modelo supuesto nunca aprende.
4. **Llamadas a herramientas.** `tool-start` y `tool` registran evidencia: un comando de verificación y su resultado, un
   commit (visto observando `HEAD`), una pieza abierta, una edición. Una edición se atribuye a la persona solo cuando la
   evidencia muestra que el agente no la hizo.
5. **Stop.** La tarea termina. Los reusos de piezas se califican según la evidencia. Si el modelo guardó una candidata
   con `athos save --auto`, el verificador se arranca desacoplado. Si el registro vivo pasó su ventana, el ciclo de
   sueño se arranca desacoplado.

## Aprender

Guardar sin preguntar necesita todo esto: un modelo frontier que fue observado; una tarea con evidencia fuerte (una
corrida de tests, un build o un linter que pasa, o un commit); una pieza con al menos un `Check` ejecutable; nada de
datos privados (secretos, emails, rutas absolutas, nombres de otros proyectos); y ninguna pieza existente que ya diga
lo mismo (en ese caso se mejora esa pieza). La pieza empieza como `candidate`.

**El verificador** es otro modelo frontier, corrido sin interfaz con herramientas de solo lectura (`Read`, `Grep`,
`Glob`) sobre un paquete: la pieza, el diff de la tarea, la salida de la verificación, una instantánea de los archivos
que la pieza nombra y los asuntos de commits anteriores. Juzga cinco criterios: la evidencia pasó, la pieza coincide con
el trabajo, sus comprobaciones se pueden correr, no tiene datos privados, es reusable. Su veredicto cuenta solo para el
texto exacto que leyó. Valores por defecto: 6 corridas y US$1 por día, US$0,50 por corrida. Un rechazo le vuelve al
autor como devolución la próxima vez que se abre la pieza; tres versiones rechazadas seguidas dejan la candidata
apartada para la persona.

**Calificaciones** (`grade.py`):

- `candidate → verified`: el verificador aprobó este texto y, desde entonces, hubo dos reusos limpios en un modelo
  frontier o uno en un modelo apply cuyos `Check` los hooks vieron pasar. Una pieza `risk: high` siempre necesita un
  reuso limpio.
- `verified → candidate`: un reuso corregido o fallido con evidencia ligada a la pieza, o 90 días sin uso.
- `→ retired`: tres reusos corregidos o fallidos entre sus últimos cinco. Las piezas retiradas nunca se cargan;
  `athos revert` las restaura.
- Una página sin `status` es de la persona: se carga como una verificada y Athos nunca la reescribe.

Un reuso es limpio solo con evidencia objetiva. Las palabras de la persona («bien», «no, está mal») mueven la confianza,
nunca el estado. Un reuso en la sesión que escribió la pieza no cuenta.

## Modelos y niveles

`tiers.py` compara el id de un modelo con dos listas de patrones en `config.json`. Frontier: aprende, recibe un índice.
Apply: reusa, recibe páginas. Un modelo que no coincide con ningún patrón es apply, así que soportar un modelo nuevo
como reusador no necesita código: ya lo es. Hacer que un modelo aprenda es una línea, `athos tiers add frontier
'<pattern>'`, y se debe hacer solo para un modelo en el que se confía para escribir know-how que otros van a seguir.

Los modelos chicos y locales llegan a Athos de tres formas:

1. **Como el modelo del agente** (por ejemplo OpenCode con cualquier modelo): los hooks corren como siempre, el modelo
   es apply.
2. **`athos delegate <piece> "<request>"`**: el propio ciclo de Athos le da al modelo la pieza como instrucciones y un
   conjunto chico de herramientas, en Ollama (`--model <name>`), OpenRouter, Baseten o la API de Meta. Un modelo recién
   publicado para Ollama funciona por nombre.
3. **`athos shadow` / `athos bench`**: la misma tarea en un modelo más barato, comparada con las respuestas que la
   persona aprobó, para decidir si puede hacerse cargo de la tarea.

Lo que un modelo débil necesita de una pieza está en la forma de la pieza: pasos en orden, cada uno con un `Check` que
pueda correr. Por eso una pieza sin un `Check` ejecutable nunca se verifica.

## Memoria

El registro vivo guarda una ventana reciente (30 días o 4 MB, nunca menos de 8 días). El **ciclo de sueño**, que arranca
el hook Stop y corre sin modelo, tiene tres fases: archivar los eventos más viejos que la ventana en un segmento
comprimido; incorporarlos al ledger y a los rollups; recortar el registro vivo. Los hooks leen solo el registro vivo y
los rollups, así que su costo no crece con la historia; un test comprueba que ningún camino de hook lea toda la
historia.

Invariantes que el ciclo mantiene, cada una con un test y una corrida de estrés (procesos reales, la mitad ignorando el
lock, el ciclo matado al azar):

- Ninguna línea se pierde y ninguna se cuenta dos veces, con escritores que toman el lock y escritores que no.
- Un registro restaurado desde un backup se recorta, no se archiva de nuevo.
- Un segmento o un manifest dañado se informa y se reconstruye desde la carpeta, nunca se lee como «no hay archivo».
- Un ciclo que no puede avanzar dice por qué una vez y espera más antes de reintentar.
- El ledger y los rollups siempre son iguales a una reconstrucción desde el archivo.

Una pasada opcional con modelo que propone fusionar piezas usadas juntas está apagada por defecto y solo propone.

## Reglas de privacidad (no debilitar)

- **Alcance por proyecto.** Una pieza etiquetada con un proyecto se carga solo ahí, salvo que la persona nombre ese
  proyecto.
- **Repositorios públicos.** En un repositorio marcado como público (`.athos.toml`, `athos public on`), o en uno cuyo
  marcador no se puede leer, Athos carga y nombra solo las piezas propias de ese proyecto y las piezas del perfil
  permitidas ahí de forma explícita, no guarda palabras ni hash de los pedidos, y ningún comando de memoria muestra otro
  proyecto o una pieza oculta. Un test recorre todos los comandos de memoria para sostener esto.
- **Piezas privadas** (`visibility: private`): nunca se nombran fuera de su proyecto y nunca se ponen en un paquete que
  se manda a un modelo.
- **`athos show` no tiene efectos secundarios.** El uso lo cuenta el hook de herramientas dentro de una sesión, no el
  comando.
- **Sin telemetría.** Las únicas llamadas de red son las que inicia la persona: un backend de modelo para `delegate`,
  `bench` o `shadow`, y el verificador a través del propio CLI del agente.

## Auditoría

`athos audit` lee los eventos de una sesión y revisa reglas, por ejemplo: se cargó una pieza de otro proyecto; una carga
en un proyecto sin piezas; una edición atribuida a la persona sin evidencia; un modelo registrado distinto del que
respondió; un guardado hecho por un modelo apply; piezas superpuestas; un Athos más viejo escribiendo en una historia
archivada. Una historia equivocada nunca se edita: `athos repair --apply` agrega eventos de corrección.

## Lo que ve la persona

`indicator.py` reduce todo a un solo estado, que lee el único módulo de UI (`hooks/ui.tsx`) a través de
`athos status --ui`: `learning` (un modelo frontier está haciendo un trabajo del que se puede aprender, o el verificador
está corriendo), `collaborating` (hay una pieza en uso), `idle` (no se dibuja nada). El módulo dibuja un cuadradito rojo
o verde al lado de las etiquetas de modo del pie del prompt. Una falla en cualquier lado borra la marca en vez de mostrar
un error.

El chat de Claude Desktop no tiene hooks: `indicator.chat` calcula los mismos tres estados a partir de la sesión del
servidor MCP (`collaborating` mientras está en uso una pieza que entregó `athos_find`, o un paso de una, y gana;
`learning` mientras se redactan pasos nuevos sin pieza, o mientras se escribe un guardado desde el chat; `idle` en otro
caso), registrado como el mismo evento `ui`. `athos_find` abre el panel (`athos/mcp/trail.html`) en una forma mínima que
dibuja solo el cuadradito, una línea corta: su contenido es el estado, su `why`, el idioma y la interfaz, nunca una
pieza, un título, un paso o el pedido. El modelo igual informa los pasos con `athos_step`, que mueven el estado.
`"ui": "classic"` trae de vuelta el panel viejo.

El chat guarda solo cuando la persona lo deja (`autolearn.chat`, `own` por defecto): el `athos_save` del modelo ahí se
convierte en una pieza propia de la persona (sin status), a través de `autolearn.save_chat`, después de las mismas
comprobaciones de contenido que un guardado automático (`private_findings`, y `wiki.same_way` contra las piezas que el
chat puede nombrar: en ese caso se mejora esa). Registra un evento `learn` marcado `chat` con el modelo no observado,
que la auditoría lista como un guardado del chat en vez de señalarlo mientras la opción esté en `own`. Con `off` el
guardado del modelo se rechaza ahí, como en cualquier modelo que Athos no puede resolver. Cada herramienta MCP lleva
anotaciones (solo lectura, destructiva, mundo abierto) para que el host pueda agruparlas y recordar el permiso de la
persona.

## Cambiar Athos

- Los tests usan un `HOME` descartable; nunca el `~/.athos` real.
- El código de los hooks sigue siendo compatible con Python 3.9 y lee solo la ventana reciente.
- Todo lo que se agrega al registro de eventos pasa por el agregado con lock.
- Un cambio en lo que se carga se mide con `athos bench route` antes y después.
- Un tipo de evento nuevo tiene que estar contemplado en la incorporación de la memoria (archivado, incorporado, campos
  desconocidos tolerados).
- Un comando nuevo que muestra piezas o proyectos tiene que respetar la regla de repositorio público.

## Límites conocidos

- La ganancia de un modelo débil con una pieza verificada todavía no está medida en una tarea que no puede hacer solo.
- En un sistema de archivos sin hard links, una línea escrita tarde en el registro viejo durante un recorte se puede
  perder; el ciclo registra que corrió sin links.
- El ledger guarda una fila por tarea, así que el pico de memoria de un ciclo crece con el archivo.
- La comprobación de datos privados antes de un guardado automático puede rechazar texto inofensivo, y el verificador
  puede necesitar más de una versión de una pieza correcta.
