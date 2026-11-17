# Referencia de Athos: todos los comandos

*English: [REFERENCE.md](REFERENCE.md)*

*El [README](../README.es.md) muestra cómo usar Athos sin comandos. Esta página es para quien prefiere la terminal:
instalar en cada agente, pasarles tareas a modelos más baratos, el bench y las carpetas de proyecto.*

## Instalar

En **Claude Code** (o en la pestaña Code de Claude Desktop):

```
/plugin install athos --marketplace athos-agent/athos
```

En **Codex**:

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

En **Muse Code**:

```
muse plugins marketplace add athos https://github.com/athos-agent/athos
muse plugins install athos@athos
muse plugins approve athos
```

En **OpenCode**, con el comando `athos` del instalador:

```
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos opencode install       then restart OpenCode
```

Después, `athos start` te pregunta tu idioma y tu profesión y agrega formas de trabajar de ejemplo (hoy hay de derecho, finanzas, periodismo, ciencia e ingeniería de guardia).

Requiere Python 3.11+ (el instalador elige el más nuevo que tengas). No tiene otras dependencias. Los hooks corren con
el `python3` que encuentre el agente, que puede ser más viejo (macOS trae 3.9): no necesitan `tomllib` y leen las
líneas `name` y `public` del marcador del proyecto sin él. Tu know-how vive en `~/.athos/know-how`, el mismo para todos
los agentes. Varios hooks, el verificador en segundo plano y tu editor pueden tocar los mismos archivos a la vez, así que
cada archivo que Athos escribe ahí y que escribe más de un proceso (una página, el estado de una sesión, el perfil, el
modo de carga, la configuración, las marcas de revisión, el reloj del detector de ediciones) se reemplaza en un solo
paso (se escribe al lado y después se mueve encima), y los que se leen, se cambian y se vuelven a escribir (una sesión,
el perfil, la configuración, las marcas de revisión) se cambian con un lock. Un archivo de estado que no se puede leer
se reintenta y después se informa como error: nunca se lee como vacío ni se vuelve a escribir encima de sí mismo.

## Uso

Athos funciona solo: carga el know-how que coincide con cada pedido y, en un modelo frontier, guarda lo que una tarea
demostró sin preguntarte (ver «Aprendizaje autónomo: candidatas, comprobaciones y un verificador» más abajo). Estos son
los comandos que vas a usar:

```
/athos:list          see your know-how and what is enabled
/athos:mark g        mark the last task: g good, c needed corrections, f failed
/athos:report        what each piece and each model brings to your work
/athos:codex         take your know-how to Codex
```

### Lo que ves: un cuadradito

En Claude Code (la terminal y la pestaña Code de la app de Desktop) Athos muestra una sola cosa, a la derecha del pie
del prompt, al lado de las etiquetas de modo propias de Claude Code, mientras el agente trabaja y mientras espera:

| estado | lo que ves | cuándo |
|---|---|---|
| aprendiendo | un ■ rojo y `Athos is learning` (`Athos está aprendiendo`) | la sesión corre en un modelo frontier con el aprendizaje autónomo activado, no hay ninguna pieza en uso, y la tarea en curso hizo trabajo o produjo evidencia (una verificación, un commit), o todavía está corriendo un guardado o una verificación independiente que empezó esta sesión |
| colaborando | un ■ verde y `Athos is collaborating` (`Athos está colaborando`) | una de tus piezas está en uso para la tarea en curso: entregada a un modelo apply, o abierta por un modelo frontier desde el índice; hasta que la tarea termina |
| inactivo | nada | todo lo demás: Athos apagado, nada coincidió, una pregunta que solo leyó, entre tareas |

Si pueden aplicar los dos, gana colaborando. No se dibuja nada más y no se te muestra ninguna línea de hook: ni línea de
estado, ni panel de trayectoria, ni banda encima del prompt ni sus botones, ni avisos (toasts), ni la línea «Stop hook
feedback», y al modelo no se le pide que te pase los ofrecimientos de Athos (un modelo más barato, la revisión
nocturna, una regla de tus ediciones, una nueva comprobación). Lo que Athos decide igual va a su registro
(`athos audit`), y cada cambio del cuadradito es un evento `ui` ahí.

`athos status --json` lleva el mismo estado como `state` (`learning`, `collaborating`, `idle`) con un `why` corto
(`gathering_evidence`, `task_with_work`, `save_asked`, `verifying`, `piece_delivered`, `piece_opened`, `nothing_in_use`,
`between_tasks`, `no_task`, `off`, …); `athos status --ui` es lo que consulta el módulo de hooks (solo eso, en esta
interfaz). Leerlo no escribe nada, salvo el único evento `ui` y `sessions/ui/<session>.json` cuando el estado
cambia. Un turno interrumpido nunca llega al hook Stop, así que una tarea se muestra como inactiva en cuanto la
transcripción de Claude Code anota que la interrumpiste (`interrupted`), o cuando su sesión no se movió en 6 minutos sin
ninguna llamada a herramienta en curso; una llamada a herramienta que empezó y no terminó mantiene el cuadradito
encendido todo lo que dure.

**La interfaz clásica.** `ATHOS_UI=classic` en el entorno con el que arranca Claude Code, o `"ui": "classic"` en
`~/.athos/config.json` (que también llega al chat de Desktop y al módulo de hooks sin importar cómo se arrancó Claude
Code), trae de vuelta todo lo de abajo: la línea de estado, el panel de trayectoria, la banda con [Guardar], [Ahora no],
[No aplicaba], [Ver trayectoria], [Cambiar este paso] y [Guardar la regla], la fila del veredicto, las barras, la línea
«siguiendo» y sus pasos, los avisos (toasts) y las líneas que se le pedía al modelo que te dijera. `ATHOS_UI=minimal`
(o `"ui": "minimal"`) es el valor por defecto.

Qué sigue visible y dónde, en la interfaz mínima: en el chat común de Desktop el panel se abre en una forma mínima que
muestra solo el mismo cuadradito, en una línea corta (ver «En Claude Desktop»), y `athos_library` igual abre la
biblioteca cuando la pedís; en OpenCode la barra lateral queda donde la pusiste, pero sus avisos de pasos están
apagados; `athos watch`, `athos watch --web` y `athos library` muestran lo que siempre mostraron, solo cuando los
corrés. Un comando que escribís vos (`athos list`, `athos mark`, …) imprime como antes.

Cuando una pieza ya demostró lo que vale, pasale la tarea a un modelo más chico y más barato: en tu propia máquina con
[Ollama](https://ollama.com), o en los modelos de Meta con Meta Model API (`--backend meta`, clave en `MODEL_API_KEY` o
`~/.athos/.env`):

```
athos delegate <piece> "<request>"           runs in the current folder; asks before every command and write
athos delegate <piece> "<request>" --model qwen3.5:9b
athos delegate <piece> "<request>" --backend meta       muse-spark-1.3; --model muse-wonder-1.0 for the largest
```

El modelo sigue la pieza con cuatro herramientas (correr un comando, leer, editar y escribir un archivo), encerrado en
la carpeta actual. La tarea aparece en `/athos:report` como `local / <model>`, al lado de Claude Code y Codex, y la
marcás como cualquier otra. No se delega nada salvo que corras `athos delegate`. El valor por defecto es `gemma4:12b`;
en nuestras pruebas un modelo de 4B no alcanzó para una tarea de release, y el de 12B la hizo en alrededor de un minuto
y medio pero igual necesitó una corrección. `--yes` corre los comandos del modelo sin preguntar: usalo solo en una
carpeta que puedas tirar.

