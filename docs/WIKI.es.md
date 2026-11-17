# Tu know-how como wiki

*English: [WIKI.md](WIKI.md)*

Athos guarda tu know-how en `~/.athos/know-how/`: una página markdown por pieza, más un `Index.md` que rehace en cada
guardado. Abrí la carpeta con cualquier editor; en [Obsidian](https://obsidian.md) es una wiki con grafo y backlinks,
porque los links son `[[página]]` y `[[página#enunciado]]` comunes.

## Una página

Una página es una lista de **enunciados**, la unidad más chica que se puede comprobar:

```markdown
## #run_guard
**When:** about to commit or push to the public repo.
**Do:** run `python3 tools/guard.py .` and stop on any finding.
**Because:** a private name reached a public PR once.
**Links:** [[land-a-change#open_pr]] · [[bump-the-plugin-version#bump]]
```

- **When** es el momento en que aplica el paso, como lo reconocerías en medio de una tarea, no un tema.
- **Do** es la acción, lo bastante concreta para comprobarla: un comando, un archivo, una pregunta para hacerte, una
  negativa.
- **Because** es la razón o la evidencia (un incidente, una medición, una decisión tuya), para que un enunciado se
  pueda comprobar y, algún día, retirar.
- **Links** nombran lo que aplica **después o al mismo tiempo**.

## Pasos que pasan a otra página

El trabajo real es modular. Un paso puede pasar a otra página y volver:

    ## #borders
    **When:** the facts are clear.
    **Do:** note the countries of the investor and the asset.
    **If:** they are not all in the same country → [[check-the-cross-border-tax-treatment]]

`**Calls:** [[página]]` (o `[[página#enunciado]]`, para empezar ahí) siempre corre los enunciados de esa página como
subpasos; `**If:** <condición> → [[página]]` los corre solo cuando la condición se cumple en este caso. Las páginas
llamadas se cargan con la pieza, y la trayectoria muestra sus pasos debajo del paso que las llamó (↳), así que el
método se abre solo donde el caso lo necesita. Cambiar este paso también funciona sobre un subpaso: mejora la página a
la que pertenece el subpaso.

## Los links son trayectorias

La única regla de los links: un enunciado lleva al enunciado que se aplicó **justo después de él, o junto con él, en
una tarea real**. Dos páginas sobre el mismo tema no se enlazan solo por eso. Así, seguir los links es lo mismo que
hacer la tarea: un recorrido empieza en la página a la que apunta el Index para la situación, toma su primer enunciado
y sigue los links mientras su **When** aplique.

Los links se escriben cuando se guarda una pieza, a partir de la tarea que acaba de correr: las piezas cargadas en esa
sesión son aquellas cuyos enunciados se aplicaron, así que los enunciados nuevos las enlazan en el orden en que se
usaron. Un link que nadie vuelve a seguir es candidato a sacarse la próxima vez que se mejore la página.

## La wiki mejora con el uso

- Cada guardado es una versión nueva de una página (la anterior queda en `.history/`), escrita a partir de la tarea que
  acaba de correr.
- Cada guardado rehace `Index.md` y revisa los links. Un link que no lleva a ningún lado se informa en el mismo turno,
  así el agente lo arregla en el momento.
- Las páginas escritas antes de este formato (pasos numerados) se siguen cargando y recorriendo como un solo bloque.
  `athos wiki` las lista, y cada una se reescribe como enunciados la próxima vez que una tarea la mejora.

```
athos wiki                  rebuild Index.md; pages, statements, links; what to fix
athos wiki --json           the same, as JSON
```

## Mantenerla limpia

Una wiki que nadie cuida se llena de consejos viejos y contradictorios, así que Athos revisa dos cosas por vos;
ninguna borra nada por su cuenta.

- **El mismo momento, dos respuestas.** Cuando se guarda una página, Athos busca en las otras páginas del mismo
  proyecto un enunciado cuyo **When** describa el mismo momento. Si no están enlazados, el guardado lo dice en el mismo
  turno, y el agente revisa que coincidan: arregla el que quedó viejo, o los enlaza si aplican juntos.
- **Candidatas a retirar.** `athos wiki` lista, a partir de tus tareas registradas, las páginas que ninguna tarea
  cargó en los últimos 30 días, las páginas cuyas tareas marcadas fallaron en su mayoría, y los links cuyas páginas
  nunca se cargaron juntas en tres o más tareas desde la versión que escribió el link. Vos decidís qué sacar la
  próxima vez que se mejore la página.

## Tu know-how como datos

```
athos export --dataset know-how.jsonl
```

Una línea JSON por enunciado (when, do, because, links, y cómo salieron las tareas que usaron su página) y una por cada
tarea que marcaste (el pedido, las páginas que usó, el agente y el modelo, tu marca). Es lo que necesitás para evaluar
un modelo sobre tu propio trabajo, o para especializar uno, y se queda en tu máquina salvo que lo muevas: tiene tus
pedidos tal como los escribiste.

## Agentes de trayectoria

Un recorrido que cruza páginas (una publicación que corre el guard, después sube la versión, después abre el PR) es una
**trayectoria**. Athos escribe cada trayectoria como un subagente en markdown, `athos-<página>.md`, en
`~/.athos/agents/`: los enunciados de cada página del recorrido, en orden, con instrucciones para seguirlos mientras
apliquen, citar cada uno que sigue y dejarte a vos tus decisiones.

Los agentes no se escriben a mano y nunca se desactualizan: cada vez que mejora una página de una trayectoria, su
agente se rehace a partir de la versión nueva (su encabezado dice de qué versiones salió); cuando una trayectoria
desaparece, también desaparece su agente.

```
athos wiki agents                  list them
athos wiki agents --install        put this project's in its .claude/agents for Claude Code, and keep them in step on every save
athos wiki agents --uninstall      remove them from there
```