El modelo de pesos abiertos de Meta también corre en las Model APIs de [Baseten](https://www.baseten.co)
(`--backend baseten`), a través del endpoint compatible con OpenAI de Baseten (`https://inference.baseten.co/v1`), en
el mismo ciclo que `--backend meta`. Creá una API key en
[app.baseten.co/settings/api_keys](https://app.baseten.co/settings/api_keys) (Organization settings → API keys →
Create API key; copiala en el momento, Baseten la muestra solo esa vez) y ponela en una línea de `~/.athos/.env` (o
exportala como `BASETEN_API_KEY`); Athos la lee solo para mandar el pedido y nunca la imprime:

```
BASETEN_API_KEY=<your key>
```

```
athos delegate <piece> "<request>" --backend baseten     meta-models/muse-spark-open-1026, recorded as `baseten`
athos delegate <piece> "<request>" --backend baseten --model meta-models/muse-spark-open
athos test <piece> --backend baseten                     your corrections as tests, on Baseten
athos shadow on --backend baseten                        the background comparison, on Baseten
athos merge <piece> <their-files>... --backend baseten   a model merges differing texts, on Baseten
athos bench <case> --agents baseten,meta,local --runs 3
```

El modelo por defecto es el slug que Meta publicó primero para él; la página del modelo en Baseten lista
`meta-models/muse-spark-open`, así que usá `--model` si tu cuenta muestra otro (`GET https://inference.baseten.co/v1/models`
los lista). El modelo siempre razona; Athos pide `reasoning_effort: low` (el valor por defecto de Baseten es `xhigh`).
Con `--by-step`, un enunciado cuyo `**Model:**` es `baseten` o `baseten:<model>` corre ahí, con `--allow-meta` como
para Meta. Igual que `--backend meta`, manda el pedido y los archivos que lee el modelo a un servicio alojado; no va
nada ahí salvo que lo elijas. En `athos bench`, el costo de una corrida en Baseten aparece como desconocido.

El mismo modelo de pesos abiertos también corre a través de [OpenRouter](https://openrouter.ai) (`--backend openrouter`),
que sirve `meta/muse-spark-open` desde varios proveedores de inferencia (BaseTen, Fireworks, Together, Nebius, Modal…) a
US$1,25 / 4,25 por millón de tokens de entrada y de salida. Creá una clave en
[openrouter.ai/settings/keys](https://openrouter.ai/settings/keys), cargá créditos y ponela en una línea de
`~/.athos/.env` (o exportala como `OPENROUTER_API_KEY`):

```
OPENROUTER_API_KEY=<your key>
```

```
athos delegate <piece> "<request>" --backend openrouter     meta/muse-spark-open, recorded as `openrouter`
athos test <piece> --backend openrouter                     your corrections as tests, through OpenRouter
athos bench <case> --agents openrouter,meta --runs 5 --without
```

Athos pide `reasoning: {effort: low}`. Con `--by-step`, un enunciado cuyo `**Model:**` es `openrouter` u
`openrouter:<model>` corre ahí, con `--allow-meta`. Manda el pedido y los archivos que lee el modelo a OpenRouter y al
proveedor que elija; no va nada ahí salvo que lo elijas. Una corrida del bench se cobra al precio de lista de arriba.

Para ver cuánto vale el know-how antes de confiárselo a un modelo más barato, `athos bench` corre la misma tarea varias
veces en cada agente y modelo, con y sin el know-how, y comprueba lo que dejó cada corrida (git, los tests, los
archivos) en vez de creerle al agente:

```
athos bench --list                                         the cases: code, data, devices, a planning method, finance ops, law, literature
athos bench all --agents claude,meta,local --runs 5 --without --max-usd 5
athos bench report                                         success, time, tokens and cost per agent; the cheapest that keeps up
```

`athos bench transfer` pregunta si lo que le enseñaste a un agente llega entero a los otros. Primero Claude Code trabaja
una tarea como la enseña una persona (su checklist, sus correcciones, «guardalo»); después, una carpeta nueva con otro
documento y sin checklist recibe un pedido de una línea en Claude Code, Codex, Muse Code y OpenCode, sin Athos, con
solo la carpeta `.athos/` del proyecto, y con la carpeta más el plugin. Cada punto del know-how de la persona se
comprueba por separado, y las reglas que agregó mientras enseñaba, que no existen en ningún otro lado, muestran lo que de
verdad viajó:

```
athos bench transfer contract-transfer --agents claude,codex,muse,opencode --arms A,B,C --runs 3 --max-usd 10
athos bench transfer chapter-transfer  --agents claude,codex,muse,opencode   an author's editing rules, the same way
athos bench transfer-report contract-transfer             per agent and arm: points applied, taught rules, time, cost
```

Cada corrida tiene una carpeta descartable y su propio home de Athos, así que tu almacén y tus tareas registradas quedan
intactos. Tus propios casos (una carpeta con `case.json`, `piece.md`, `setup.py` y `check.py`, como los de
`athos/bench/cases/`) van en `~/.athos/bench/cases/` y nunca salen de tu máquina.

Tu know-how vive en `~/.athos/know-how/`, una página markdown por pieza, como una wiki: cada paso es un enunciado
(cuándo / hacer / porque / enlaces), los enlaces siguen el orden en que se hacen las cosas en una tarea, e `Index.md`
dice dónde empieza cada tipo de tarea. Los recorridos que cruzan páginas se vuelven subagentes que mejoran con las
páginas. Ver [docs/WIKI.es.md](WIKI.es.md). Elegí qué puede cargarse con
`/athos:load auto | all | project <name> | pieces <id>... | none`, y copiá todo afuera con `/athos:export <folder>`.

Una forma de trabajar también se puede dictar. Grabate explicando cómo hacés una tarea (alcanza con una nota de voz) y
corré `athos save --from-audio memo.m4a [--lang es|en]`: Muse Voice Transcribe de Meta (`muse-voice-transcribe-1.0`, el
endpoint de archivos de Meta Model API) escribe lo que dijiste, y Muse Spark (`muse-spark-1.3`) lo convierte en un
borrador de pieza en el formato de arriba, un enunciado por paso, conservando tus palabras y dejando afuera lo que no
dijiste. Ves el borrador y se guarda solo cuando respondés que sí; `--yes` lo guarda sin preguntar, y sin terminal (un
agente que corre el comando) el borrador se imprime con el comando `athos save` que lo guarda. El endpoint acepta un WAV
mono de 16 bits a 16 o 24 kHz de hasta 10 minutos; cualquier otra grabación se convierte primero con `afconvert`
(macOS) o `ffmpeg` cuando alguno de los dos está instalado, y no se te instala nada. La grabación y su transcripción van
a Meta solo cuando corrés este comando, con tu `MODEL_API_KEY`.

### Una memoria por proyecto

Cada página dice a qué proyectos pertenece (`projects:` en su frontmatter). Una página que guardás pertenece al proyecto
en el que la guardaste. Por defecto (`auto`), una sesión en la carpeta de un proyecto carga las páginas de ese proyecto
y tu **perfil**; las páginas de otro proyecto se cargan solo cuando el pedido nombra ese proyecto («…like we did in
heat-v2»; «heat v2» también cuenta). Gana el nombre más largo: «heat-v2» nombra a heat-v2, no a un proyecto llamado
heat; y un nombre de cuatro letras o menos cuenta solo como palabra suelta («api» lo nombra «the api», no «api.js»).

**Un proyecto con nombre de palabra común necesita una señal** (desde 0.1.180). Un nombre que también es una palabra
común en tu almacén (cada una de sus palabras está en al menos el 10% de las páginas de los otros proyectos, y en dos de
ellas: la misma rareza de palabras con la que el router pondera las palabras, dejando afuera las páginas del propio
proyecto) o un nombre de una sola palabra de tres letras o menos («api», «web») es ambiguo: «the api returns 500» puede
no referirse al proyecto en absoluto. Un nombre así cuenta solo con una señal de referencia (desde 0.1.180 en las dos
direcciones):

- una preposición con el nombre solo al final de una frase («from api», «en api.», «the conventions of api»), pero no
  antes de otra palabra («the timeout in api calls», «errors from billing data», «en billing hay un error»);
- una frase de referencia («like we did in the api», «como hicimos en el api», «igual que en billing», «mirá cómo lo
  hace billing», «as in api»);
- un sustantivo de repositorio o de proyecto en cualquier lugar («the api repo», «el proyecto de billing», «repo api»,
  «api's repo»), y una carpeta, directorio, servicio, app, paquete o módulo solo después de una preposición o con «of»
  («in the api directory», «en el directorio api», «from the api service», «la carpeta de billing»), así que «the
  billing app crashes» y «the docs folder is stale» no lo son;
- una ruta (`~/api`, `api/`, `/api/`).

El nombre entre backticks o comillas, solo, ya no es una señal («the `api` key», «the "billing" column»); antes de un
sustantivo de proyecto, sí («the "api" folder»). Un nombre distintivo («heat-v2») sigue funcionando sin señal. En un
almacén chico casi todos los nombres son distintivos (una palabra tiene que estar en el 10% de las páginas de los otros
proyectos, y en dos de ellas, para ser común: con nueve de cien páginas de otros proyectos que dicen «billing», sigue
siendo distintivo), así que ahí «billing» todavía trae las páginas de su proyecto solo por la palabra, como antes de
0.1.180; solo un nombre de una palabra de tres letras o menos necesita una señal sea cual sea el almacén. Sin señal, en
un modelo frontier, el índice del pedido recibe en cambio una
línea (el pedido puede referirse también al proyecto `api`, con cuántas páginas tiene, y `athos list --project api`
para listarlas), así que decide el modelo; no se carga ni se lista por id nada de ese proyecto. En un modelo apply la
mención se descarta: no se trae nada de ese proyecto, y tampoco se ofrece nada (a un modelo apply se le dan páginas, no
un índice para elegir), así que ahí un pedido que sí se refería al proyecto necesita una señal. En un repositorio marcado
como público no se ofrece nada. El evento `route` registra cómo se decidió cada proyecto mencionado
(`named_how`: cue, distinctive, offered, rejected; en un repositorio público solo `named_how_count`) y los proyectos
ofrecidos (`offered_projects`), nunca las palabras; `athos audit` no señala una pieza de un proyecto ofrecido que el
modelo abrió por su cuenta. Medido el 2026-11-15 sobre las 1769 cabeceras de pedidos registradas de una persona: 40
nombraban otro proyecto antes; con la regla de la señal, 17 por una señal, 22 por un nombre distintivo, y 6 son
menciones ambiguas que ya no traen las páginas de ese proyecto. `bench route` (34/56 hit@1, 1 errado, 24/24 none ok),
`--from-store` y la repetición privada de una sesión (0 de 29 cargadas, en los dos niveles) no cambian.

Un proyecto que todavía no
tiene páginas propias ve solo el perfil (hasta 0.1.110 veía todas las páginas, y cargaba páginas de otros proyectos en
su primer día). El chat de Claude Desktop, que no tiene carpeta, sigue viendo todas las páginas, y `athos load all`
vuelve a un solo conjunto para todo (pero una página privada, ver abajo, se queda en sus proyectos).

El perfil es una lista corta que elegís vos de las páginas que aplican en todos lados, cómo trabajás siempre (12 como
máximo):

```
athos profile                         the pages in it
athos profile add <id>... | remove <id>...
athos profile allow-public <id>... | deny-public <id>...   whether a profile page also loads in a public repository
athos profile --untagged [--json]     the pages with no project, and whether each is in the profile (read-only)
```

Una página sin proyecto no es general solo porque no tiene etiqueta: fuera del perfil se carga solo donde no se conoce
ninguna carpeta, o con `athos load all`. `athos start` pone en el perfil las páginas de ejemplo de la profesión, y lo
mismo hace `athos add` con una página de la galería. Solo el perfil va a `~/.agents/skills`, la carpeta que Codex y Muse
Code leen en todos los proyectos (`athos export --codex` y la actualización después de cada guardado); `athos project
sync` les da las páginas propias de un proyecto a los agentes de ese proyecto.

Una sesión empieza con un índice: las páginas de este proyecto y el perfil, y de los otros proyectos solo una cuenta
(«12 formas de trabajar en otros 4 proyectos»), nunca sus nombres ni sus títulos.

**Quién puede ver una página.** El frontmatter de una página puede decir `visibility: private`, `project` o `general`.
Sin eso, una página con proyectos es `project` y una sin proyectos es `general`. Una página privada se carga solo en una
sesión de uno de sus propios proyectos, nunca donde el repositorio está marcado como público (ver abajo), y nunca se
nombra en la sesión de otro proyecto: ni en su índice, ni en el registro de auditoría, ni en `log.md` ni en nada de lo
que agregan los hooks, ni siquiera cuando el pedido nombra su proyecto.
`athos privacy [--json]` lista por id las páginas que parecen privadas (datos que apuntan a una persona o a una cuenta,
o un cuerpo sobre clientes, pacientes, dinero o producción), para que las revises; no cambia nada. Para marcar una,
agregá la línea `visibility: private` debajo de `projects:`.

**El marcador del proyecto.** Un `.athos.toml` opcional en la raíz de un repositorio:

```
name = "my-app"      # the project's name, whatever the folder is called (default: the repository's folder name)
public = true        # a public repository
```

Quien escribió un repositorio escribió su marcador, así que un `name` no se toma de confianza: un repositorio clonado
podría ponerse el nombre de uno de tus proyectos y llevarse las páginas de ese proyecto. Athos usa el `name` del
marcador cuando es el nombre propio de la carpeta, o una vez que lo aceptás para esa carpeta en esta máquina con
`athos public name` (guardado en `~/.athos/marker-names.json`, nunca en el repositorio; un cambio posterior del nombre
no se acepta hasta que lo vuelvas a correr). Hasta entonces se usa el nombre de la carpeta, `athos public status` lo
dice y `athos audit` informa `marker_name_ignored`. `public = true` vale sea cual sea el nombre: declarar público un
repositorio solo puede restringir.

Athos lo busca en la carpeta en la que corre una sesión y en cada carpeta por encima, sin depender de git, y falla
cerrado: cualquier marcador en el camino hacia arriba que diga `public = true` hace pública la carpeta, así que una
subcarpeta, un repositorio anidado dentro de uno público y una carpeta donde git no puede correr (no instalado, se
agotó el tiempo, rechazado por `safe.directory`) también son públicos. En un `git worktree` sin marcador propio, aplica
el marcador del worktree principal (encontrado a partir del archivo `.git` del worktree, así que esto tampoco necesita
git). Un marcador que está pero no se puede leer (TOML no válido, no es texto, o un `public` que no es `true` ni
`false`, como `public = "true"`) se lee como público. Lo que todavía se le escapa: un marcador en una carpeta que no es
ni la carpeta de la sesión ni una de las de arriba (un checkout hermano, el superproyecto de un submódulo al que se
llega solo a través de git, un repositorio cuyo `.git` vive en otro lado vía `GIT_DIR`), y un repositorio público sin
ningún marcador, que Athos no puede conocer (ver abajo).

**En un repositorio público, todo lo demás es privado.** En un repositorio cuyo marcador dice `public = true`, solo se
cargan las páginas propias de ese proyecto (y ninguna de ellas marcada como privada). Cualquier otra página se trata ahí
como privada, sea cual sea su `visibility`: nunca se carga y nunca se nombra, ni en el índice de la sesión, ni en el
índice de un pedido frontier, ni en una página entregada, ni en `log.md`, el diario, el panel o nada de lo que agregan
los hooks, aun cuando el pedido nombra su proyecto, cosa que en otro lado la traería (el evento `route` guarda solo
cuántos proyectos se nombraron, `named_count`). Ningún comando que se corra ahí nombra una tampoco: `athos list`,
`profile` (y `--untagged`), `report`, `wiki`, `status --json`, `privacy` y `audit` las dejan afuera o solo las cuentan;
un comando al que se le da el id de una página que no se puede nombrar ahí (`show`, `revert`, `test`, `share`, `route`,
`verify`, `dismiss`, `delegate`, `merge`, `export --piece`) responde exactamente igual que para un id que no existe,
así que la respuesta no dice si otro proyecto lo tiene, y lo mismo hace `athos save` con un `id:` así (no se cambia ni
se crea nada; una página nueva se guarda dejando afuera el `id:`); `athos audit` lee solo las sesiones de este proyecto
y rechaza `--show` y `--project` de otro; `athos journal --project` de otro proyecto se rechaza; `athos export` a una
carpeta escribe solo las páginas de este proyecto, y `--dataset` (que contiene pedidos) se rechaza. Una sola
comprobación (`control.Here`) decide por todos ellos, y un test corre cada comando en un repositorio público.
Las páginas del perfil entran en esto: una se carga en un repositorio público solo una vez que lo permitís con `athos
profile allow-public <id>`; por defecto, ninguna. No hace falta que marques las páginas una por una: el campo
`visibility` por página sigue disponible, y en un repositorio que no está marcado como público vale la regla de siempre.

**Declarar público un repositorio.** `athos public` escribe `public = true` en el `.athos.toml` de la raíz del
repositorio en el que lo corrés (lo crea con el nombre del proyecto si no existe, y conserva cualquier otra línea);
`athos public off` escribe `public = false`; `athos public status [--json]` dice qué está declarado y a qué sitios de
alojamiento de código se hace push del repositorio; `athos public name` acepta el nombre que le da su marcador. La línea
va entre las claves de primer nivel del marcador, antes de cualquier `[table]`, y el archivo se vuelve a leer: el
comando falla, y deja el archivo como estaba, salvo que ahora diga lo que se pidió. Un marcador que no se puede leer no
se toca: el comando dice que Athos trata el repositorio como público hasta que se arregle el archivo. Athos pregunta
porque no puede saberlo: si un repositorio es público es algo que vive en el sitio de
alojamiento, detrás de tu cuenta, y Athos no hace ninguna llamada de red. Tu configuración local de git solo dice a
dónde se hace push del código, no quién puede leerlo ahí. Por eso `athos audit`, corrido en un repositorio que tiene un
remoto en un sitio de alojamiento de código (GitHub, GitLab, Bitbucket, Codeberg y similares) y ninguna línea `public`
en su marcador, informa `public_not_declared` hasta que respondas en un sentido o en el otro. Hasta entonces el
repositorio se trata como no público.

En un repositorio público no se guarda ninguna palabra de un pedido ni ningún hash de un pedido: el registro de tareas
guarda el largo del pedido pero no sus primeros 120 caracteres, los eventos de auditoría y la sesión ninguna huella
(`request_sha`, `prompt_sha`), la sesión ninguna copia, y [No aplicaba] ninguna palabra. Sin huella, un camino especial
(guardar, ajustar) que actuó sobre un texto que se leía como de la persona antes de que Claude Code escribiera su
entrada en la transcripción se puede comprobar contra la transcripción solo cuando el hook da el id del prompt; si no,
queda sin verificar. Lo que sí se sigue guardando ahí son indicadores derivados de un pedido, nunca sus palabras: una
marca inferida de la reacción de la persona y `reaction_corrected`, `+named` en un motivo de alcance en `log.md` y
`named_count` (cuántos otros proyectos nombró, nunca cuáles), si mencionó un checklist, el idioma en que estaba escrito
(`lang_seen`) y su largo. El evento `route` dice cuándo aplicó un marcador (`marker`, `public`).

Medido en el almacén de una persona (71 páginas en diez proyectos, 252 tareas marcadas bien;
`athos bench route --from-store`): una página de otro proyecto se cargó en 14 tareas con un solo conjunto y en ninguna
con `auto`. Medido de nuevo el 2026-11-15 (91 páginas, 343 tareas marcadas bien), contando esta vez todas las tareas,
también las de proyectos sin páginas propias que la cuenta antes salteaba: 2 tareas con el alcance de 0.1.110, las dos
en proyectos así, y ninguna ahora.

### El diario: qué pasó últimamente en este proyecto

Junto a las formas de trabajar (la memoria de largo plazo, que cambia solo cuando guardás o aprobás), cada sesión
empieza con el pasado reciente de su proyecto: las últimas tareas con lo que usaron o guardaron y cómo salieron, lo que
se corrigió o falló en la última semana, y las tareas más viejas contadas por forma de trabajar. `athos journal
[--project <name>]` lo imprime. Se lee del registro de tareas que Athos ya lleva en tu máquina; no se guarda nada nuevo,
y el pasado de otro proyecto nunca aparece en este. Desde 0.1.180 el diario es memoria de corto plazo en sentido
estricto: sus líneas salen de la ventana del registro vivo (ver abajo); las tareas que el ciclo de sueño archivó solo se
cuentan en «Before that», nunca se citan.

### Memoria de largo plazo: el registro vivo, su archivo y el ciclo de sueño

Números de versión: la memoria de largo plazo, el ciclo de sueño y la pista para un proyecto con nombre de palabra común
llegaron a la línea principal en 0.1.180. Se construyeron en una línea de trabajo propia, numerada ahí de 0.1.165 a
0.1.179, mientras la línea principal iba de 0.1.165 a 0.1.172 sin ellos; esta referencia da los números de la línea
principal, y un evento marcado de 0.1.165 a 0.1.179 puede venir de cualquiera de las dos líneas.

El registro de tareas (`~/.athos/events.jsonl`) antes crecía sin límite, y los hooks lo leían entero. Ahora tiene tres
capas:

| capa | dónde | qué |
|---|---|---|
| corto plazo | `events.jsonl` | los eventos crudos de una ventana reciente: los hooks agregan acá |
| consolidada | `memory/archive/events-NNNNN.jsonl.gz`, `archive/manifest.json`, `memory/ledger.json`, `memory/rollups.json` | los eventos fuera de la ventana, comprimidos y nunca borrados (el manifiesto guarda las líneas, los bytes y el sha256 de cada segmento); el ledger, esos eventos agrupados por tarea sin una palabra de ningún pedido, con lo que solo lee el ciclo (pedidos que no encontraron ninguna pieza, contados, nunca citados; pasos que corregiste; descartes); los rollups, sumas chicas que leen los hooks, acotadas por la ventana y por la cantidad de piezas y proyectos, nunca por lo largo que sea el historial: por pieza (usos, resultados, por plataforma, nivel de modelo y proyecto, último uso, medias, la corrida que la enseñó), por proyecto (tareas, las piezas que usaron, su última tarea), piezas usadas en la misma tarea, lo que todavía pueden usar las reglas de calificación de una pieza aprendida, los resultados del verificador, las últimas corridas en sombra y estrellas, los usos archivados cerca del corte uno por uno, y un filtro de tamaño fijo de los ids de tareas archivadas |
| largo plazo | `know-how/`, `projects/<name>.md` | la wiki: tus piezas, y una página por proyecto que dice qué se sabe sobre trabajar en él |

El ledger y los rollups son derivados: borralos y `athos memory rebuild` vuelve a agrupar el archivo en los mismos
archivos (`athos memory check` los compara con una reconstrucción y comprueba cada segmento contra su manifiesto).

**La ventana.** El registro vivo guarda como mínimo `keep_days` (30) y como máximo `keep_bytes` (4 MB), y corta los días
más viejos cuando se pasa, pero nunca los últimos `min_keep_days` (8), así el diario y las marcas que miran una semana
atrás siempre leen el registro vivo. Todas estas son claves de `"memory"` en `~/.athos/config.json`.

**Qué lee qué.** Los hooks (inicio de sesión, pedido, herramienta, fin) y `athos status` leen solo los rollups y el
registro vivo, así que lo que cuestan no crece con el archivo: el historial de una pieza y las barras, el diario, el
historial de calificación de una pieza aprendida, qué candidatas esperan al verificador, las corridas en sombra y la
revisión de estrellas; lo mismo hacen `athos watch`, que redibuja cada dos segundos, y la elección de la tarea que marca
un `athos mark` sin argumentos (los importadores de sesiones de otros agentes que corre antes siguen leyendo todo el
historial, que necesitan para nunca importar una sesión
dos veces). Los
comandos offline leen todo el historial, el archivo descomprimido y después el registro vivo: `athos report`, `audit`,
`curate`, `repair`, `bench route --from-store`, los importadores de sesiones de Codex y Muse Code; `report`, `audit` y
`repair` lo dicen en stderr (`history: N archived event(s) in K segment(s) read with the live log`) cuando hay archivo.
Una tarea empezada antes del corte y seguida después se guarda entera en los rollups y se agrupa con sus líneas vivas, y
las barras deciden, para cada uso cerca del corte, si empezó después de la corrida que enseñó la pieza, esté donde esté
esa corrida. Una línea escrita sobre una tarea archivada (una corrección de `athos repair`, un `athos mark` tardío) queda
fuera de los números de los hooks hasta que los rollups la toman, cosa que `athos repair --apply` y `athos mark` hacen
en el acto, y el próximo ciclo hace en cualquier caso; los comandos offline la cuentan enseguida. Una línea sobre una
tarea que seguro no está en el archivo (su id no está en el filtro de ids archivados de los rollups: por ejemplo, un fin
sin inicio en ningún lado) cuenta enseguida como tarea nueva.

Lo que los rollups guardan de un historial largo: del historial de calificación de una pieza aprendida, el último paso a
candidata, la última aprobación del verificador para cada uno de sus últimos 8 textos, y para sus dos versiones más
nuevas los últimos 5 reusos juzgados y los últimos 4 de cada tipo (las reglas comparan cuentas con umbrales de 1 a 3,
así que deciden lo mismo que sobre todo el historial); las últimas 10 corridas en sombra por pieza y modelo; las últimas
20 estrellas por página y paso (el relato de una estrella sobre lo que se hizo ahí se descarta cuando repite cuatro
palabras del pedido sobre el que se dio). El filtro de ids de tareas archivadas ocupa 64 KB como mucho: pasadas unas
cientos de miles de tareas dice «quizás archivada» más seguido, y esa línea entonces espera a un ciclo, como antes.

**El ciclo de sueño**, en tres fases (a la manera de la repetición de ondas lentas, la abstracción REM y la
consolidación del sueño):

1. **Repetir y podar.** Los eventos fuera de la ventana, un prefijo del registro vivo, se escriben en un segmento
   comprimido nuevo, se agrupan en el ledger y los rollups, y recién entonces se recortan del registro vivo. No se borra
   nada.
2. **Abstracción**, contando, sin modelo: piezas usadas en la misma tarea (tres veces o más), pedidos que no encontraron
   ninguna pieza y los que volvieron más de una vez todavía sin ninguna (por huella, nunca por sus palabras), piezas que
   parecen la misma forma de trabajar (la prueba que usa `athos curate`, y enunciados para el mismo momento), pasos que
   corregiste a mano al menos dos veces, piezas cuyo propio Check falló en al menos dos reusos; y la revisión de
   estrellas que `athos dream` siempre hizo. Se guardan en `memory/findings.json` (`athos memory findings`).
3. **Consolidación.** Una página por proyecto, `projects/<name>.md`: sus formas de trabajar con sus usos, resultados y
   estado, las piezas usadas juntas, cada cuánto un pedido no encontró nada, y qué mirar. Nombra solo piezas que se
   pueden nombrar en las sesiones de ese mismo proyecto (las de otro proyecto se cuentan, y en un proyecto cuyo
   repositorio está marcado como público, solo lo que puede cargar ahí); no se cita ningún pedido. Una página sin la
   línea `written_by: athos` en su frontmatter es tuya y nunca se toca; una página que Athos escribió y reescribe se
   guarda antes en `projects/.history/`. Si el repositorio de un proyecto es público se guarda con sus cuentas, así
   sigue valiendo después de que se archivan sus eventos de ruteo. `athos memory project [<name>]` la imprime; en un
   repositorio marcado como público, solo la página de ese mismo proyecto, y nunca la página guardada tal cual: una que
   escribió Athos se vuelve a armar como ese repositorio la puede ver, y se deja afuera cualquier línea que nombre una
   pieza que ahí no se puede nombrar. `athos memory findings` ahí guarda solo las filas de este proyecto y las piezas
   que se pueden nombrar en él. El ciclo sin modelo no escribe ningún archivo de pieza: las asociaciones quedan en los rollups y las páginas
   de proyecto.

Cada paso se puede interrumpir y volver a correr: un segmento se escribe de forma atómica antes de que nada lo
referencie (sincronizado, con su carpeta, y lo mismo el manifiesto, el ledger y los rollups, así un corte de luz deja el
archivo viejo o el nuevo), el ledger lista los segmentos que agrupó, y el registro vivo se recorta solo mientras todavía
empieza con los bytes exactos de los segmentos, bajo el lock que toma cada agregado, retenido solo para la copia de lo
que queda. Un primer ciclo sobre un registro largo lo lee como flujo y escribe segmentos de 8 MB como mucho.

No se pierde ni se cuenta dos veces nada, escriba quien escriba el registro:

- *Quien escribe sin el lock* (un Athos más viejo, otra herramienta) y abrió el registro antes de un recorte y escribe
  después escribe en el archivo viejo: queda accesible bajo un nombre oculto (`.events.jsonl.trim-…`) y lo que le llega
  se traslada al final del ciclo y de nuevo en el siguiente (el hook Stop pide un ciclo cuando algo espera ahí), hasta
  que nadie le escribió durante 30 segundos. Cada recorte le da a ese nombre un token propio, así el mismo registro
  repuesto dos veces nunca reusa uno. En un sistema de archivos sin hard links el archivo viejo se lee por el handle que
  el recorte dejó abierto, trasladando líneas enteras a medida que llegan, hasta que no le llegó nada durante un segundo
  (15 s como mucho); el evento `replay` lo dice (`no_links`), ya que una línea escrita ahí más tarde no se traslada.
- *Un registro repuesto* después de un recorte (la restauración de un backup, una herramienta de sincronización, dos
  máquinas que comparten el home) empieza con segmentos ya archivados: todos los lectores los saltean por sus bytes,
  sea cual sea su estado, y el próximo ciclo los vuelve a recortar; los bytes que el archivo ya tiene nunca se escriben
  como segmento nuevo. Un backup que terminó dentro de un segmento empieza con las primeras líneas enteras de ese
  segmento, que se saltean y recortan de la misma forma. Una línea igual byte por byte a una archivada en un segmento
  superpuesto (turnos que un Athos más viejo volvió a importar, líneas archivadas que volvieron a mezclarse desde una
  copia) nunca frena el archivo: se archiva con el resto, su número figura en los `repeats` del segmento, y ningún
  lector la vuelve a contar (el evento `replay` dice cuántas, `repeats_skipped`). Un registro reemplazado entre el
  archivado y el recorte se deja como está (su segmento se marca `kept`), y el evento `replay` del ciclo dice por qué
  (`refused`).
- *Los lectores durante un ciclo* leen primero el registro vivo y después el manifiesto y los rollups (una lectura de
  todo el historial toma el lock de agregado para esas dos lecturas), así un ciclo que archiva y recorta mientras tanto
  no puede esconderles un segmento ni hacer que cuenten uno dos veces.

Ordenar nunca borra un segmento: un segmento temporal que dejó un corte de luz se promueve cuando se descomprime
(se descarta solo cuando los mismos bytes ya están en su lugar, y si no se aparta en `memory/archive/damaged/`); uno que
el manifiesto no lista se vuelve a listar; uno que no se puede leer se mueve a `damaged/`; un manifiesto que no se puede
leer también se mueve ahí y se reconstruye a partir de los segmentos en disco; y un ledger o unos rollups perdidos o
ilegibles los vuelve a armar el próximo ciclo, que los hooks arrancan apenas lo notan. Corre un ciclo a la vez: un
`flock` exclusivo sobre `memory/.cycle.lock` retenido durante toda la corrida, así nunca se le quita a un proceso vivo y
se va con un proceso que murió; si hay uno corriendo se lee del pid que quien lo tiene escribe en ese archivo, nunca
tocando el lock. Sin `flock` el archivo de lock se enlaza entero en su lugar (creado de forma exclusiva donde también
fallan los hard links) y se toma solo cuando el proceso que nombra ya no existe; un lock que no se puede tomar mientras
nadie lo tiene hace que los hooks esperen como con un ciclo trabado. El archivo viejo de un registro recortado al que
nadie escribió durante 30 segundos hace que el próximo Stop pida el ciclo que lo suelta. El
hook Stop lo arranca desacoplado y con baja prioridad, como arranca el verificador, cuando el registro vivo pasa
`trigger_bytes` (6 MB) o su evento más viejo tiene más de `trigger_days` (37), o un segmento quedó a medio hacer, o una
línea tardía espera; `"memory": {"auto": false}` lo apaga. `trigger_bytes` y `trigger_days` siempre actúan más allá de
lo que guarda la ventana (por encima de `keep_bytes` y `keep_days`), y una línea marcada con más de un día en el futuro
(un reloj mal puesto) cuenta como sin hora. Un ciclo que arrancaron los hooks y que no puede avanzar (por ejemplo, un
registro más grande que `trigger_bytes` todo dentro de los últimos `min_keep_days`) se saltea el conteo y las páginas,
deja un evento `memory_cycle` con `phase` stuck y `why`, y los hooks esperan una hora antes de arrancar otro, el doble
cada vez que sigue sin poder, hasta un día (`memory/cycle-state.json`); un ciclo que lanza una excepción deja un evento
`failed` (el tipo de error y dónde) y los hooks esperan de la misma forma. Cada fase es un evento `memory_cycle` (`run_id`, `phase`
(replay, abstraction, consolidation, model, done; stuck, failed), sus cuentas, `duration_ms`, para replay `archived_lines`,
`archived_bytes`, `compressed_bytes`, `live_before`, `live_after`, `rollup_bytes`, y `spend_usd` al final).

```
athos memory [status]                  the layers' sizes and dates, and whether a cycle is due or running
athos memory cycle [--model] [--json]  run it now, in the foreground
athos memory check                     every segment against its manifest; ledger and rollups against a rebuild
athos memory rebuild                   make the ledger and the rollups again from the archive
athos memory findings                  what the last counting found
athos memory project [<name>]          a project's page
```

**La pasada del modelo**, opcional y apagada por defecto (`"memory": {"model": {"on": true, "model": "<id or alias>"}}`,
o `athos memory cycle --model` una vez): en un modelo frontier, solo cuando ninguna sesión se movió en `idle_minutes`
(30) (un ciclo que arrancó el hook Stop no cuenta la sesión cuyo turno acaba de terminar, así que con la pasada
encendida puede correr desde ahí), y por debajo del tope diario que comparte con el verificador independiente
(`autolearn.budget`: primero se reserva el tope de la corrida, `max_usd_per_run` (US$0,50) o el tope por corrida del
verificador si es menor, con un evento `model_run` de `purpose` dream). Un proyecto por pasada, el que tiene más para
mirar. El modelo recibe, como
archivos en una carpeta y nada más, el resumen contado del proyecto (sin palabras de pedidos) y el texto de las piezas
de ese mismo proyecto que no son privadas (título, when, cuerpo: nunca las de otro proyecto, nunca una pieza privada,
nunca frontmatter ni historial), y corre como el verificador:
sin interfaz, con herramientas de solo lectura limitadas a esa carpeta, sin plugins, hooks ni MCP, con un home de Athos
descartable. Lo que propone
es siempre una candidata:

- un párrafo corto de lo que se sabe sobre trabajar en el proyecto va a `projects/<name>.candidate.md`
  (`status: candidate`), al lado de la página que escribe el conteo; no se inyecta en ningún lado;
- dos o más piezas del proyecto que son la misma forma de trabajar se vuelven una pieza candidata **nueva** (las de
  origen quedan como están), solo si `bench route --from-store` con ella no es peor que sin ella (no menos aciertos
  primeros, no más cargas de una pieza que la tarea no usó, de una pieza donde no hacía falta nada, o de otro proyecto;
  una carga de la fusión donde la tarea usó una de sus piezas de origen cuenta como acierto), y entonces va al
  verificador independiente como cualquier candidata. Sin ninguna tarea marcada como bien que haya usado una pieza, no
  se mide nada y no se guarda nada;
- una regla de evitar o de mantener para un paso es una nueva versión candidata de una pieza aprendida del proyecto, por
  el mismo camino de actualización versionada y el verificador (una pieza verificada se vuelve a verificar desde cero);
  para una pieza tuya (sin `status`) es solo una propuesta en `memory/findings.json`, nunca escrita en su archivo.

Cada escritura figura en el evento `model` del ciclo (`wrote`, cada una con el estado previo de la pieza).

**Piezas usadas juntas, al cargar.** `"memory": {"associations_line": true}` agrega como mucho una línea al índice de un
modelo frontier: la pieza que más seguido se usó en la misma tarea que la primera elección del router (tres tareas o
más, de los rollups y el registro vivo), cuando está al alcance y todavía no figura; un modelo apply no recibe nada más.
Está apagada: sobre 343 tareas bien de una persona (2026-11-15, dejando afuera de las cuentas los pares de cada tarea),
el router eligió una pieza para 91 de ellas por proyecto y 56 de esas usaron también otra pieza; la línea se agregó a 16
índices y nombró una pieza que la tarea usó en ninguno, y las tareas cuya otra pieza llegó al índice siguieron siendo 18
(con un solo grupo: 25 líneas, ninguna usada, 20 y 20). La elección del router, y por lo tanto `bench route`,
`--from-store` y la repetición privada, no cambian en ningún caso.

**`athos dream`** es la revisión de estrellas, sin cambios: `athos dream` lista sus propuestas y `athos dream --apply N`
convierte una en el pedido que lleva a cabo tu agente. Ahora es una parte de la fase de abstracción del ciclo, que la
refresca; `athos dream --cycle` corre el ciclo entero.

Lo que ves no cambia: el ciclo no muestra nada en la interfaz, y la única salida nueva es la de los comandos de arriba
cuando los corrés, y la línea `history:` de los comandos offline una vez que hay archivo.

### Curar: ordenar la memoria a medida que crece

`athos curate` lista lo que vale la pena ordenar, encontrado a partir de tus páginas y tu registro de tareas: una página
usada en un proyecto con el que no está etiquetada (la carga por proyecto la dejaría afuera ahí), una página sin usar
hace 45 días (nunca se propone una que otra página llama), dos páginas que parecen la misma forma de trabajar, enlaces a
páginas o pasos que no existen, y trabajo que vuelve una y otra vez en un proyecto sin página para él. `athos curate
apply <n>...` hace los mecánicos: etiquetar la página con el proyecto (una versión nueva) o moverla a `~/.athos/archive/`
(ya no carga; `athos curate restore <id>` la trae de vuelta). El resto queda para que actúes vos. No cambia nada hasta
que digas cuáles.

También aprende de lo que salió mal: cuando corregiste una tarea que siguió una página (tus palabras después de marcarla
corregida), propone un paso de «no hacer» para esa página con tus correcciones, e imprime el pedido que lo agrega, listo
para pegar; una página con al menos tres tareas corregidas o fallidas y más del doble que bien queda señalada para
revisar. Cada pasada se registra en `~/.athos/curate.json`: las propuestas que no se mostraron antes se marcan como
nuevas, y `athos curate dismiss <n>...` oculta una para siempre. Las pruebas y los ensayos no proponen nada: tareas en
una carpeta temporal o de demo, proyectos con nombre de una (prueba, test, demo, tmp, scratch, sandbox, example), y
cualquier proyecto que marques con `athos curate ignore <project>`.

### La biblioteca

`athos library [--port N] [--no-open]` abre todas tus formas de trabajar como una sola página en `127.0.0.1` (puerto
8712 por defecto, si no el siguiente libre), en inglés o en castellano como el resto de Athos:

- **Qué te aportó**: una barra por agente y modelo (las filas de `athos report`): sus tareas, cuántas usaron tu
  know-how, cuántas de esas marcaste como bien, y el tiempo y los tokens de cada una.
- **La lista**: cada forma de trabajar con para qué sirve, cuántas veces se usó y cómo salió (bien, corregida, fallida,
  según tus marcas), en qué agentes y modelos, y su última mejora (`v3: …`). Un filtro la acota por palabras. Una página
  a la que se llega por el `**Calls:**` o el `**If:**` de otra página queda debajo de ella, marcada con ↳ y la
  condición.
- **Una página**: sus pasos como checklist, con las ramas anidadas bajo el paso que lleva ahí (↳, como en el panel); sus
  versiones con la nota de cada una; **Volver a esta versión**, que primero pregunta y después trae esa versión de
  vuelta como una nueva (`athos revert <id> --to N` hace lo mismo; nunca se borra ninguna versión, y la página conserva
  la `visibility` y los `projects` que tiene ahora, así un `visibility: private` agregado a mano sobrevive); y **Abrir
  en el editor**, que abre el archivo markdown de la página con la app predeterminada de tu sistema (solo archivos dentro
  de `~/.athos/know-how`).

Nada sale de tu máquina. Las dos acciones de la página son pedidos POST que necesitan un token aleatorio generado para
cada corrida y que solo lleva la propia página, y el servidor responde solo pedidos dirigidos a `127.0.0.1`/`localhost`,
así otro sitio web abierto en tu navegador no puede ni llamarlas ni leer tu know-how. En el chat de Claude Desktop la
misma página se abre como MCP App cuando pedís ver tus formas de trabajar (`athos_library`, recurso
`ui://athos/library`); sus botones pasan por la herramienta solo de la app `athos_library_do`.

### Cómo elige el router el know-how, medido

En cada pedido Athos carga la pieza o las dos piezas cuyo título y «when» comparten las palabras del pedido (las
palabras más raras cuentan más, y una palabra cuenta con sus terminaciones: publish, published, publishing; publicar,
publicado; [No aplicaba] recuerda las palabras que cargaron una pieza por error). Desde 0.1.111 una pieza además
necesita un margen, porque el puntaje crece con el largo del pedido y un texto largo pegado comparte palabras con casi
cualquier página: al menos el 5% de las palabras de su título y su «when» tienen que estar en el pedido
(`head_share_min`), y esas palabras compartidas tienen que ser al menos el 7% de las palabras del propio pedido
(`request_share_min`), así un pedido no puede ganar por volumen. Lo que agrega un pedido tiene un tope de 8000
caracteres. Una página que no entra llega como sus pasos (desde 0.1.117): el When y el Do de cada enunciado, y sus
traspasos, sin las razones, los enlaces ni el historial, con una nota de cómo leer la página entera (`athos show <id>`);
si ni eso entra, tantos pasos enteros como entren, nombrando los que quedaron afuera. Una página sin enunciados se corta
en una línea. El evento de ruteo lo registra (`steps_only`, `cut`, `left_out`). En el almacén de una persona (91 piezas,
2026-11-15) 13 archivos de pieza pasan los 8000 caracteres (por 126 a 18963, mediana 2410) y 12 no entraron en un
pedido: cortados en una línea, entregaban 112 de sus 191 pasos con When y Do; como pasos, 158, y 7 de los 12 llegan con
todos sus pasos. Nada de eso le pide al modelo trabajo visible: ninguna línea inicial que nombre la página, ningún
comando de pasos; solo la página y una nota corta sobre cómo responder. `athos bench route` mide esa elección
antes de que algo la cambie:

```
athos bench route                         the public cases on a throwaway store of the starters (both languages),
                                          and each language's requests against the other language's starters only
athos bench route --scale 300             also a store padded to 300 pages with generated pages from other trades
athos bench route --router lexical,hybrid words only vs words + meaning (needs Ollama, see below)
athos bench route --from-store            your own tasks marked good against your own store: read-only, counts only
athos bench route --replay <file>         one session's requests again, through the scope the hooks apply
athos bench route --json
```

Los casos (`athos/bench/route_cases.json`, ficticios) son pedidos en inglés y en castellano para cada starter (derecho,
operaciones, periodismo, ciencia, finanzas), redactados de forma directa y como paráfrasis con pocas palabras en común,
más pedidos que no necesitan know-how («qué hora es», «escribí un haiku»). Informa hit@1 (la primera pieza cargada es la
esperada), missed (no cargó nada), wrong (cargó una pieza que el pedido no pedía; las páginas a las que una pieza
esperada hace traspaso no cuentan) y «none ok» (un pedido que no necesita nada no cargó nada), con el tiempo por pedido
incluida la lectura del almacén. `--from-store` usa el pedido que empezó cada tarea que marcaste como bien y las piezas
que usó, e imprime solo totales, nunca un pedido. `--replay <file>` corre los pedidos de una sesión (un archivo JSON que
guardás fuera del repositorio, ya que tiene pedidos reales: `{"project": "<name>", "cwd": "<optional folder>", "public": <optional
true>, "cases": [{"request": "...", "expect": []}]}`, siendo `expect` los ids de las piezas que debería cargar, ninguna
si está vacío) a través del modo de carga y el alcance por proyecto que aplican los hooks, la regla de lo público (el
`public` del caso, o el marcador de su `cwd`), y lo que se le puede dar al modelo del nivel (ninguna pieza retirada; a un
modelo apply solo las verificadas y las heredadas), después `load.relevant`, y cuenta los pedidos donde algo cargó,
donde cargó una pieza de otro proyecto, donde cargó una pieza general, los que cargaron exactamente lo esperado, y los
caracteres agregados (el máximo y la media); `--show` agrega, por cada pedido que cargó algo, su número, su largo y los
ids cargados, nunca su texto. Medido el 2026-10-31 sin los starters de deportes (embeddinggemma con un Ollama local):

| router | almacén | hit@1 | wrong | none ok | ms/pedido |
|---|---|---|---|---|---|
| palabras | starters, en+es (14 páginas) | 34/56 | 2 | 23/24 | 1.3 |
| palabras + significado | starters, en+es | 43/56 | 2 | 23/24 | 17 |
| palabras | pedidos en castellano, starters en inglés | 0/28 | 0 | 12/12 | 0.6 |
| palabras + significado | pedidos en castellano, starters en inglés | 6/28 | 0 | 12/12 | 20 |
| palabras | pedidos en inglés, starters en castellano | 0/28 | 0 | 12/12 | 0.7 |
| palabras + significado | pedidos en inglés, starters en castellano | 10/28 | 0 | 12/12 | 14 |
| palabras | en+es, 300 páginas | 33/56 | 7 | 23/24 | 15 |
| palabras + significado | en+es, 300 páginas | 40/56 | 11 | 21/24 | 36 |

Con el margen (0.1.111, medido el 2026-11-15, solo palabras): starters en+es 34/56, 1 wrong, 24/24 none ok; 300
páginas 33/56, 6 wrong, 24/24; las corridas entre idiomas sin cambios. Los dos valores fueron los más altos que no
costaban ningún acierto en estos casos y a la vez rechazaban la mayoría de las cargas de una sesión real cuyos pedidos no
necesitaban nada (entre ellos, textos largos pegados). En las tareas propias de una persona (`--from-store`, por
proyecto) hit@1 pasó de 38 a 28 de 141: 8 de los 10 perdidos los rechazó el margen (7 de ellos coincidencias de una
sola palabra en páginas con un «when» largo) y 2 son páginas que ya no están al alcance ahí (una página sin etiquetar
fuera del perfil). Ese bench cuenta como esperado lo que haya cargado en su momento, así que premia al router viejo; los
pedidos que no necesitaban nada y cargaron algo pasaron de 20 a 13 de 202.

**Pedir en vez de empujar, en modelos frontier.** Cuando el modelo que responde un pedido está en el nivel frontier
(`athos tiers`), la elección del router no se pega: el pedido recibe en cambio un índice corto de las piezas al alcance,
las mejores primero (la elección del router y las páginas a las que hace traspaso, después las otras piezas que puntuó,
después el resto de las piezas de este proyecto y tu perfil, las usadas más recientemente primero), una línea cada una
con id, título y «when», como mucho 6 líneas y 1200 caracteres, y una oración: si alguna aplica, leela con `athos show
<id>` y seguila; si ninguna aplica, ignorá la lista. El modelo abre lo que necesita, y eso cuenta como usar la pieza
(ver abajo). Una mala elección del router entonces cuesta unas líneas en vez de una página. Un modelo apply, o uno de
nivel desconocido, sigue recibiendo las piezas mismas, ya que sigue mejor de lo que elige. Si no se eligió nada no se
agrega nada, en ningún nivel. El evento de ruteo dice qué entrega se usó (`delivery`: index o piece) y mide las dos
(`index_chars`, `piece_chars`). `athos bench route --replay <file> --tier frontier|apply` repite una sesión como para
cualquiera de los dos niveles (los dos por defecto).

En el bench, «cargado» es la elección del router en cualquiera de las dos entregas: las piezas que recibe un modelo
apply, y las primeras líneas del índice que se le ofrece a un modelo frontier. Por eso hit@1 es igual para las dos, y
dice si la pieza correcta está arriba de todo en el índice en frontier; lo que cambia es el tamaño. Medido el
2026-11-15 en los casos públicos (starters en+es, pedidos que cargaron algo): piezas, media 3336 y máximo 6823
caracteres; índice, media 1013 y máximo 1075.

**Leer una pieza no escribe nada.** `athos show <id>` imprime una pieza y deja todo como estaba: ninguna sesión, ningún
evento, ni la fecha de último uso de la pieza, así vos (o un agente que revisa tus reglas) podés leer cualquier pieza
sin que cuente como usada. Cuando el agente corre `athos show` dentro de una sesión, el hook de herramienta ve el comando
y cuenta la pieza como usada para esa tarea (evento `piece_opened`; la pieza se suma a las piezas de la tarea y se le
acredita una edición después de las ruteadas); el archivo de una pieza leído directamente del almacén se dibuja en la
trayectoria pero no se cuenta. `athos show --use <id>` la cuenta desde la línea de comandos, en la sesión de la carpeta
donde lo corrés.

`athos embed on` le suma significado a las palabras, con un modelo de embeddings local a través de Ollama (por defecto
`embeddinggemma`, `athos embed on --model <name>` para otro; antes, `ollama pull embeddinggemma`). Está apagado por
defecto, y apagado, o con Ollama caído, la carga es exactamente el router de solo palabras. Encendido, el título, el
«when» y las líneas `When:` de los enunciados de cada pieza se embeben una vez y se guardan en `~/.athos/index/` (por
pieza y por un hash de ese texto, así una pieza editada se vuelve a embeber); las piezas todavía sin indexar las completa
un trabajo en segundo plano, nunca mientras esperás. En cada pedido, cuando las palabras ya encontraron una pieza clara
no pasa nada más; si no, se embebe el pedido (en menos de 300 ms, si no solo palabras) y la pieza más cercana en
significado se suma cuando queda claramente por encima de su cercanía habitual a cualquier pedido: esto es lo que deja
que un pedido en castellano encuentre una pieza en inglés. [No aplicaba] vale también para estas cargas.
`athos embed` muestra si está encendido y cuántas piezas están indexadas; `athos status --json` tiene `embed`. Nada sale
de tu máquina. En el bench de arriba rescata pedidos entre idiomas y parafraseados sin nuevas cargas equivocadas en los
starters, pero en el almacén de 300 páginas agrega cuatro cargas equivocadas, así que sigue siendo opcional.

### El registro de auditoría: qué decidió Athos, para que un agente lo revise

Cada decisión que toman los hooks queda escrita en tu máquina, junto al registro de tareas (`~/.athos/events.jsonl`), y
nada de eso guarda las palabras de un pedido: solo su largo y una huella de 12 caracteres (`request_chars`,
`request_sha`).

| evento | se escribe cuando | campos |
|---|---|---|
| `route` | cada pedido que ve el hook de pedido, cargue algo o no | `task_id`, `model`, `model_source` y `model_observed` (el pedido se decidió sobre una suposición cuando es false; ver «Qué modelo respondió, y los niveles de modelos»), `tier`, `work_mode`, `collaborates` (un modelo apply siempre; uno frontier cuando cargó una pieza), `mode` (el modo de carga), `project`, `scope_reason`, `named_projects` (vacío en un repositorio público), `named_count` (en un repositorio público: cuántos otros proyectos nombró el pedido), `named_how` (cómo se decidió cada proyecto mencionado: cue, distinctive, offered, rejected; no en un repositorio público, donde `named_how_count` los cuenta), `offered_projects` (proyectos con nombre de palabra común ofrecidos en una línea del índice a un modelo frontier), `marker` (se aplicó un `.athos.toml`), `public`, `private_held` (piezas privadas dejadas afuera, contadas), `store_pieces`, `in_scope`, `request_chars`, `request_sha` (no en un repositorio público), `request_kind` (person, harness, empty), `wrapper`, `candidates` (hasta 5: `piece`, `score`, `shared` (cuántas palabras comparte con el pedido, nunca cuáles), `head_share`, `request_share`, `projects` (en un repositorio público solo este proyecto, nunca el nombre de otro), `kept`, `reason`), `scored`, `chosen`, `handed_over` (páginas que trajo el `**Calls:**` o el `**If:**` de una página elegida; solo páginas dentro del alcance de este pedido, las mismas que podía elegir el router), `meaning`, `thresholds`, `cut` (páginas cortadas para que entren), `left_out` (páginas sin lugar), `steps_only` (páginas dadas solo como el When, el Do y el Check de sus pasos, enteros), `delivery` (piece: las páginas mismas, a un modelo apply; index: una lista de las piezas al alcance, a un modelo frontier; null cuando no se eligió nada), `offered` (los ids que listó el índice), `piece_chars` e `index_chars` (lo que cuesta cada entrega, medido de las dos formas), `injected_chars` (el texto propio del router), `injected_total` (todo lo que el hook de pedido le pasó al modelo: el texto del router más un aviso de edición, un pedido de compartir o una calificación agregados después), `injected_parts` (los caracteres de cada uno: `pieces`, `connectors`, `offer`, `edit`, `share`, `rating`), `ms` |
| `edit_seen` | el detector de ediciones guarda un archivo que escribió el agente, ve que el agente lo vuelve a cambiar, o encuentra un cambio en el pedido siguiente | `task_id`, `file_sha` (un hash de la ruta), `decision` (snapshot, rebased (lo cambió el agente: la copia avanza), pending (la persona lo cambió entre dos llamadas a herramientas; se avisa en el pedido siguiente), attributed, unattributed (un cambio sin evidencia: no se le atribuye a nadie)), `source` (agent_tool, agent_shell, outside, unexplained), `basis` (la evidencia de la decisión: `changed_during:<tool>`, `no_timing:<tool>`, `tool_failed`, `changed_between_tool_calls`, `changed_after_turn_end`, `no_tool_call_since`, o por qué no hay ninguna: `no_turn_end`, `changed_before_turn_end`, `tool_after_turn_end`, `background_task_running`), `attributed_to` (agent, person, o null), y para un cambio atribuido a la persona `detector` (between_tool_calls, after_turn_end), `piece` (no en un repositorio público), `piece_basis` (current_step, route_best, none) |
| `model` | empieza una sesión, cada pedido, el primer hook de herramienta o guardado o fin de turno que observa un modelo que hasta entonces solo se suponía o se desconocía, y el fin de una tarea cuyas respuestas se pudieron leer | `task_id`, `model`, `source` (event: lo dijo el hook; transcript_switch: un cambio con `/model` más nuevo que el último pedido o respuesta; transcript_request: el último pedido que mandó la conversación principal, su fila `api-request`, escrita antes de cualquier respuesta; transcript_reply: la última respuesta; session: lo que informó la sesión, cuando lo informó después de estos, o lo último observado; replies: las respuestas que contestaron la tarea; una suposición: launch_flag, env o settings; unknown), `observed` (false para una suposición o unknown), `guessed_from` (para una suposición: `--model`, `ANTHROPIC_MODEL`, `user`, `project` o `project_local`), `seen_in_transcript` (el modelo de la última respuesta del transcript), `stage` (session_start, prompt, tool_start, tool, save, stop, end), `changed`, `tier` (frontier, apply), `work_mode` (learn, collaborate), para una observación que reemplazó una suposición `corrects` y `corrects_source`, y al final `answered` (los modelos cuyas respuestas contestaron la tarea) y `at_start` |
| `trigger` | coincide un camino especial: guardar, ajustar, galería, compartir | `task_id`, `trigger`, `from_person` (true; false para un envoltorio del harness como el mensaje de un subagente, en cualquier parte del texto y en cualquier caso, también uno que abre con otro envoltorio, o cuando el transcript dice que lo mandó el harness; un guardar o ajustar cuyo texto abre con sus propias palabras («Athos · save:») es de la persona aunque mencione una etiqueta de envoltorio, salvo que haya venido con él un elemento envuelto entero (la etiqueta y su etiqueta de cierre); null cuando el texto abre con otra etiqueta o el transcript todavía no tiene una entrada para él), `acted` (actúa solo cuando `from_person` es true), `wrapper`, `origin_signal` (qué señal decidió: `heuristic`, `both`, `disagree`, `missing:verify` (actuó sobre el texto, se comprueba después), `missing` (`origin_check` strict: retenido), `missing:heuristic`), `transcript_origin` (person, harness, o null), `verified` (null mientras hay una comprobación pendiente); la comprobación misma es otro evento `trigger` con `stage` verify, `verified` (true, false, o null cuando el turno terminó sin entrada), `hook` (tool, stop), `undone` (offer_restored, edit_offer_restored, model_told) y `saved_meanwhile`, `project`, `request_chars`, `request_sha`, `injected_total` (lo que el camino le pasó al modelo: guardar, ajustar y galería; un pedido de compartir se cuenta en su evento de ruteo) |
| `context` | empieza una sesión | `hook` (session_start), `project`, `injected_total` (todo lo que el hook le pasó al modelo), `injected_parts` (`index`, `journal`, `guide`, `offer`, `audit_hint`, `review`), `index_cap` |
| `piece_opened` | el hook de herramienta ve que el agente corre `athos show <id>` | `task_id`, `piece`, `projects` (en un repositorio público solo este proyecto, nunca el nombre de otro), `via` (show), `offered` (el índice frontier de este pedido la listaba), `again` (ya estaba en uso para la tarea), `project` |
| `hook_error` | un hook se traga una excepción para que tu sesión siga | `hook`, `where`, `error` (el tipo de la excepción), `line` (archivo y línea dentro de Athos), nunca su mensaje; lo que el hook imprime en stderr es el mismo tipo y lugar, tampoco nunca el mensaje (puede citar un pedido o una ruta) |
| `learn` | el aprendizaje autónomo decide sobre una tarea: le pide al modelo que guarde lo que enseñó, guarda, o la saltea (cada decisión, con su razón) | `task_id`, `decision` (asked, saved, skipped), `reason` (strong_evidence, no_strong_evidence, last_verification_failed, correction_after_success, apply_model, model_unknown, model_guessed (un modelo frontier que hasta ahora solo se supone, no se vio), private_data, set_aside, duplicate, no_project, off, invalid, model_saved_nothing), `model`, `tier`, `work_mode`, `mode` (learn, apply, unknown), `project`, `strong`, `weak`, `positive`, `negative` (la evidencia de la tarea, contada), `evidence` (su resumen corto), `grounds`, y para un guardado `piece`, `version`, `risk`, `checks` (líneas Check ejecutables), `confidence`; para un rechazo por datos privados `private` (los tipos encontrados, nunca el texto); para un rechazo `duplicate`, o un guardado junto a una pieza tuya, `overlaps` (los ids) y `score`; `caught_up` cuando lo registró un inicio de sesión posterior |
| `ui` | reservado para el estado del panel | todavía no se escribe |
| `memory_cycle` | cada fase de un ciclo de sueño (ver «Memoria de largo plazo») | `run_id`, `phase`, `duration_ms`, las cuentas de la fase, para la pasada del modelo `wrote` |

Todos llevan además `at`, `session_id` y `v`, la versión de Athos que lo escribió. `candidates.reason` dice por qué una
pieza cargó o no: `chosen`, `runner_up_too_weak`, `over_budget`, `beyond_top_k`, `below_min_score`,
`prefixes_only`, `head_share_low`, `request_share_low`, `no_head_match`, `dismissed` o `meaning`; `scope_reason` es el
modo guardado (`all`, `project`, `pieces`, `none`) o, en `auto`, `auto:project`, `auto:project+named`,
`auto:no-own-pieces` (un proyecto sin páginas propias: solo el perfil), `auto:no-own-pieces+named` o
`auto:no-folder`. Los eventos escritos por 0.1.110 pueden decir `auto:project-without-pieces`: esa carpeta entonces veía
todas las páginas.

**Quién escribió un pedido.** Guardar, ajustar, galería y compartir actúan solo sobre texto que escribió la persona.
Deciden dos señales: los envoltorios que el harness pone alrededor de su propio texto (el informe de un subagente, una
notificación), y, cuando el hook da una ruta de transcript, la entrada del transcript para ese pedido (`promptId`, o, sin
él, el mismo texto; `origin.kind` human, o un botón del propio Athos que apretó la persona, es la persona). Cuando están
las dos tienen que coincidir. Claude Code escribe esa entrada recién después de que corrió el hook de pedido, así que al
momento del pedido suele faltar: entonces el camino actúa solo según los envoltorios y la entrada se comprueba en el
siguiente hook de herramienta, o al final del turno (desde 0.1.120; de 0.1.112 a 0.1.119 una entrada faltante quería
decir que el camino no actuaba, así que [Guardar] y un `Athos · adjust` escrito a mano nunca actuaban en Claude
Code). Si la entrada dice que lo escribió el harness, Athos deshace lo que puede: la oferta de [Guardar] vuelve, la
edición que ofreció la banda vuelve, y, en un hook de herramienta, se le dice al modelo que descarte la instrucción; un
guardado que ya ocurrió se cuenta, no se deshace (`athos revert` devuelve una pieza a como estaba). El evento `trigger`
de esa comprobación tiene `stage` verify, `verified` false y lo que se deshizo, y `athos audit` lo señala.
`"origin_check"` en `~/.athos/config.json` elige otra forma: `"strict"` no actúa mientras falta la entrada,
`"heuristic"` actúa según los envoltorios y nunca comprueba. Los agentes que no dan ruta de transcript (Codex, Muse
Code, OpenCode) se juzgan por los envoltorios, como antes.

`~/.athos/log.md` dice lo mismo en una línea por operación, para que una persona o un agente lo lea con grep y tail:

```
grep '^## \[' ~/.athos/log.md | tail
## [2026-11-15 09:21] route | my-app | loaded release-checklist · 1853 chars · scope auto:project
## [2026-11-15 09:24] route | my-app | none · scope auto:project
## [2026-11-15 09:30] trigger | my-app | share · harness text <agent-message> (heuristic) · ignored
```

Las horas están en UTC. Nombra una pieza solo cuando la pieza pertenece a ese proyecto, o a ninguno y no es privada (las
de otro proyecto solo se cuentan), y se mueve a `log.1.md` cuando pasa los 256 KB (bajo un lock, así dos hooks nunca lo rotan dos veces), así que se guardan como mucho dos archivos. Cada sesión empieza con
una línea oculta que le dice al agente dónde está el registro y que `athos audit --session <id>` lo resume.

`athos audit [--session <id> | --project <name> | --last N] [--show] [--json]` agrupa el registro por sesión y compara
cada una con estas reglas. Por defecto lee la última sesión que trabajó en la carpeta donde lo corrés o en cualquier
lugar dentro de su repositorio (los hooks anotan la carpeta de cada sesión), nunca la sesión de la terminal donde corre
(un agente que audita el trabajo de otra sesión desde su propia terminal leería la suya) ni la más grande o la más vieja
del proyecto; si no hay ninguna así, la última de este proyecto, y si no la última en cualquier lado:

| regla | señala |
|---|---|
| `other_project_load` | una pieza de otro proyecto cargada (elegida, traída por traspaso de una página cargada, o abierta por el modelo) u ofrecida en el índice de un modelo frontier, sin que el pedido nombrara ese proyecto; una pieza del perfil nunca es de otro proyecto, tenga las etiquetas que tenga |
| `load_without_own_pieces` | una pieza cargada en un proyecto que no tiene piezas propias (desde 0.1.111 un proyecto así ve el perfil, así que solo se señala una pieza de otro proyecto que no nombró) |
| `edit_without_basis` | una edición atribuida a la persona sin evidencia de que la hizo la persona |
| `model_inconsistent` | un pedido registrado bajo un modelo distinto del que dio las respuestas que lo contestaron (un cambio con `/model` registrado en los pedidos posteriores no se señala; un pedido decidido sobre una suposición o sobre unknown se juzga por el modelo observado después en la misma tarea, y se señala solo cuando ese, o la suposición nunca corregida, difiere de las respuestas); para sesiones anteriores a 0.1.113, los modelos de la sesión no coinciden entre sí o con el transcript de Claude Code. También informa `decided_on_guess` (pedidos decididos sobre una suposición o sobre unknown) y `guess_wrong_tier` (aquellos cuyo modelo observado era del otro nivel) |
| `injected_over_cap` | más caracteres pasados al modelo con un pedido que el tope del router: desde 0.1.114 todo lo que agrega el hook de pedido (`injected_total`), no solo el texto del router, así cuenta un aviso de edición, un pedido de compartir o una calificación encima de una página; los eventos de ruteo más viejos se juzgan por `injected_chars` y la regla dice partial |
| `trigger_not_from_person` | guardar, ajustar, galería o compartir se dispararon con texto que la persona no escribió (un camino que se retuvo, `acted` false, no se señala), o actuaron sobre texto que parecía de la persona y que el transcript después atribuyó al harness (se señala aunque se haya deshecho) |
| `version_mismatch` | los eventos de la sesión escritos por dos versiones, o el plugin de Claude Code y el `athos` de tu PATH difieren ahora. Cada hallazgo dice lo que cuesta: un Athos más viejo que reescribe una pieza descarta las líneas del frontmatter que no conoce (`visibility`, `status`, `risk`, `confidence`, `evidence`), así una pieza privada vuelve a ser visible; nada del lado más viejo puede evitarlo. Una vez que el ciclo de sueño archivó el registro, también se señala un evento o un agente instalado más viejo que el `oldest_reader` del archivo (0.1.180, en `memory/archive/manifest.json`; un manifiesto que dice 0.1.166 se lee como 0.1.180): un Athos así lee solo la ventana viva, así que su report, su export y sus benches dejan afuera el historial archivado sin decirlo, su hook Stop puede volver a arrancar el verificador (una corrida paga) para una versión cuyo veredicto está archivado, sus reglas de calificación no ven ninguno de los resultados archivados (ni retira lo que retiraría el historial entero ni verifica una candidata cuya aprobación está archivada), y sus importadores pueden volver a importar una sesión de Codex o Muse cuyas tareas se archivaron (mismos ids de tarea: los comandos offline las cuentan una vez; los hooks las dejan afuera y piden un ciclo, después del cual las cuentan una vez). Un Athos más viejo que solo lee o importa no deja ninguna versión en sus líneas: sus importaciones se señalan por sus ids de tarea, un `task_start` vivo para una tarea que el archivo ya tiene. Nunca reescribe ni borra el registro ni el archivo. |
| `private_piece_named` | una página privada (la `visibility` de hoy; en un repositorio marcado como público, toda página que no puede cargar ahí) elegida, traída por traspaso, ofrecida o puntuada en un evento de ruteo de una sesión fuera de sus proyectos, o nombrada, como id entero, en las líneas de `log.md` de este proyecto escritas mientras corría la sesión; sin eventos de ruteo para la sesión dice `not_evaluated` (no se comprobó nada), y un resultado limpio cubre solo lo que escribió Athos, no las respuestas del agente |
| `weak_evidence_learning` | una pieza guardada por el aprendizaje autónomo sin ningún ítem de evidencia fuerte (un código de salida o un artefacto que vieron los hooks): solo la opinión del modelo |
| `save_in_apply_mode` | una pieza guardada en un modelo apply: un guardado autónomo en un modelo que no es frontier, o, en sesiones escritas por 0.1.124 o posterior, una tarea respondida por un modelo apply que guardó una pieza (sesiones más viejas: solo se juzgan los guardados autónomos, partial) |
| `promotion_without_verifier` | una pieza del proyecto de la sesión que pasó a verificada sin un veredicto aprobatorio previo del verificador independiente cuyo prompt llevaba solo rutas |
| `verifier_saw_summary` | una corrida del verificador del proyecto de la sesión cuyo `paths_only` o `bundle_clean` registrado es false, cuyas entradas no fueron exactamente el conjunto fijo (las siete entradas de abajo; o las seis de una corrida registrada antes de 0.1.167, o los cuatro archivos de una registrada antes de 0.1.166), cuyo paquete tiene cualquier otra entrada, o cuyo `prompt.txt` guardado no es el texto fijo con las rutas de entrada del propio paquete |
| `candidate_set_aside` | una candidata de este proyecto que el verificador rechazó 3 versiones seguidas, todavía candidata y todavía marcada: el modelo ya no la reescribe, y solo vos podés arreglarla, conservarla o retirarla |
| `overlapping_pieces` | dos piezas de este proyecto para la misma forma de trabajar (puntaje a nivel de página de 0.5 o más), al menos una aprendida por Athos, o una pieza aprendida guardada junto a una tuya (marcada al guardar): vos decidís cuál conservar; no se fusiona ni se cambia nada. Una candidata que la fusión del ciclo de sueño hizo con esas mismas piezas (`dream:merge` y `from:` en su evidencia) es una propuesta que espera al verificador, no un accidente: se deja afuera y se cuenta en el fundamento; una vez aceptada, el hallazgo dice que retires las piezas de las que vino |
| `verifier_over_cap` | un día UTC cuyas corridas de modelo (verificador y repetición, de todos los proyectos) superaron el tope de corridas o de costo que registraron (una corrida sin costo informado cuenta su estimación) |
| `marker_name_ignored` | el repositorio donde corre la auditoría tiene un `.athos.toml` cuyo `name` no es el de la propia carpeta y nunca se aceptó en esta máquina (`athos public name`), así que Athos usa el nombre de la carpeta |
| `public_not_declared` | el repositorio donde corre la auditoría (cuando es el proyecto de la sesión) está subido a un sitio de alojamiento de código, según su configuración local de git, y su `.athos.toml` no dice si es público; `athos public` o `athos public off` lo responde |
| `memory_rollup_mismatch` | el ledger o los rollups que leen los hooks difieren de una agrupación del archivo entero y el registro vivo (`athos memory rebuild` los vuelve a armar) |
| `memory_archive_integrity` | un segmento archivado falta, no se puede leer, o no son los bytes y el sha256 que registró su manifiesto (un comando offline igual lo lee tal como está, y lo dice) |
| `memory_wrote_legacy` | el ciclo de sueño informó que escribió en una pieza sin estado, o una pieza así tiene una versión escrita por el sueño (`athos-dream` en su historial) |
| `memory_model_over_cap` | una pasada del modelo del ciclo de sueño que se liquidó sin una reserva previa, o en un día por encima del tope compartido con el verificador |

Cada regla dice cómo se juzgó: flagged, clean, partial (comprobada con datos más viejos, lo que no es una prueba) o
not evaluated (con lo que falta). Las sesiones registradas antes de estos eventos se
comprueban hasta donde permiten sus líneas de tarea: las piezas que usó cada tarea y los primeros 120 caracteres de su
pedido, las piezas tal como están etiquetadas hoy, y, para el modelo, las respuestas en el transcript de Claude Code
cuando todavía está en tu máquina. Solo lee; los pedidos nunca se muestran, y las piezas de otro proyecto se nombran
solo con `--show`.

### Qué modelo respondió, y los niveles de modelos

El modelo se resuelve en cada pedido, no una vez por sesión, en este orden de confianza:

1. El campo propio del hook, cuando el agente lo manda (Codex en cada evento; Claude Code solo en el SessionStart de una
   sesión interactiva).
2. La conversación principal en el transcript de Claude Code: entre un cambio con `/model` (cuenta solo la salida que
   Claude Code escribe justo después de un comando `/model`, nunca las mismas palabras en tu propio mensaje), el último
   pedido que mandó (la fila `api-request`, con `params.model`, escrita antes de cualquier respuesta) y la última
   respuesta, el más nuevo. Nunca el modelo asesor que Claude Code nombra en cada respuesta (`advisorModel`), y nunca el
   de un subagente: sus pedidos viven en su propio archivo, y no se toma una fila de pedido de ningún origen que no sea
   la conversación principal (`sdk` headless, `repl_main_thread` interactiva). El modelo que la sesión informó al
   empezar gana cuando se informó más tarde (una sesión retomada en otro modelo).
3. El último modelo observado de la sesión.
4. Una suposición, solo en Claude Code: el `--model` con el que se lanzó (leído de su línea de comandos, `launch_flag`),
   después `ANTHROPIC_MODEL` (`env`), después el `model` del `.claude/settings.local.json` del proyecto, del
   `.claude/settings.json` del proyecto y de tu `settings.json` en `~/.claude` o `CLAUDE_CONFIG_DIR` (`settings`; un
   cambio con `/model` también guarda ahí su elección). Un alias como `opus` tiene el nivel de la familia que nombra.
5. `unknown`, que cuenta como modelo apply.

El SessionStart headless de Claude Code y cada UserPromptSubmit no traen modelo, y en el primer prompt de una sesión el
transcript todavía no existe, así que el primer pedido de una corrida `claude -p` se decide con una suposición o con
unknown. La primera observación lo reemplaza: en la primera llamada a herramienta del turno (su PreToolUse, donde la
fila del pedido ya está escrita), al guardar, o al final de un turno sin herramientas (cuyo Stop ve la fila del pedido,
mientras todavía no existe ninguna fila de respuesta). Un evento `model` registra la observación con lo que `corrects`;
el `task_end` de la tarea, la evidencia y la contabilidad de reuso usan el modelo observado (`model_at_start` guarda
con qué se decidió el pedido).

**Qué puede decidir una suposición, y cuándo se permite guardar.** Una suposición elige cómo se entrega el know-how (un
índice o las piezas) y qué guía recibe la sesión. Guardar, o cualquier cambio a una pieza que inicie el modelo, se
permite solo una vez que el modelo fue observado (el campo del hook, el transcript o las respuestas) y es frontier; con
una suposición se rechaza (`model_guessed`), y el rechazo se comprueba primero contra el transcript, así que la propia
llamada a herramienta del guardado alcanza para observar el modelo. Unknown queda como apply: no se guarda, y las piezas
se entregan solo como las recibe un modelo apply (piezas verificadas y legacy). Cuando la sesión resulta estar en un
modelo frontier y su inicio retuvo la guía autónoma (o dio la de guardado de la persona), la guía llega una vez, fuera
de tu vista: en el contexto de esa primera llamada a herramienta (PostToolUse) o del pedido siguiente. Cuando una
sesión que recibió la guía con un modelo frontier supuesto resulta estar en un modelo apply, al modelo se le dice una
vez, fuera de la vista, que la guía no aplica, y no se guarda ni se pide nada. `athos status --json` tiene `model`
(`id`, `source`, `observed`, `tier`, `work_mode`, `collaborates`).

Cada modelo tiene un nivel. Los modelos **frontier** pueden aprender formas de trabajar nuevas (modo `learn`); los
modelos **apply** usan lo que ya se sabe (modo `collaborate`), y una sesión frontier también colabora cuando se cargó
una pieza para el pedido. Un modelo que no coincide con ningún patrón cuenta como apply. Desde 0.1.116 el nivel decide
cómo se entrega la elección del router (ver «Pedir en vez de empujar» más abajo), y desde 0.1.124 qué se guarda: solo un modelo frontier aprende (ver «Aprendizaje autónomo»), y en un modelo apply `athos save` se niega y nunca se ofrece ni se pide guardar.

```
athos tiers [--json]                              the patterns of each tier
athos tiers add frontier|apply <pattern>...       e.g. 'local-big-*', or an exact id, which wins over any pattern
athos tiers remove frontier|apply <pattern>...
athos tiers reset                                 back to the defaults
athos tiers which <model>...                      the tier and mode of a model id
```

Valores por defecto: frontier `claude-fable-*`, `claude-mythos-*`, `claude-opus-*`; apply `claude-sonnet-*`,
`claude-haiku-*`. Se guardan en `~/.athos/config.json` bajo `tiers`, y se comparan sin distinguir mayúsculas y sin
tener en cuenta un sufijo de tamaño de contexto como `[1m]`.

### Aprender de tus propias ediciones

Cuando el agente escribe o edita un archivo de texto siguiendo una de tus piezas (una revisión de contrato, un informe,
código) y después vos cambiás ese archivo a mano, tu cambio suele ser una regla de cómo trabajás. Athos guarda una
copia de cada archivo tal como lo dejó el agente (`~/.athos/snapshots/<session>/`, archivos de texto de hasta 200 KB,
solo las últimas tres tareas de la sesión), también de los archivos dentro del proyecto que nombra un comando de shell
del agente.

Un cambio cuenta como tuyo solo con evidencia de que no lo hizo ninguna llamada a herramienta del agente, y en la duda
no se le atribuye a nadie. El agente cambia archivos de muchas maneras además de sus herramientas de edición (un
script, `sed -i`, un formateador, `git checkout`, un paso de build, el hook de otro plugin, un subagente, una tarea que
dejó corriendo en segundo plano); hasta 0.1.111 cada una se tomaba como edición tuya. Ahora:

- el inicio de cada llamada a herramienta lo sella un hook PreToolUse (el reloj del propio hook, no una estimación).
  Después de cada llamada a herramienta del agente (en Claude Code también una fallida, `PostToolUseFailure`) se revisa
  cada archivo guardado, primero con un `stat` y su contenido solo cuando eso se movió. Un cambio que pudo haber pasado
  durante la llamada es del agente, y la copia pasa a ese cambio. Un cambio es tuyo solo cuando su hora (el ctime del
  archivo, que ninguna herramienta puede atrasar) cae más de un segundo antes del inicio sellado de la llamada, más de
  15 segundos después de que terminó la llamada a herramienta anterior (un formateador que corre otro plugin después
  de una escritura), y mientras no corría ninguna otra llamada a herramienta, ningún subagente ni ninguna tarea en
  segundo plano;
- en tu pedido siguiente, un cambio es tuyo solo cuando llegó más de 15 segundos después de que terminó el turno del
  agente (otro hook Stop puede estar escribiendo todavía), sin ninguna llamada a herramienta desde entonces ni abierta
  todavía, sin tareas en segundo plano corriendo, y sin que otra sesión de agente haya trabajado en el mismo proyecto
  desde entonces;
- cualquier otra cosa no se le atribuye a nadie: sin sello de inicio, la llamada de un subagente (el `agent_id` de
  Claude Code), una llamada o tarea todavía corriendo, un cambio dentro de una ventana de gracia, un ctime en el futuro
  (el reloj de un sistema de archivos en red). El evento `edit_seen` dice `agent_shell`, `agent_tool` o `unexplained`
  con el motivo, y al agente no se le dice nada.

Un cambio tuyo se acredita al paso en el que estaba el agente cuando escribió el archivo; si no, a la pieza mejor
rankeada que cargó el pedido; si no, a ninguna pieza (y entonces al agente no se le dice). El agente recibe un diff
corto y se le pide que proponga la regla en una línea, en tu idioma, y que te pregunte antes de agregarla. Decí que sí y
mejora la pieza igual que [Adjust]; un cambio de tipeo o de espacios no se menciona. Cada edición se ofrece una vez y
su copia se borra enseguida; `athos status --json` la muestra como `learned_from_edit` (archivo, pieza, paso y el texto
`Athos · adjust <piece>#<step>:` que un panel puede precargar). Los paneles la ofrecen como un botón, **Keep this rule**
(`Guardar la regla de …`) (el pane de Claude Code, el panel de Desktop, la paleta de OpenCode: *Athos: guardar la regla
de mi edición*); en Codex y Muse Code, `athos watch --trail` muestra la edición y un simple «sí» al agente la guarda.
El evento `learned_from_edit` guarda la ruta del archivo, la pieza y su título, y la evidencia (`basis`); en un
repositorio marcado como público (`.athos.toml`) guarda solo hashes de la ruta, la pieza y el paso. Funciona en Claude
Code, Codex (`apply_patch`), Muse Code y OpenCode, queda en tu máquina, y se apaga con `ATHOS_CAPTURE=off`.

Lo que no puede ver: un proceso que el agente dejó corriendo y que escribe después del turno y después de la ventana de
gracia, cuando el hook Stop del agente no informa ninguna tarea en segundo plano (`background_tasks` de Claude Code), se
toma como tuyo; un cambio hecho mientras el agente escribe su última respuesta (después de su última llamada a
herramienta) no se le atribuye a nadie; una edición a mano seguida por la propia herramienta de edición del agente en el
mismo archivo, sin otra llamada a herramienta en el medio, queda incluida en la escritura del agente; una edición a mano
dentro de los 15 segundos de una llamada a herramienta o del final de un turno no se le atribuye a nadie; los agentes
sin hook PreToolUse (Codex, OpenCode) solo tienen la evidencia de después del turno. Revisar los archivos guardados
cuesta bastante menos de un milisegundo por llamada a herramienta con veinte archivos guardados; el sello de
PreToolUse es la escritura de un archivo chico.

### Aprendizaje autónomo: candidatas, comprobaciones y un verificador

En un modelo frontier Athos puede aprender solo, y solo una pieza probada con evidencia objetiva llega a un modelo
apply.

**Estado y procedencia.** El frontmatter de una página puede llevar, después de `visibility`, cada línea solo cuando
tiene valor:

| campo | valores |
|---|---|
| `status` | `candidate` (aprendida, todavía no probada), `verified` (probada: ver más abajo), `retired` (reemplazada después de fallas repetidas; nunca se carga) |
| `risk` | `normal` o `high` (sus pasos publican, hacen merge, despliegan, borran, hacen force-push o tocan producción) |
| `learned_by` | el modelo que la escribió |

Los números cambiantes de una página aprendida se guardan al lado de su archivo, nunca adentro: `confidence` (un número
de 0 a 1), `last_verified` (la fecha en que se probó por última vez) y `evidence` (una lista corta de ítems
`kind:detail`, p. ej. `verify:unittest:ok, commit, task:3f9a1c2b7d10, verifier:pass`), en `~/.athos/piece-meta.json`.
Cambian con cada veredicto y cada reuso calificado: un archivo que los tomaba en su último cambio de estado mostraba un
número viejo hasta el siguiente (una prueba en vivo leyó 0.05 en el archivo mientras la confianza real era 0.25), y
escribirlos en cada reuso reescribiría el archivo en cada uso, ruido en una carpeta de know-how sincronizada o bajo
control de versiones. `athos show <id>` imprime la página con sus números reales, y `athos report` agrega a su línea su
estado, su confianza y, cuando ya hay, sus reusos calificados (`graded reuses 2 clean of 2`: los reusos que la
calificación juzgó con evidencia objetiva, al lado de las tareas que marcaste). Un inicio de sesión saca los números
de cualquier página aprendida cuyo archivo todavía los tenga (escritos por una versión anterior), una vez, sin una
versión nueva. El costo: una carpeta de know-how copiada a otra máquina sin `~/.athos` lleva el estado de una página
aprendida pero no su confianza (ahí cuenta como 0.5 hasta que se la vuelva a calificar; la confianza solo desempata
casos parejos en el router).

Una página sin `status` (toda página escrita antes de 0.1.122, y cualquier página que escribas vos) es **legacy**: se
carga, se ofrece y se entrega exactamente como una verificada. Su archivo es tuyo: Athos nunca lo reescribe salvo que
pidas un cambio a esa página (`athos save` con su `id:`, `athos revert`, un curate o un merge que apliques). Usarla,
calificarla, envejecerla y la contabilidad (confianza, evidencia) la dejan byte por byte como está, incluidos los
comentarios y las claves que Athos no conoce; lo que habrían registrado va al registro de auditoría (un evento `grade`,
de legacy a legacy, con lo que se vio), a las marcas de revisión (el índice del próximo modelo frontier dice que
necesita revisión) y, para su último uso, a `~/.athos/last-used.json`. El archivo de una página aprendida tampoco se
reescribe al usarla o calificarla: su último uso va a `last-used.json` y sus números cambiantes a
`~/.athos/piece-meta.json` (arriba), y el archivo toma su último uso con su próximo cambio de estado o mejora. Un
cambio de estado es una versión nueva, con la saliente archivada en `.history` como en cualquier mejora, así que
`athos revert <id>` la trae de vuelta; retirar reemplaza una página y no borra nada.

**Verificada quiere decir verificada para ese texto.** Un cambio en el título, el when o el cuerpo de una página
verificada, lo haga quien lo haga, la vuelve `candidate` (su historial lo dice), y el veredicto de un verificador cuenta
solo para el texto exacto que leyó. `athos revert` a una versión que estaba verificada la trae de vuelta verificada
solo cuando el verificador aprobó ese mismo texto; si no, vuelve como candidata.

**Las líneas Check.** Un enunciado puede decir cómo saber que su paso salió bien, junto a When, Do, Because y Links:

```
## #run_tests
**When:** after changing the parser.
**Do:** run the unit tests.
**Check:** `python3 -m unittest discover -s tests` exits 0
```

Un Check es un comando entre backticks, o un hecho que cualquiera puede observar. Un modelo apply corre la comprobación
en vez de juzgar su propio trabajo, y una candidata necesita al menos un Check ejecutable antes de poder verificarse:
un comando entre backticks que sea en sí una verificación (un runner de tests, un build, un linter, un type checker,
como en la tabla de abajo). Un Check de `git status` o `cat VERSION` solo lee algo: no es ejecutable, y correrlo no es
evidencia. La guía de captura pide uno por paso; una página dada solo con sus pasos, para entrar en el tope de 8000
caracteres, conserva el Check de cada paso con su When y su Do.

**Evidencia, reunida sin preguntar.** Durante cada tarea los hooks anotan lo que pasó objetivamente, en
`~/.athos/evidence/<task>.jsonl` (las últimas 300 tareas), y guardan al lado los últimos 4000 caracteres de la salida
de cada comando de verificación, para el verificador:

| ítem | se escribe cuando | fuerza |
|---|---|---|
| `verify` | termina un comando de verificación: un runner de tests (pytest, `python -m unittest`, `npm test`, `npm run test:*`, `go test`, `cargo test`, `make test`/`check`, jest, vitest, …), un build (`npm run build`, `cargo build`, `go build`, `tsc`, …), un linter (`ruff check`, eslint, flake8, `black --check`, …), un type checker (mypy, pyright, `tsc --noEmit`, `go vet`, `cargo check`), un script de comprobación propio del proyecto (`npm run validate`, `npm run verify`, `npm run check`, y lo mismo bajo pnpm, yarn y bun), o el **Check** de una pieza que usa la tarea; con `ok`, `kind`, `label`, `check_of` y, cuando es fuerte, la `rule` que lo hizo fuerte | fuerte cuando el hook vio el propio estado de salida de ese comando, o el resumen propio de su runner (abajo) |
| `commit` | HEAD se movió durante un comando de shell, a un commit hecho durante ese comando (horas de autor y de committer iguales o posteriores al inicio del comando), fuera cual fuera el texto del comando: un mensaje en heredoc, `git commit -F -`, un alias, un script que hace commit; un ítem por cada commit así (`sha`, `basis: head_moved`, `amend` para un amend) | fuerte (débil cuando un subagente estaba trabajando al mismo tiempo) |
| `revert` | HEAD retrocedió en la misma rama (commits descartados, ninguno agregado: `git reset --hard HEAD~1`; `basis: head_moved_back`), o salió bien `git revert`, `git reset --hard`, `git checkout -- …` o `git restore` (`basis: command`; no `git revert --abort` ni `--quit`, ni `git reset --hard` sobre `origin/…`, `upstream/…` o `@{u}`, ni `git restore --staged` solo) | fuerte, en contra del trabajo |
| `rewrite` | HEAD se movió de costado en la misma rama (commits descartados y otros agregados: un rebase, un reset sobre otro commit) | fuerte, ni a favor ni en contra: no es un commit |
| `person_edit` | el detector de ediciones te atribuyó un cambio a vos (ver arriba): una corrección | fuerte, en contra del trabajo |
| `reaction` | tus palabras siguientes juzgaron claramente la tarea (`ok`, `corrected`) | débil: leído de palabras |
| `model_claim` | la propia afirmación del modelo sobre su trabajo | débil |

**Cómo se lee un comando.** Los hooks leen un comando de shell como la shell decidiría qué se ejecuta: comillas,
escapes con barra invertida y continuaciones de línea, comentarios `#`, `$( … )` y backquotes (se mantienen dentro de
su palabra, nunca se leen como comandos), heredocs (`<<EOF`, `<<'EOF'`, `<<-EOF`, varios en una línea: el cuerpo son
datos, y el comando sigue después de la línea terminadora; un cuerpo sin terminador se lleva el resto), `&&`, `||`,
`|`, `;`, `&`, saltos de línea, y agrupaciones en `( … )` y `{ …; }` (el estado de un grupo es el de su último comando).
Un comando que corre `athos` igual se lee; `athos` en sí no verifica nada.

El estado de salida de un comando es el de una verificación, y el ítem es fuerte, por una de estas reglas (guardada
como `rule`):

| regla | cuándo | p. ej. |
|---|---|---|
| `alone` | el comando entero es esa verificación | `pytest -q` |
| `and_chain` | solo `&&` lo une a los comandos anteriores de su lista y a todo lo que viene después: el comando salió bien solo si ella salió bien | `cd app && npm test && git commit …` |
| `last_in_sequence` | es el último comando, después de un `;`, un salto de línea o el terminador de un heredoc: el estado es el del último comando | un heredoc que edita un archivo, y después `npm test` en la línea siguiente |
| `pipefail` | pasado por pipe solo a `tail`, `head` o `tee` cuando el propio comando activa pipefail primero, unido con `&&` | `set -o pipefail && pytest -q \| tail -5` |
| `runner_summary:<runner>` | (solo éxito) la llamada salió bien pero el estado no es el de la verificación, y su salida trae el resumen final propio de su runner en un formato que Athos lee exactamente, una vez: pytest (`4 passed in 0.12s`, con o sin barras `=`), `python -m unittest` (`Ran 4 tests in 0.1s` y después `OK`), jest (`Tests: 5 passed, 5 total`), vitest (`Tests  3 passed (3)`); el comando tiene que nombrar al runner en sí (`npm test` puede correr cualquier cosa), correrlo una vez, pasarlo por pipe (si lo hace) solo a `tail`, `head` o `tee`, no mandar su salida a un archivo, y no correr nada más que imprima texto elegido por él (`echo`, `printf`, `cat`, `sed`, …) | `pytest -q 2>&1 \| tail -5` imprimiendo `4 passed in 0.3s` |

Un resumen que cuenta una falla o un error es una falla fuerte por la misma regla, aunque `tail` haya salido bien. Un
resumen que no cuenta ningún test aprobado, dos resúmenes, o cualquier otra cosa ambigua deja el ítem débil; una
llamada fallida nunca se mejora por un resumen limpio. Todo lo demás es débil: `pytest | tail` sin pipefail ni resumen
informa el estado de `tail`, `pytest || true` siempre sale bien, y `npm test; ls` informa el de `ls`. Una falla cuenta
como de ese comando solo cuando es el último y antes de él en su lista hay solo preparación (`cd`, `export`, `source`)
o un `;` (regla `alone` o `last_command`); una cadena fallida con una verificación adentro cuya falla no se puede
atribuir a un solo comando (`pytest && npm run build`, `pytest 2>&1 | tail`) es igual un ítem fuerte en contra del
trabajo (`unattributed`), hasta que una verificación posterior pase. Fuerte se reserva para comandos que
realmente comprobaron algo: no son fuertes una corrida que solo le pregunta al runner sobre sí mismo o lista lo que
haría (`--version`, `--help`, `--collect-only`, `--no-run`, `make -n`), un linter al que se le dice que arregle
(`--fix`, `lint:fix`), las tareas que una corrida de gradle deja afuera (`-x test`), un comando mandado a segundo plano
(su hook llega cuando empieza, así que no se conoce su estado), cualquier cosa después de un comentario `#`, y una
corrida de tests cuya salida dice que no corrió ningún test (`Ran 0 tests`, `collected 0 items`, `[no
test files]`, `running 0 tests`, `No tests found`, `0 passing`). Una palabra más larga es otro comando:
`pytest-watch` no es pytest y `make test-clean` no es `make test`. El hook no dice cómo se inició la
shell, así que sin ese `set` (o un resumen del runner) un pipe queda débil, y una falla nunca se toma por un
éxito.

**Los commits se observan, no se leen.** Antes de cada comando de shell en un repositorio, el hook PreToolUse guarda
HEAD y su rama, leídos de los archivos de la carpeta git (sin proceso git; a git se le pregunta solo por un almacenamiento
de refs que los archivos no muestran); después del comando (PostToolUse o PostToolUseFailure) la misma lectura dice si
HEAD se movió, y solo cuando se movió un `git log` lista los commits del medio. Medido en esta máquina: unos 0.04 ms en
cada extremo cuando HEAD no se movió, sin proceso git; nada en absoluto fuera de un repositorio. Un movimiento hacia
adelante registra los commits hechos durante el comando; uno que solo llegó (un pull o merge fast-forward, un checkout
de otra rama) no es de la tarea; un amend es un commit; un movimiento hacia atrás en la misma rama es un `revert`, un
movimiento de costado un `rewrite`, nunca un commit; una rama nueva con un commit encima registra ese commit; un
repositorio todavía sin commits registra el primero. Los comandos propios de un subagente quedan afuera, y un commit
hecho mientras trabajaba un subagente se guarda como débil. Las palabras del comando ya no deciden nada sobre los
commits.

**Lo que queda invisible.** Una verificación dentro de un script que escribió el modelo o de un script del proyecto que
no es uno de los nombres de arriba (`./scripts/check.sh`, `node scripts/validate.mjs`), dentro de `sh -c '…'`, `eval`,
un heredoc pasado a una shell (`bash <<EOF`), un target de `make` que no sea `test`/`check`/`build`/`all`, o la
condición de un `if`/`while`; una verificación corrida en otro repositorio que no es la carpeta de la sesión (`cd
../other && git commit`); un commit hecho fuera de la shell del agente (en tu propia terminal mientras corría el
comando se tomaría como del agente); y los comandos de agentes cuyos hooks no dan estado de salida ni sello de
PreToolUse. La guía autónoma le pide al modelo que corra cada comando de verificación una vez, solo, antes de terminar.
Se guardan hasta 60 ítems débiles por tarea; los fuertes nunca se descartan. Claude Code corre PostToolUse después de un
comando que salió con 0 y PostToolUseFailure después de uno que no; los agentes cuyos hooks de herramientas no dan estado
de salida (Codex, Muse Code y OpenCode salvo que el evento traiga un código de salida) solo producen ítems débiles. Los
comandos de los subagentes quedan afuera, los de Athos no verifican nada, y en un repositorio marcado como público no se guarda el comando en sí, solo de qué tipo era. Con
el aprendizaje autónomo activado (abajo), y siempre en un modelo apply, una edición tuya es solo evidencia: al agente ya
no se le avisa ni se le pide que proponga una regla.

**Guardar solo, en un modelo frontier.** Cuando una tarea en un modelo frontier termina con motivos para guardarla (la
misma regla que antes preguntaba: una edición dentro de tres llamadas a herramienta, cinco comandos que cambiaron algo,
o una checklist seguida, y nada guardado todavía), Athos mira su evidencia. Al menos un ítem fuerte a favor del trabajo
(una verificación que pasó, un commit), ninguna verificación fallida como última, y ningún revert ni edición tuya
después del último éxito.

Cómo se entera el modelo lo decide `autolearn.ask` en `~/.athos/config.json`:

- `"guide"` (el valor por defecto): no se dice nada al final de la tarea. La guía de la sesión (oculta, al inicio de la
  sesión, y de nuevo, una vez, en la primera llamada a herramienta o pedido después de que el modelo resulta ser
  frontier) le dice una vez a un modelo frontier: antes de su respuesta final a una tarea cuyo trabajo probó una
  comprobación objetiva en esta sesión, si la tarea enseñó algo reusable, que lo guarde con `athos save --auto`; si no,
  que no haga nada y no mencione Athos. El hook Stop solo registra la tarea como `qualified`.
- `"stop"`: el hook Stop además le dice una línea corta al modelo cuando una tarea califica, que vos también ves (Claude
  Code la muestra como "Stop hook feedback"; el cuadradito queda rojo mientras el modelo la responde):

```
Athos: if this task taught something reusable, keep it as one piece with Check lines (`athos save --auto`, as the session guide says); otherwise just stop.
```

La contrapartida: la línea llega en el momento en que termina la tarea, con la evidencia fresca, así que un modelo actúa
sobre ella de forma más confiable que sobre una instrucción leída al principio de una sesión larga, que puede olvidar o
sopesar contra tu pedido; pero vos la leés después de cada tarea que califica. Con `guide`, comprobá que los guardados
sigan pasando: `athos audit` imprime, por sesión, `learning on its own: N saved · M task(s) qualified without a save
before the end · K ended with nothing saved` (y cuántas tareas que calificaron corrieron sin la guía de la sesión); si
las tareas que califican siguen terminando sin nada guardado, mientras los guardados siguen en cero, el modelo no está
actuando según la guía, y `"ask": "stop"` trae de vuelta la línea.

La guía dice cómo: una pieza, cada paso con un Check, solo lo que alguien podría comprobar en el repositorio (sus
archivos, su historial, lo que imprimen sus comandos; nada de tiempos ni otras observaciones circunstanciales), tus
preferencias escritas como reglas a seguir y no como cosas que dijiste, sin secretos, emails, links, carpetas de esta
computadora ni nombres de otros proyectos; cuando la tarea siguió una pieza de Athos, nada si no enseñó nada que a esa
pieza le falte, esa misma pieza mejorada (con su `id:`) si lo que enseñó le corresponde y es una aprendida, y una pieza
nueva solo para una forma de trabajar distinta. `athos save --auto` después la guarda sin preguntarte, como `candidate`
solo del proyecto actual (`visibility: project`), con `learned_by`, el resumen de la evidencia, `confidence: 0.3` y el
riesgo que encuentra el detector, después de dos comprobaciones: la evidencia de la tarea tiene que seguir calificando,
y el detector de datos privados de `athos share` no tiene que encontrar nada (emails, números de teléfono y de
documento, links, carpetas de esta computadora, el nombre de otro proyecto, tu nombre); si encuentra algo, la pieza no
se guarda y al modelo se le dice de qué tipos, nunca el texto. **Una forma de trabajar, una pieza**: antes de crear una
candidata nueva, se la compara, página por página, con las piezas del proyecto y con las que abrió la tarea (la
proporción de palabras que sus títulos y sus líneas **When** tienen en común, en las propias palabras del router, más
0.2 cuando las dos nombran el mismo archivo y 0.2 cuando la página nueva enlaza a la otra). Con 0.5 o más contra una
pieza aprendida de este proyecto (0.4 contra una pieza que la tarea abrió y siguió), el guardado se rechaza (`learn`
motivo `duplicate`, con `overlaps` y `score`) y el modelo lee: "not saved: this is the same way of working as `<id>`
("<title>"), a piece Athos learned in this project. Improve that piece instead of creating another: run `athos save
--auto` again with the whole piece rewritten (its steps and what this task added: a step, a Check, a case it did not
cover), with `id: <id>` and a `note:` saying what changed in its frontmatter. If this task taught nothing that piece
lacks, save nothing." Una pieza apartada no se esquiva: no se guarda nada en su lugar. Contra una pieza tuya, nada tuyo
cambia: la pieza nueva se guarda, su línea de historial dice cuál de las tuyas repite, una marca de revisión la muestra
en `athos report`, y `athos audit` la lista (regla `overlapping_pieces`, que también lista pares de piezas aprendidas
que ya están en el almacén; no se fusiona ni se borra nada). Los umbrales se calibraron con 18 pares casi duplicados
aprendidos en pruebas en vivo (puntaje más bajo 0.55) contra 1776 pares del mismo proyecto de piezas propias de una
persona, realmente distintas (la más alta 0.49; 2 de ellas llegan a 0.4). Nunca cambia tus propias
piezas (sin `status`) ni una retirada;
una pieza aprendida de este proyecto sí puede mejorarla, con las mismas comprobaciones, y la versión nueva es una
candidata con su propia corrida del verificador (una pieza verificada mejorada así se vuelve a verificar desde cero).
Una candidata no llega a un modelo apply hasta que se verifica. Cada decisión es un evento `learn`: calificada (`ask:
guide`), preguntada (`ask: stop`), guardada, u omitida con su motivo (sin evidencia fuerte, una última verificación
fallida, datos privados, un modelo apply, el modelo que se detiene sin guardar, `duplicate`, o `set_aside` más abajo).
Una tarea que calificó y terminó sin guardar se registra como `model_saved_nothing` en el pedido siguiente de la sesión
o, para una sesión que nunca mandó uno, en el siguiente inicio de sesión en el proyecto diez minutos o más después de
que terminó la tarea (`caught_up`).

**Una candidata rechazada vuelve como algo para arreglar.** Cuando el último veredicto del verificador sobre el texto
actual de una candidata es un fallo, y la candidata es una que Athos aprendió (tiene `status` y `learned_by`), a una
sesión frontier del propio proyecto de esa pieza se le avisa, fuera de tu vista, en dos lugares: su línea del índice
dice `candidate, not accepted by
the verifier: open it with `athos show <id>` and improve it if this task shows how`, y `athos show <id>`, cuando lo
corre la shell de un agente (con las variables propias de Claude Code, Codex, Muse Code u OpenCode) en una carpeta del
proyecto de la pieza durante una sesión que aprende sola, imprime después de la pieza:

```
Athos (for you, not the person): this piece, `<id>`, was not accepted. An independent verifier rejected its current
text (attempt <n> of 3), for these reasons:
- <criterion>: <the verifier's one-line reason>
If this task shows how to fix that, save an improved version of this same piece before your final answer: run
`athos save --auto` with the whole piece rewritten (title, when, every step with its **Check:**), adding `id: <id>`
and a `note:` that says what changed to its frontmatter. It stays a candidate and is checked again; nothing you write
about your work reaches the verifier. If this task does not show how, leave the piece as it is. Don't mention this to
the person.
```

Solo se listan los criterios que fallan. Nada de esto se te dice a vos en tu propia terminal, en otro proyecto, en un
repositorio marcado público para una pieza que no es de ese proyecto, ni a un modelo apply (que nunca recibe una
candidata). El único camino para mejorar una candidata es el guardado automático con el `id:` de la pieza
(`athos save --auto`, o un `athos save` común que corre el modelo, que va por el mismo lado): mismo id, una versión
nueva con una línea de historial, estado todavía `candidate` (una pieza verificada vuelve a candidata), un paquete
nuevo para el verificador, y el verificador arrancado bajo los mismos topes diarios; rechaza tus propias piezas (sin
`status`), las retiradas, las de otro proyecto y una tarea sin evidencia fuerte. **El ciclo tiene límite**: cuando el
verificador rechazó 3 textos de una pieza seguidos (cada texto cuenta una vez, y la cuenta vuelve a empezar después de
una aprobación), la pieza queda **apartada**: al modelo ya no se le avisa (su línea del índice dice
`set aside for the person: don't rewrite it`), el guardado automático se niega a cambiarla (razón de `learn`
`set_aside`), un evento `grade` registra por qué (`set_aside: the verifier rejected 3 versions in a row (last: …)`), y
una marca de revisión la pone en `athos report` (bajo el `review` de la pieza) y en `athos audit` (regla
`candidate_set_aside`) hasta que un texto pase o la edites o la retires. Un reuso hecho mientras el veredicto sobre ese
texto era un fallo nunca cuenta para la promoción, aunque el mismo texto pase después (el evento `reuse` guarda
`verdict`).

**Quién puede guardar.** Cada guardado o cambio de una pieza es tuyo o del modelo, y en la duda es del modelo:

- **tuyo**: apretaste [Guardar] (o [Cambiar este paso], [Guardar la regla]), o escribiste un pedido que empieza con
  `Athos · save:` o `Athos · adjust` (`Athos · ajustar`), y la comprobación de quién escribió el pedido lo lee como
  texto tuyo (los envoltorios del propio texto, y la entrada de la transcripción de Claude Code para ese pedido cuando
  está: si la transcripción dice que lo mandó el harness, el permiso se retira). El `athos save` que el modelo corre
  después en esa tarea, desde cualquier carpeta del proyecto, es tuyo: funciona en cualquier modelo y guarda una pieza
  tuya (sin `status`), como antes del aprendizaje autónomo. Dura hasta tu próximo pedido (30 minutos como mucho). Un
  `athos save` que corrés en tu propia terminal, donde ningún agente lo corre y ninguna sesión trabaja en esa carpeta
  ni más arriba, también es tuyo. Lo mismo el `athos_save` del modelo en el chat de Claude Desktop mientras
  `autolearn.chat` es `own` (el valor por defecto), porque lo elegiste vos.
- **del modelo**: todo lo demás. Un comando que corre un agente (la shell de Claude Code define `CLAUDECODE` y el id
  de la sesión, `CLAUDE_CODE_SESSION_ID`, que además dice qué sesión es cuando dos trabajan en una carpeta), un comando
  en una carpeta donde trabajó una sesión en los últimos 30 minutos (o en una carpeta de más arriba: una subcarpeta
  pertenece a la sesión del proyecto), el `athos save` de un subagente (su modelo no es el de la sesión), y todo
  `athos_save` a través de `athos mcp` (un servidor MCP no puede saber quién escribió el pedido).

Un guardado que arranca el modelo, con o sin `--auto`, pasa por el pipeline autónomo de arriba: en un modelo frontier
da una candidata, con evidencia fuerte, después de la comprobación de datos privados, y después el verificador; en un
modelo apply, o en uno que Athos no pudo resolver, no se guarda ni se cambia nada, desde ninguna carpeta, ni por la CLI
ni por MCP (`athos save`, `athos
revert`, `athos merge --apply`, `athos curate apply|restore`, `athos_save` y `athos_merge` con `apply`), y el rechazo
dice cómo podés guardarlo vos. Si un agente corre el comando y no se encuentra ninguna sesión, cuenta como un modelo que
Athos no pudo resolver. En el chat de Claude Desktop el modelo no se conoce; ahí decide el ajuste `autolearn.chat`:
`own` (el valor por defecto) guarda el `athos_save` del modelo como una pieza tuya (sin `status`), por elección tuya,
después de las comprobaciones de datos privados y de casi duplicados; `off` no guarda nada ahí. En los dos casos
`athos_merge` con `apply` se rechaza en el chat (ver «En Claude Desktop»). Cada guardado del chat es un evento `learn`
marcado `chat`, con `observed` en false (el modelo no se vio); `athos audit` los lista como guardados desde el chat en
vez de señalarlos bajo `save_in_apply_mode` mientras el ajuste es `own`.

En un modelo apply nunca se ofrece ni se pide nada. Los modelos de otro agente (Codex, Muse Code, OpenCode) son modelos
apply hasta que los nombres frontier con `athos tiers add frontier <pattern>`. `"autolearn": {"on": false}` en
`~/.athos/config.json` apaga el aprendizaje autónomo, y con él todo guardado que arranca el modelo: a una sesión
frontier se le ofrece entonces [Guardar] como antes, en la interfaz clásica; en la mínima no se ofrece nada a la vista,
y la guía solo dice cómo guardar cuando lo pedís. (Una corrida headless de `claude -p`, `ATHOS_ASK=model`, Codex, Muse
Code y OpenCode siguen teniendo el hook Stop pidiéndole al modelo que guarde; ese guardado es del modelo, así que se
rechaza salvo que lo hayas pedido.)

**Quien trabaja nunca califica su propio trabajo.** Si el trabajo estuvo bien lo decide un verificador independiente,
no el modelo que lo hizo. Justo después de un guardado autónomo Athos escribe una carpeta para él,
`~/.athos/verify/<id>-v<n>-<task>/`: `diff.patch` (solo de git: los cambios de los commits que hizo la tarea, nunca sus
mensajes, lo que quedó sin commitear, y los archivos nuevos que git todavía no sigue con su texto, salvo archivos
binarios, archivos de más de 50 KB y nombres que sugieren secretos), `verification.txt` (la salida que el hook de
herramientas guardó de cada comando de verificación, con su código de salida), `piece.md` (la candidata solo como su
título, when y cuerpo: sin frontmatter, así que sin evidencia, confianza ni estado, y sin historial), `checks.json`
(sus comandos Check), y una instantánea del repositorio para que se puedan comprobar las afirmaciones que quien trabajó
aprendió leyendo archivos: `files/<path>` tiene los archivos que la pieza nombra y que existen en el repositorio y los
archivos que cambió la tarea, en su estado final, y `files.json` lista qué se incluyó, qué se recortó o se dejó afuera
y por qué. Las rutas se resuelven solo dentro del árbol de trabajo de git en el que corrió la tarea (una ruta absoluta
o `../` que lleva afuera de él, `~/…`, un enlace simbólico en cualquier punto del camino, una carpeta, un binario, un
archivo que git ignora, un nombre que sugiere secretos, y un archivo cuyo texto se dirige al verificador —«ignore
previous instructions», «note to the verifier», un veredicto en el JSON de la rúbrica— se dejan afuera y se listan;
una ruta absoluta nunca se anota), así que una pieza guardada en un repositorio marcado público nunca copia nada de
afuera; cada archivo se corta en 40.000 caracteres, todos juntos en 200.000, como mucho 25 archivos y 80 rutas
revisadas; fuera de git no hay instantánea. `history.txt` tiene los asuntos de los commits del repositorio anteriores
a los de la tarea, del más nuevo al más viejo, para que se pueda comprobar una afirmación sobre las convenciones del
historial (un prefijo en el asunto, por ejemplo): solo asuntos (sin cuerpo, autor, email ni fecha; una dirección de
email en un asunto se reemplaza), sin merges (sus asuntos nombran ramas y personas), como mucho 20, cada uno cortado en
120 caracteres, leídos de git dentro del repositorio en el que corrió la tarea, detrás del primer commit de la tarea
(detrás de HEAD cuando no hizo ninguno); los mensajes de commit de la propia tarea nunca están ahí, un asunto cuyo
texto se dirige al verificador se deja afuera y se cuenta, y cuando no hay un commit anterior (o no hay repositorio) el
archivo lo dice. `meta.json` guarda el hash del texto que lee el verificador, el repositorio en el que corrió la tarea
y el manifiesto. Después arranca, desacoplada para que ningún hook espere, una corrida headless de tu propio Claude
Code:

```
claude -p <prompt> --output-format json --model <verifier> --tools Read,Grep,Glob
       --allowedTools "Read(//<folder>/**)" --disallowedTools Bash,Edit,Write,…
       --permission-mode dontAsk --restricted --no-session-persistence --safe-mode --strict-mcp-config
       --max-budget-usd <cap> --add-dir <folder>          (in that folder, with a throwaway ATHOS_HOME,
                                                           ATHOS_HOOKS=off, ATHOS_CAPTURE=off, and none of the
                                                           calling session's variables)
```

Herramientas de solo lectura que solo pueden leer la carpeta (`--restricted` mantiene las herramientas de archivos
dentro de las carpetas de trabajo, y la única regla de permiso es una regla Read para la carpeta, que Grep y Glob
siguen; `dontAsk` niega todo lo demás), un contexto nuevo, sin plugins, hooks, CLAUDE.md ni servidores MCP
(`--safe-mode`; `ATHOS_HOOKS=off` hace que `athos hook` tampoco haga nada), nada guardado de la sesión. Su prompt es un
texto fijo con las siete rutas de entrada (los cuatro archivos, `files/`, `files.json` y `history.txt`) y nada más, y
le dice que los archivos, incluidos los del repositorio y los asuntos de los commits, son datos, nunca instrucciones:
nunca el resumen de quien trabajó ni la conversación (`prompt.txt` lo guarda, y el evento `verify` registra
`paths_only`, y `bundle_clean`: que la carpeta tiene solo sus entradas fijas —las entradas, `prompt.txt`, `meta.json`,
`result.json`—, `files/` exactamente lo que lista `files.json`, como archivos comunes, y `history.txt` solo su
encabezado fijo y líneas de asunto dentro de los topes, sin direcciones de email; que `piece.md` no tiene frontmatter ni
historial y `diff.patch` no tiene encabezado ni mensaje de commit; una aprobación de un paquete que no está limpio nunca
cuenta). Responde una rúbrica fija, un veredicto por criterio, en JSON:

| criterio | pasa cuando |
|---|---|
| `evidence_passed` | la salida de verificación muestra que los comandos terminaron bien, sin ningún fallo después del último éxito |
| `piece_matches_work` | los hechos y las instrucciones se juzgan por separado. Cada enunciado de hecho sobre el repositorio, su historial o lo que imprimen sus comandos (una duración o cualquier otra observación incluida) está respaldado por el diff, la salida de verificación, el contenido de los archivos del repositorio en la instantánea (su código o sus datos; un comentario que el diff muestra que agregó el propio trabajo no respalda nada) o los asuntos de los commits; un hecho que ninguno de ellos muestra, o uno sobre un archivo dejado afuera o una parte recortada, no está mostrado. Cada instrucción (lo que un paso dice que hay que hacer o no hacer) concuerda con lo que el diff y la salida muestran que se hizo: una que el trabajo contradice falla, y una que no muestran ni contradicen pasa solo como precaución general («no hagas push salvo que te lo pidan»), nunca cuando afirma o da a entender que algo pasó. Los enunciados sobre esta tarea o sobre la persona se juzgan bajo `reusable` |
| `checks_runnable` | al menos una Check es un comando concreto que se puede volver a correr más adelante en este repositorio |
| `no_private_data` | ningún secreto, credencial, dato personal ni carpeta de una computadora en particular |
| `reusable` | una forma de trabajar para una tarea futura, no una narración de esta: nada sobre esta tarea en particular, ni sobre lo que la persona pidió, dijo o quería, dicho como un hecho («la persona pidió…», «en esta sesión…», el asunto que usó el commit de este trabajo); una preferencia de la persona cuenta solo escrita como una regla a seguir |

El veredicto pasa solo cuando pasan todos los criterios, y cuenta solo para el texto que leyó: cuando la pieza cambió
desde que se escribió su carpeta, o mientras corría el verificador, el veredicto no se aplica (resultado `stale`).
Corre en un modelo frontier distinto del que hizo el trabajo: `autolearn.verifier.models` en `config.json`, o si no uno
por cada familia frontier que nombran tus niveles (`claude-fable-*` → `fable`, `claude-opus-*` → `opus`; un id exacto
tal como está escrito), el primero de una familia distinta de la de quien trabajó. Cuando hay uno solo, o no se puede
leer el id del modelo de quien trabajó, se puede usar el mismo modelo y el evento `verify` dice `same_model_fallback`
(y la evidencia de la pieza `verifier:pass:same-model`).

Cada corrida de modelo que arranca Athos (verificadores y repeticiones juntos) cuenta contra un tope diario:
`autolearn.budget` con `runs_per_day` (por defecto 6) y `usd_per_day` (por defecto US$1,00); cada corrida además tiene
un tope de `autolearn.verifier.max_usd_per_run` (US$0,50) o lo que quede del día, lo que sea menor, y se corta después
de `autolearn.verifier.timeout_s` (300 s). Los topes son estrictos: antes de que arranque una corrida se reserva su
tope, bajo un lock, en `~/.athos/autolearn/runs.json`, y se liquida después con lo que la corrida informó que gastó;
una corrida que no informó nada (un timeout, un verificador que se mató) cuenta toda su reserva. Una corrida que nunca
arrancó (sin `claude` en el PATH, sin sesión iniciada, un modelo que la cuenta no puede usar) no cuesta nada y no usa
ningún intento, y un modelo no disponible se reintenta una vez con el propio modelo de quien trabajó. Corre un solo
verificador a la vez (su lock se toma en un paso). Un tope de 0 apaga las corridas de modelo, y
`"verifier": {"on": false}` apaga el verificador. Una corrida rechazada por el tope, fallida o que se pasó de tiempo
deja la pieza como candidata y dice por qué (eventos `grade` y `learn`); una candidata que sigue esperando la toma, sin
que nadie lo pida, el primer inicio de sesión o fin de turno que el tope permita (después del tope de un día, el
primero del día siguiente), como mucho dos intentos. Los paquetes se podan a los últimos 50 al final de un turno, salvo
los que siguen esperando. `athos verify <id>` lo corre a mano, en primer plano; `athos verify --pending`, la más vieja
que espera. `athos verify <id> --rebuild` verifica de nuevo una candidata (después de un veredicto fallido, por
ejemplo) desde un paquete nuevo armado a partir de la tarea que registró su último paquete: el diff de los commits de
esa tarea y la instantánea leída de su último commit, en una carpeta nueva (`…-r<time>`), bajo los mismos topes; el
veredicto nuevo reemplaza al anterior para el mismo texto (un fallo posterior anula una aprobación anterior). Cuando ya
no están el repositorio, la evidencia de la tarea o uno de sus commits, o la tarea no hizo ningún commit, lo dice
(resultado `error`) y la pieza sigue como candidata.

| evento | se escribe cuando | campos |
|---|---|---|
| `verify` | termina una corrida del verificador, o se rechaza | `piece`, `version`, `task_id`, `outcome` (pass, fail, error, skipped, stale), `model`, `worker_model`, `same_model_fallback`, `verdict` (por criterio, true o false), `why` (una línea por criterio), `error`, `cost_usd`, `bundle`, `inputs` (los nombres de archivo que recibió), `prompt_file`, `paths_only`, `bundle_clean`, `attempts`, `body_sha` (el texto que leyó) |
| `model_run` | antes de que arranque una corrida de modelo (`phase` reserved, con `usd_reserved`), cuando termina (`phase` settled), o cuando el tope la rechaza (`phase` refused); una corrida con reserva y sin evento settled (matada) cuenta toda su reserva | `phase`, `purpose` (verify, replay), `piece`, `version`, `model`, `run_id`, `started` (false para una que nunca arrancó), `refused` (por qué), `ok`, `error`, `cost_usd`, `cost_estimated`, `cost_counted` (lo que el presupuesto del día cuenta por ella), `usd_cap_run`, `usd_per_day`, `runs_per_day`, `duration_s` |

**Promoción y degradación.** Cada movimiento es un evento `grade` con su fundamento, y también lo es una decisión de
no moverse:

- **candidata → verificada** cuando el verificador aprobó la pieza tal como está ahora (su título, when y cuerpo;
  `body_sha` en el evento `verify`), tiene al menos una Check que se puede correr, y desde que pasó a candidata hubo
  **dos reusos limpios en un modelo frontier** o **una aprobación en un modelo apply** (una repetición, más abajo, o un
  uso real cuyas Checks los hooks vieron pasar). Una pieza `risk: high` necesita el verificador y al menos un reuso
  limpio; una repetición sola no la verifica. Los reusos solos, sin el verificador, nunca verifican nada.
- **verificada → candidata** después de un reuso que se corrigió o falló, lo que requiere evidencia fuerte atada a esa
  pieza: un cambio tuyo atribuido a ella, o una de sus propias Checks fallando al final. Una pieza legacy nunca se
  mueve: con esa evidencia se marca para revisión en cambio, y un evento `grade` dice qué se vio. Las señales débiles
  nunca cambian un estado: una reacción leída de tus palabras solo baja la confianza (−0,1) y hace que ese reuso no
  cuente como limpio.
- **→ retirada** cuando 3 de sus últimos 5 reusos juzgados se corrigieron o fallaron, contados desde su último cambio
  de estado, revert o mejora (cada uno es una versión nueva, y la cuenta vuelve a empezar), así que una pieza que
  volvió con `athos
  revert` no se retira de nuevo por su próximo reuso (una pieza legacy se marca para revisión en cambio). Retirarla la
  reemplaza con una versión nueva; `athos revert` la restaura.
- **envejecimiento, sin modelo**: una pieza verificada sin uso ni reverificación en `autolearn.age_days` (90) días
  vuelve a candidata; se comprueba cuando arranca una sesión. Usar una pieza mueve su fecha de último uso, así que el
  uso frena el envejecimiento. Las piezas legacy no envejecen.

Un reuso se juzga cuando termina la tarea (el hook Stop), cuando su evidencia objetiva es definitiva: un evento `reuse`
por cada pieza que usó la tarea (abierta, en un modelo frontier; dada, en un modelo apply), nunca en la sesión que la
guardó o la mejoró, así que una sesión con un solo pedido, y la última tarea de cualquier sesión, también se juzgan. Tu
próximo pedido puede enmendarlo: tu reacción leída de las palabras baja la confianza (−0,1) y hace que ese reuso no
cuente como limpio, y una edición tuya atribuida a la pieza la vuelve corregida; la enmienda es un evento `reuse` nuevo
para la misma tarea (`amends`: el resultado que reemplaza), escrito solo cuando el resultado cambia, y solo cuenta el
último de una tarea, así que un mismo trabajo nunca son dos reusos. Una tarea que terminó sin juzgarse (una sesión
matada antes de su próximo pedido, una versión anterior) se juzga en el próximo inicio de sesión en su proyecto
(`stage` catch_up), con las mismas reglas, a partir del registro. Un mensaje que el harness manda en medio del trabajo
(el `<task-notification>` de una tarea en segundo plano, el informe de un subagente: texto en uno de los envoltorios
del harness) no arranca una tarea: la tarea abierta sigue (un evento `task_continued`), así que un mismo trabajo se
juzga una vez. En un modelo frontier es **limpio** cuando la evidencia de la tarea tiene un elemento fuerte a favor del
trabajo y nada en contra, **corregido** con evidencia fuerte atada a la pieza (una edición tuya atribuida a ella, una
de sus Checks fallando al final), y **no verificado** (no cuenta) cuando nada probó el trabajo, cuando algo estuvo en
contra del trabajo sin nombrar esta pieza (un revert, una edición tuya atribuida a otra pieza o a ninguna, una
verificación fallida que no es una de sus Checks), o cuando tus palabras se leen como una corrección. En un modelo
apply es **limpio** solo cuando se vio pasar al menos una de sus Checks y ninguna fallando al final, **fallido** con la
misma evidencia atada, y no verificado en los demás casos. Un fallo en un modelo apply además marca la pieza para
revisión: el índice del próximo modelo frontier lo dice.

La confianza (de 0 a 1) arranca en 0,3, se mueve +0,2 con una aprobación del verificador, −0,1 con un fallo, +0,1 por
reuso limpio, −0,2 por uno corregido o fallido, −0,1 cuando la comprobación del entorno de abajo encuentra algo que
falta, es al menos 0,7 una vez verificada y 0,05 una vez retirada. Multiplica el puntaje del router por
1 + 0,2 × (confianza − 0,7), de 0,92 a 1,06: deciden las palabras y la confianza solo desempata casi empates. Una pieza
legacy no tiene confianza, su factor es exactamente 1, y a su archivo nunca se le pone una. `athos bench route` da el
mismo hit@1, cargas equivocadas y «none ok» que antes.

**Comprobar una pieza vieja contra el entorno.** Antes de que el índice de un modelo frontier liste una pieza no creada
ni verificada en `autolearn.reverify_days` (14) días, Athos comprueba una vez por sesión, sin correr nada, que lo que
nombra sigue ahí: archivos entre backticks relativos al repositorio, los comandos con los que empiezan sus líneas de
comando (en el PATH), sus scripts `npm run` (en package.json) y sus targets de `make` (en el Makefile). Los flags de
otros comandos no se pueden comprobar así y no se comprueban. Lo que falta va en la línea del índice
(`may be stale: 1 named file(s) not found here`), en un evento `reverify` y, para una pieza aprendida, en una
confianza más baja. El índice de un modelo frontier además dice `candidate, not
verified yet` para una candidata (o, para una de su proyecto que el verificador rechazó, `candidate, not accepted by the
verifier: …`, arriba), `needs review: it failed on an apply model` después de un fallo así, y `set aside for the
person: don't rewrite it` para una pieza apartada.

**En un modelo apply.** Solo cargan las piezas verificadas y las legacy, y nunca una retirada;
`"autolearn": {"apply_candidates": true}` además deja cargar las candidatas de su propio proyecto. Una pieza aprendida
llega como un checklist corto: el When y el Do de cada paso, su Check y sus traspasos, sin razones, links ni historial,
bajo "Steps, in order.
After each one, run its Check and go on only when it holds; if a Check fails, stop and say which one failed." Los pasos
riesgosos de cualquier pieza, también de las legacy, llevan una línea después de su Do: `**Ask first:** this step publishes: ask the person and do it
only on their clear yes.` (un modelo frontier lee las páginas tal como están escritas). El modelo apply nunca guarda ni
cambia una pieza: lo que vieron los hooks (sus Checks pasando o fallando, tus correcciones) es la evidencia.

**Repetir una candidata en un modelo apply**, apagado por defecto porque cuesta dos corridas de modelo: con
`"autolearn": {"replay": {"on": true, "model": "haiku"}}`, un guardado autónomo además guarda la tarea como el caso de
la candidata (el pedido y la respuesta frontier, `mark: frontier`, nunca en un repositorio público), y una vez que el
verificador aprueba, el modelo apply responde ese pedido con la pieza como su know-how y un modelo frontier lo juzga
contra la respuesta frontier, como hace `athos shadow`. Una aprobación es un evento `reuse` (nivel apply, `replay_pass`)
que puede verificar una pieza de riesgo normal. Las dos corridas cuentan contra el mismo tope diario.

| evento | se escribe cuando | campos |
|---|---|---|
| `grade` | una pieza se mueve, o un resultado del verificador o una regla la deja donde está | `piece`, `version`, `from`, `to` (candidate, verified, retired, legacy), `basis`, y para un movimiento `trigger`, `verifier_pass`, `verifier_model`, `frontier_clean`, `apply_pass`, `risk`, `checks` |
| `reuse` | el final de una tarea que usó una pieza (y su enmienda por el próximo pedido, o su puesta al día en un inicio de sesión posterior), o una repetición | `piece`, `version`, `task_id`, `stage` (stop, next_request, catch_up), `amends` (el resultado que reemplaza), `tier` (frontier, apply), `model`, `outcome` (clean, corrected, failed, unverified, replay_pass, replay_fail), `basis` (strong_positive, no_correction, check_passed, check_failed, person_edit, person_edit_not_this_piece, revert, last_verification_failed, reaction_corrected, no_check_ran, nothing_proved_the_work, written_in_session, replay, score), `status`, `verdict` (el último veredicto del verificador sobre ese texto en ese momento, para una candidata: un reuso bajo `fail` nunca cuenta para la promoción) |
| `reverify` | una pieza vieja se comprueba contra el entorno | `piece`, `version`, `age_days`, `checked`, `missing` (archivos, comandos, scripts, targets: cantidades), `stale` |

**Reparar estadísticas contaminadas.** Las sesiones registradas antes de 0.1.111 contaban como usadas piezas de otros
proyectos (un proyecto sin piezas propias veía entonces todas las piezas), y antes de 0.1.112 el detector de ediciones
te atribuía a vos las ediciones del propio agente. Esas líneas quedan como estaban; `athos repair --session <id>`
agrega eventos `correction` en cambio, y las estadísticas (`athos report`, las barras, el curado, la calificación)
dejan de contar lo que nombran:

```
athos repair --session <id> [--pieces mistaken|foreign|all|none] [--apply] [--show] [--json]
```

Corrige los eventos `learned_from_edit` de la sesión sin evidencia (sin `basis`), y los usos en tareas de piezas que
solo se inyectaron: piezas de otros proyectos y, cuando el proyecto de la sesión no tiene piezas propias, todas las
piezas (`--pieces mistaken`, el valor por defecto; `foreign` conserva las piezas generales; `all`; `none` no toca
ningún uso). Una pieza que el modelo abrió por su cuenta (`piece_opened`) sigue siendo un uso. Es una prueba en seco
salvo con `--apply`; correrlo de nuevo no escribe nada nuevo. El evento `correction` tiene `target` (learned_from_edit,
task_pieces), `task_id`, `piece`, `original_at` y `reason` (no_evidence_the_person_edited, another_project,
project_without_own_pieces, asked_all); `athos audit` sigue listando las ediciones viejas, marcadas `corrected`.

**Carriles de riesgo.** Un paso es de riesgo alto cuando su When o su Do publica (`npm publish`, `git push`,
`docker push`, `gh
release create`, la palabra publish), mergea (`gh pr merge`, `git merge`, merge), despliega (deploy, `kubectl apply`,
`terraform apply|destroy`, `helm install|upgrade`, `vercel --prod`), borra (`rm -r`, `rm -f`, delete, `DROP TABLE`,
`git branch -D`, `git clean -f`), hace force-push (`--force`, `-f`, `--force-with-lease`) o toca producción (prod,
production), en inglés o en castellano. El detector es conservador a propósito: en la duda un paso es de riesgo alto,
lo que solo hace más estricta la promoción y, en un modelo apply, te pregunta antes de que corra el paso. Una pieza con
algún paso así se guarda con `risk: high`.

### Modelos por paso

Para `athos delegate`: dentro de una forma de trabajar, la mayoría de los pasos son mecánicos (extraer los datos, correr
un script, armar una tabla) y uno o dos necesitan razonar de verdad. Un enunciado puede nombrar el modelo que necesita
con una línea opcional:

```
## #judge
**When:** the totals are extracted.
**Do:** decide which invoices look wrong, and why.
**Model:** meta
```

El valor es `local` (el modelo de Ollama por defecto), `meta` (muse-spark-1.3), `ollama:<model>` o `meta:<model>`. Un
enunciado sin esa línea corre con el modelo de la tarea (`--model` / `--backend`, si no el que viene por defecto), y las
piezas sin ninguna línea `**Model:**` se comportan como antes. Un valor desconocido frena la ejecución antes de que
empiece nada.

```
athos delegate <piece> "<request>" --by-step                 each statement in turn, on its own model
athos delegate <piece> "<request>" --by-step --allow-meta    also let the steps marked meta run on Meta Model API
athos route <piece>                                          per step: which models ran it and how those tasks ended
athos route <piece> --apply                                  write the suggested **Model:** lines (a new version)
```

`--by-step` corre la pieza enunciado por enunciado en una sola conversación: para cada uno se le dice al modelo «Now do
only this step: #id — <Do>» y trabaja con las mismas herramientas y confirmaciones que una delegación común. Cada paso
se reporta a la trayectoria, así que `athos watch` lo va tildando a medida que avanza, y el registro de la tarea guarda,
por paso, el modelo, el tiempo y los tokens. Un paso con el modelo hospedado de Meta manda el pedido y los archivos que
lee fuera de tu máquina, así que solo corre con `--allow-meta` (o `--backend meta`).

`athos route` lee tus delegaciones por paso anteriores de una pieza y tus marcas sobre ellas, y sugiere para cada paso
el modelo más barato (local antes que hospedado, un modelo local más chico antes que uno más grande) que tuvo ahí al
menos tres ejecuciones marcadas bien y nunca terminó en una tarea corregida o fallida; si no, dice por qué no tiene
sugerencia. Una marca es para toda la tarea, así que cada paso comparte la marca de su tarea, y las ejecuciones sin
marcar no prueban nada. `--apply` guarda las sugerencias como una versión nueva con la nota «routed by results»;
`athos revert <piece>` lo deshace.

### Tus correcciones como tests, tus respuestas aprobadas como referencias

Cuando marcás una tarea que siguió una de tus piezas, Athos la guarda como un **caso**, solo en tu máquina, en
`~/.athos/cases/<piece>/<task>.json`: el pedido completo, la respuesta final del agente (de la transcripción del agente,
cuando se puede leer), la pieza y la versión usadas, tu marca y, para una tarea corregida, tu corrección: las palabras
que dijiste después y que la juzgaron mal («no, el preaviso es de 30 días»), o tu pedido siguiente después de
`/athos:mark c`. Las tareas que nunca marcás, o que no usaron ninguna pieza, no se guardan.

Cada caso corregido es un **test** de la pieza. Después de que mejorás una pieza, la línea de guardado dice cuántas de
tus correcciones anteriores se pueden volver a comprobar, y el agente ofrece correrlas:

```
athos test <piece>                           each past request answered again with the piece as it is now, and a
                                             second call judges whether the answer respects your correction
athos test <piece> --backend meta            the same on Meta Model API (--model to choose the model)
```

Imprime una línea por caso (pasa o falla, y por qué) y registra la ejecución. Cada caso bien es una **referencia**:
`athos shadow` vuelve a responder tus pedidos aprobados con un modelo más barato, con la pieza, y juzga qué tan cerca
está cada respuesta de la que aprobaste (0-100, equivalente o no):

```
athos shadow [--limit N]                     the approved tasks not yet compared on this model
athos shadow on                              after each task, compare one approved task in the background
athos shadow on --backend meta               the same on Meta Model API; `athos shadow off` stops it
```

Los dos responden sin herramientas (la pieza como instrucciones, tu pedido como mensaje) y corren con Ollama en tu
máquina por defecto; nada va a un modelo hospedado salvo que elijas `--backend meta`. En segundo plano, la comparación
corre como un proceso aparte de baja prioridad que nunca demora a tu agente. Cuando un modelo más barato corrió al
menos 5 de las tareas aprobadas de una pieza y coincidió en 9 de las últimas 10, Athos te avisa una vez, en tu idioma,
al empezar una sesión o cuando esa pieza se carga: «Tu forma de trabajar «Revisar un contrato» está firme: Muse Spark
coincidió en 9 de tus últimas 10 tareas aprobadas. ¿Querés pasársela a Muse Spark?». Decir que sí quiere decir correr
esas tareas con `athos delegate`. `athos status --json` muestra los conteos (`tests` por pieza cargada) y las
sugerencias (`handoff`).

### En Codex

Athos también es un plugin de Codex, que lee el mismo almacén:

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

El plugin trae la skill `athos`. En la app de escritorio de Codex también trae los hooks de Athos; en el CLI de Codex
agregalos una vez con `athos codex install` (Codex te pide que confíes en ellos con `/hooks`). El pie de Codex no
admite líneas propias, así que corré `athos watch` en una terminal al lado: una barra por agente para el know-how de
este proyecto, las mismas barras que Claude Code muestra debajo de su prompt, marcadas con g / c / f.

### En Muse Code

Muse Code corre el mismo plugin que Claude Code: se cargan las piezas que coinciden con cada pedido, cada tarea se
registra con el modelo que respondió y sus tokens (del propio registro de sesión de Muse), y después de un turno que
cambió algo o siguió una checklist Athos pregunta una vez si guardar o mejorar una pieza (el guardado del modelo se
rechaza salvo que lo hayas pedido con `Athos · save:`: ver «Quién puede guardar»). `athos watch` y `/athos:report`
muestran Muse Code al lado de Claude Code y Codex. Dejá apagado el modo Contributor de Muse Code (`muse` → `/settings`)
salvo que quieras que Meta entrene con tus sesiones; Athos avisa cuando una tarea corrió con él.

Sin el plugin, `athos export --muse` escribe tu perfil como skills en `~/.agents/skills` (esa carpeta se lee en todos
los proyectos; `athos project sync` le da a un proyecto sus propias piezas) y `athos import muse` registra tareas
anteriores desde los registros de sesión de Muse.

### En OpenCode

Athos es un plugin de OpenCode. Instalalo una vez:

```
athos opencode install       writes ~/.config/opencode/plugins/athos.js (it runs ~/.athos/bin/athos, the newest installed Athos); restart OpenCode
```

Con cualquier modelo que corra OpenCode, las piezas que coinciden con cada mensaje van a su prompt de sistema, cada
tarea se registra con los conteos de tokens del propio OpenCode y, en la interfaz clásica, después de un turno que
cambió algo o siguió una checklist Athos pregunta una vez si guardar o mejorar una pieza, y un aviso (toast) sigue los
pasos; en la mínima (la que viene por defecto), ninguna de las dos cosas. `athos opencode uninstall` lo quita.

### En Claude Desktop

En la pestaña **Code**, Claude Desktop corre Claude Code con la misma configuración, así que el plugin funciona tal
cual, incluido el panel de la trayectoria al lado de la transcripción. Para el **chat** común, que admite servidores
MCP pero no plugins, instalá Athos como extensión de Desktop: `athos desktop` arma `dist/athos.mcpb`; hacele doble clic
(o arrastralo a Configuración → Extensiones). Corre `athos mcp` contra tu propio `~/.athos`.

En el chat, Athos encuentra el know-how para cada pedido (`athos_find`), y en un chat que dibuja MCP Apps esa llamada
abre el panel de Athos en la conversación. En la interfaz mínima (la que viene por defecto) el panel es el mismo
cuadradito que en Claude Code, una línea corta, y nada más:

| estado | lo que ves | cuándo |
|---|---|---|
| colaborando | un ■ verde y `Athos is collaborating` (`Athos está colaborando`) | `athos_find` entregó una de tus piezas, o se está reportando un paso de una (`athos_step`); gana, también mientras un guardado mejora esa pieza |
| aprendiendo | un ■ rojo y `Athos is learning` (`Athos está aprendiendo`) | la tarea no sigue ninguna pieza y el modelo reporta pasos que tu know-how no tiene (`athos_step` con `new`), o se está escribiendo un guardado desde el chat |
| inactivo | nada: el panel está vacío y no ocupa lugar | nada coincidió y no hay nada en borrador, la tarea terminó (`athos_done`), o no se movió en 6 minutos |

Sin título de pieza, sin pasos, sin botones, sin avisos: la página recibe solo el estado, su `why`, el idioma y la
interfaz, nunca un id de pieza, un título, un paso o tu pedido. El modelo igual reporta cada paso con `athos_step`,
porque eso mueve el cuadradito, pero no se muestra nada de eso. El estado lo calcula `indicator.py` (`chat`), y cada
cambio es un evento `ui` en `athos audit`, como en Claude Code. Las MCP Apps declaran la página de una herramienta una
sola vez, en la lista de herramientas, no por resultado, así que un pedido que no coincide con nada igual abre el panel;
queda vacío.

**El chat guarda solo.** Con `autolearn.chat` en `own` (lo que viene por defecto), cuando una tarea de varios pasos no
siguió ninguna forma de trabajar y terminó, el modelo guarda una vez lo que le enseñaste con `athos_save` (un título, un
when, un enunciado por paso con When, Do y Because), justo antes de `athos_done`, sin anunciarlo ni preguntarte; cuando
la tarea siguió una pieza y agregó pasos, mejora esa pieza en su lugar (su id y una nota). La pieza es tuya (sin
`status`), porque elegiste dejar que el chat guarde. Igual pasa las comprobaciones que un guardado automático aplica a
su contenido: la comprobación de datos privados (emails, números de teléfono y de documento, links, carpetas de esta
computadora, nombres de otros proyectos, tu nombre) y la comprobación de casi duplicados contra las piezas que el chat
puede nombrar (se rechaza con el pedido de mejorar esa pieza en su lugar). Un rechazo le dice al modelo por qué en una
línea y no guarda nada. Una pieza que el chat no puede nombrar nunca se cambia desde ahí. `athos_merge` con `apply`
sigue rechazado en el chat. Mirá lo que se guardó con `athos list`, o preguntándole al chat *«¿qué formas de trabajar
tengo?»*; `athos revert <id> <version>` vuelve atrás. Para apagarlo:

```json
{ "autolearn": { "chat": "off" } }
```

en `~/.athos/config.json`: entonces el `athos_save` del modelo no guarda nada en el chat, como antes (ver «Quién puede
guardar»). El panel nombra solo piezas que `athos_find` puede entregar ahí (tu selección, sin carpeta: `athos load`);
un paso reportado sobre cualquier otra pieza, o una pieza abierta con `athos_show`, no prende el cuadradito.

Cada herramienta de Athos le dice a Claude Desktop qué hace (anotaciones de herramientas MCP y un título): `athos_show`,
`athos_list`, `athos_trail` y `athos_library` solo leen; las demás cambian algo pero nunca borran ni sobrescriben (un
guardado, una fusión o volver atrás agrega una versión y conserva las viejas); `athos_share`, `athos_add` y
`athos_connect` van más allá de esta computadora. La primera vez que corre cada herramienta, Claude Desktop pregunta;
**Always allow** ahí, o los permisos de la herramienta en Configuración → Extensiones (o Conectores) → Athos, hacen que
deje de preguntar (los nombres pueden variar un poco según la versión).

`"ui": "classic"` en `~/.athos/config.json` trae de vuelta el panel viejo: la tarjeta del momento, estrellas en
cualquier paso, el comprobante al final (lo abre `athos_done`) y **Fijar al costado** (**Keep beside**). En un chat sin
MCP Apps, las mismas herramientas responden como texto.

Paso a paso, para quienes no programan: [docs/guides/claude-desktop.md](guides/claude-desktop.md)
(en inglés: [docs/guides/claude-desktop-en.md](guides/claude-desktop-en.md)).

Sin la extensión, el servidor también se puede agregar a mano en Configuración → Desarrollador → Editar configuración
(`claude_desktop_config.json`), con la ruta absoluta del comando `athos`:

```json
{ "mcpServers": { "athos": { "command": "/Users/you/.local/bin/athos", "args": ["mcp"] } } }
```

### El primer uso y tus otros agentes, desde el panel de Desktop

El panel también configura Athos, de a un clic por vez; nada cambia tu configuración sin uno.

- **Primer uso**: cuando todavía no hay formas de trabajar, el panel pregunta a qué te dedicás (derecho, finanzas,
  periodismo, ciencia, ingeniería de guardia, otra cosa) en tu idioma. Un clic agrega las formas de trabajar de ejemplo
  de esa profesión, exactamente como hace `athos start`, dice en una línea qué agregó y ofrece un primer pedido para
  probar.
- **Usá Athos también en tus otros agentes**: el panel lista Codex, OpenCode y Muse Code cuando están en esta
  computadora (su comando en el PATH, o su carpeta de configuración), cada uno con **Connect**. Codex corre el mismo
  código que `athos codex install` (después aprobá los hooks una vez con `/hooks` en Codex), OpenCode lo mismo que
  `athos opencode install` (después reiniciá OpenCode), y Muse Code corre `muse plugins marketplace add athos
  https://github.com/athos-agent/athos`, `muse plugins install athos@athos` y `muse plugins approve athos`.
- **Versiones**: una línea cuando un agente corre un Athos más viejo que el más nuevo de esta computadora, con qué
  hacer.

Los dos botones llaman herramientas que solo ve el panel (`athos_start`, `athos_connect`); el modelo nunca las llama.

### athos doctor

```
athos doctor [--json]
```

Qué Athos correría cada agente, y cuáles están atrás del más nuevo publicado o instalado (la versión más nueva que los
marketplaces de esta computadora bajaron por última vez, o la más nueva que corre un agente; nunca la copia que corre el
comando, que puede ser un checkout adelantado respecto de la publicación): Claude Code (su caché de
plugins), Claude Desktop (el `manifest.json` de la extensión), Codex (el `athos` que corren sus hooks: `~/.athos/bin/athos`
corre el plugin de Claude Code más nuevo), OpenCode (el `athos` que corre su plugin), Muse Code (su registro de plugins, o
`muse plugins list` con un timeout corto) y el `athos` del PATH. Sale con 1 cuando uno está atrás. La misma línea está
en `athos status --json` (`behind`) y en el panel de Desktop.

### La galería

`gallery/` tiene formas de trabajar que cualquiera puede tomar, en inglés y en español: páginas normales de Athos
(frontmatter con `id`, `title`, `when`, `profession`, `lang`; enunciados con ramas **If:** y **Calls:**). Cada ejemplo
es ficticio y deja las decisiones profesionales a la persona. `athos gallery build [--out DIR]` escribe `gallery.json`
(cada página, sus pasos y ramas, y las páginas que llama) e `index.html`, una página estática que previsualiza cada
entrada como la dibuja el panel, filtrada por profesión e idioma. Su botón **Usar en Athos** (**Use in Athos**) copia un
pedido corto:

```
Athos · add from gallery: review-a-services-contract
```

Pegado en cualquier agente con Athos, el hook del prompt (o `athos_find` en Desktop) hace que el agente corra el add:

```
athos add <id | raw URL> [--dry-run]       athos_add in Desktop's chat
```

Descarga solo desde `https://raw.githubusercontent.com/athos-agent/athos/main/gallery/` (cualquier otro host o ruta se
rechaza), la entrada y las páginas a las que enlaza, y guarda cada una que todavía no tenés como versión 1 con origen
`gallery`. Una página que ya tenés queda como está. Para aportar una entrada, abrí un pull request con sus páginas en
los dos idiomas; `tests/test_gallery.py` comprueba que cada link y cada rama lleven a una página de la galería.

### Dentro de un proyecto, para cualquier agente

`athos project sync` escribe el know-how de este proyecto en `.athos/`, como markdown simple que cualquier agente lee
sin tener Athos instalado:

```
.athos/
  wiki/      Index.md (where a task starts), the pages, METHOD.md (how the pages and their trajectories were made)
  agents/    one subagent per trajectory, and AGENTS.md listing them
  skills/    one skill per page, and SKILLS.md listing them
  tools/     code the pages call when a step is a calculation, not a judgement
```

Cada agente lo encuentra donde ya busca: `.claude/skills` y `CLAUDE.md` (Claude Code), `.agents/skills` y
`AGENTS.md` (Codex, Muse Code, OpenCode), `.claude/agents` y `.opencode/agents` (subagentes). Por defecto toma las
piezas que este proyecto usó o con las que está etiquetado (`--piece ID` o `--all` para elegir), y se agrega a sí mismo
a `.gitignore`: tu know-how sigue siendo tuyo aun en el repositorio de otra persona, salvo que lo compartas con
`--commit`. `athos project remove` lo saca todo de nuevo.
En un repositorio marcado como público escribe solo las páginas que se pueden cargar ahí (las propias de este proyecto
y las páginas del perfil que permitiste en público), pida lo que pida `--all` o `--piece`.

**Subagentes de trayectoria.** `athos wiki agents --install` escribe los subagentes que recorren las trayectorias de
este proyecto (sus propias páginas y tu perfil, nunca las de otro proyecto) en `.claude/agents` del repositorio (o
`--dir <folder>`), los deja fuera de git en esta máquina (`.git/info/exclude`) y los reescribe después de cada
guardado. Se niega en un repositorio marcado como público (el que corre o la carpeta nombrada con `--dir`), y nunca se
reescriben desde uno ni hacia uno: un guardado hecho en un repositorio público no los toca, y tampoco ningún guardado
una vez que el repositorio donde se instalaron se declara público. `athos wiki agents --uninstall [--dir <folder>]`
los quita y deja de reescribirlos. Antes de 0.1.121 iban a `~/.claude/agents`, que Claude Code lee en todos los
proyectos, y recorrían todo el almacén, así que sus descripciones llevaban los títulos de las páginas de todos los
proyectos a todas las sesiones; una instalación hecha de esa forma ya no se mantiene al día después de un guardado
hasta que instales de nuevo.

### Gremios: una forma de trabajar para el equipo

Cuando varias personas de un estudio o de un equipo mejoran su propia copia de la misma pieza («Revisar un contrato de
locación»), Athos puede fusionar lo mejor de cada una en una versión del equipo. Cada colega exporta la suya:

```
athos export --guild <folder> --as Ana [--piece review-a-lease]
```

Esto escribe cada archivo de pieza y un `<id>.stats.json` al lado: por enunciado, cuántas tareas de esa persona lo
recorrieron (los pasos que reportó el agente) y cómo se marcaron esas tareas (bien, corregida, fallida). Solo conteos:
ningún pedido, ningún cliente, nada sobre el trabajo en sí. Después, con sus carpetas (o archivos) en tu máquina:

```
athos merge review-a-lease ./team                 a dry run: what it would keep, take from whom, drop, and why
athos merge review-a-lease ./team --apply         save it as a new version of your piece (the old one stays in history)
athos merge review-a-lease ana/lease-review.md --as-id lease-review     their copy has another id
athos merge review-a-lease ./team --model qwen3.5:9b                    let a local model merge differing texts
```

Los enunciados se alinean por id, o por un **When** para el mismo momento cuando los ids difieren (se conserva tu id,
así los links siguen resolviendo). Un enunciado que tiene una sola copia se conserva si sus tareas salieron bien o nadie
las marcó, y se descarta (y se lista) cuando la mayoría de sus tareas marcadas fueron corregidas o fallidas. Donde las
copias dicen cosas distintas, gana el texto con el mejor historial; si nadie marcó nada, queda el tuyo. Con `--model`
(Ollama en esta máquina) o `--backend meta` (manda esos enunciados a Meta Model API), un modelo fusiona los textos
distintos en uno, conservando tus convenciones, y cualquier respuesta que no sea un enunciado limpio vuelve al mejor
historial. La prueba en seco escribe la propuesta en `~/.athos/guild/<id>.merged.md` (`--out` para elegir); `--apply`
la guarda con una nota en el historial que nombra las fuentes, y `athos revert <id>` lo deshace. En el chat de Claude
Desktop la misma fusión es la herramienta `athos_merge` («fusioná mi revisión de contratos de locación con la versión
de Ana que está en esta carpeta»): primero propone y aplica solo cuando se le pide.

### Tu know-how como dataset de fine-tuning (Fireworks AI, OpenAI)

`athos export --dataset FILE` escribe tus enunciados y tus tareas marcadas como líneas JSON. Con `--format fireworks`
los escribe en cambio como el JSONL de chat que lee el fine-tuning supervisado de Fireworks AI (y el de OpenAI, que
tiene la misma forma, así que `--format openai` escribe las mismas filas): un `{"messages": [system, user, assistant]}`
por línea. Para cada pieza, el turno del usuario es una situación para la que sirve (su **When**, y el pedido de cada
tarea que marcaste bien y que la usó) y el turno del asistente son sus enunciados en orden (when, do, because). Las
tareas marcadas como corregidas o fallidas, y las que no están marcadas, no dan ninguna fila. Cada fila se comprueba
antes de escribir el archivo (JSON válido, turnos de usuario y asistente alternados y terminando en el asistente,
ningún mensaje vacío), y Athos imprime cuántas filas escribió y dónde:

```
athos export --dataset know-how.fireworks.jsonl --format fireworks
firectl dataset create my-know-how know-how.fireworks.jsonl
firectl sftj create --base-model <MODEL_ID> --dataset my-know-how --output-model my-know-how-model
```

Fireworks pide al menos 3 filas (OpenAI al menos 10; Athos avisa por debajo de eso) y corta cada ejemplo en la longitud
de contexto del modelo (32.768 tokens por defecto). Las versiones más viejas de `firectl` escriben el primer comando
`firectl create dataset`. Para entrenar sin subir un dataset, el starter de Serverless Training del cookbook de
Fireworks (`fw-ai/cookbook`, `examples.sft.muse_glimmer_starter`) toma el mismo archivo con
`--file`. El archivo tiene tus pedidos tal como los escribiste: nada sale de esta máquina hasta que lo subas.
