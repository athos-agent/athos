# Athos en Claude Desktop: tu know-how en el chat

*English: [claude-desktop-en.md](claude-desktop-en.md)*

Este tutorial es para quien usa el **chat** de Claude Desktop (no la pestaña Code). No hace falta programar ni escribir
comandos. Al terminar, cada vez que le pidas algo a Claude:

1. Athos busca **tu** forma de hacer esa tarea y Claude la sigue.
2. Un **cuadradito** en la conversación te dice si Athos está colaborando (sigue una de tus formas de trabajar) o
   aprendiendo (anota una nueva). No se muestra nada más.
3. Cuando una tarea enseñó algo nuevo, Athos **lo guarda solo**, como una forma de trabajar tuya, y la próxima vez
   Claude ya lo sabe.

Todo queda en tu computadora, en la carpeta `~/.athos`, como texto que podés leer y editar. Nada se manda a ningún
servidor de Athos.

## 1. Lo que necesitás

- **Claude Desktop** en Mac (o Linux), con tu cuenta.
- **Python 3**, que la Mac ya trae. Si es la primera vez que se usa, la Mac puede pedirte instalar las "herramientas de
  línea de comandos": aceptá.
- Dos archivos, que se descargan de la página de Athos: [**athos.mcpb**](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb), la extensión para Claude
  Desktop, y [**athos-skill.zip**](https://github.com/athos-agent/athos/releases/latest/download/athos-skill.zip), la skill. Si ya tenés Athos en la terminal, `athos desktop`
  crea los dos en la carpeta `dist/` de Athos, con tus propias formas de trabajar en la skill.

## 2. Instalar (2 minutos)

1. Hacé **doble clic** en `athos.mcpb`. Claude Desktop se abre y te muestra la extensión: tocá **Instalar**.
   (También podés arrastrar el archivo a Claude Desktop → **Configuración → Extensiones**.)
2. Verificá que **Athos** aparezca activado en **Configuración → Extensiones**.
3. Abrí un **chat nuevo**. Los chats que ya estaban abiertos no ven la extensión.

4. Subí la **skill** `athos-skill.zip` en Claude Desktop →
   **Personalizar → Skills**. Sin la skill, Claude usa Athos solo si se lo nombrás: en el chat, las herramientas de
   las extensiones quedan guardadas hasta que el modelo las busca, y un pedido como *«revisá este contrato»* no le hace
   buscar nada. La skill le dice cuáles son tus tareas. Cuando guardes formas de trabajar nuevas, volvé a subirla.
   Con `athos desktop --carry <id>,<id>` la skill lleva adentro las formas de trabajar que elijas, y Claude las sigue
   aunque no llame a Athos. Esas quedan guardadas también en tu cuenta de Claude: elegí solo las que no tengan datos
   privados.

Para desinstalarla, desactivala o quitala desde **Configuración → Extensiones**. Tu know-how queda en `~/.athos`.

## 3. Tu primera forma de trabajar

Si ya usás Athos en Claude Code, Codex, Muse Code u OpenCode, tus formas de trabajar ya están: es la misma carpeta.
Pasá al paso 4.

Si empezás de cero, enseñale una tarea a Claude **una vez**, con tus pasos y tus criterios. Por ejemplo:

> Quiero que revises contratos de locación siempre así: primero identificá las partes y el plazo; después revisá la
> cláusula de actualización del alquiler; después las causales de rescisión; y al final armá una tabla con riesgo
> alto, medio y bajo. Revisá este contrato: [pegás el texto, ficticio o anonimizado].

Cuando termine, pedile:

> Guardá esto como forma de trabajar.

Claude la guarda con Athos y te dice el nombre. Desde ahora, un pedido corto como *«revisá este contrato de locación»*
alcanza.

## 4. Pedir algo y mirar el cuadradito

Escribí un pedido que corresponda a una de tus formas de trabajar:

> Revisá este contrato de locación: [texto]

Antes de empezar, Claude consulta a Athos y aparece una sola línea corta en la conversación:

```
■ Athos está colaborando                      (verde)
```

Es todo lo que muestra el chat: Claude sigue tu forma de trabajar, paso por paso, sin que se vea, y responde como
siempre. Si ninguna de tus formas de trabajar corresponde y la tarea lleva varios pasos, Athos los anota como una forma
de trabajar nueva:

```
■ Athos está aprendiendo                      (rojo)
```

Cuando nada corresponde y no se anota nada, no se muestra nada. Cuando la tarea termina, el cuadradito desaparece.
Habla el idioma en que escribís, español o inglés.

## 5. Aprende solo

Cuando una tarea de varios pasos no siguió ninguna de tus formas de trabajar, Athos guarda lo que enseñó al terminar,
como una forma de trabajar **tuya**: no lo anuncia ni te pregunta. Cuando la tarea siguió una tuya y sumó pasos, mejora
esa en vez de crear otra (la versión anterior se conserva). Antes de guardar, Athos rechaza lo que parece privado
(correos, enlaces, números de documento, carpetas de tu computadora, los nombres de tus proyectos) y lo que repite una
forma de trabajar que ya tenés.

Para ver lo que guardó, preguntá en el chat *«¿qué formas de trabajar tengo?»*, o escribí `athos list` en una terminal.
Para cambiar una, pedíselo a Claude o editá su archivo (ver el paso 6).

¿No querés que el chat guarde solo? Agregá esto a `~/.athos/config.json` (crealo si no existe):

```json
{ "autolearn": { "chat": "off" } }
```

Con `"off"` el chat no guarda nada, hasta que saques esa línea.

¿Querés el panel anterior, más grande (cada paso, estrellas, un resumen al final, **Fijar al costado**)? Agregá
`"ui": "classic"` al mismo archivo.

**Permisos.** La primera vez que se usa cada herramienta de Athos, Claude Desktop te pide permiso. Elegí **Permitir
siempre** ahí, o configuralo una vez en **Configuración → Extensiones** (o **Conectores**) → **Athos** → permisos de
las herramientas. Los nombres pueden variar un poco según la versión.

## 6. Ver y editar tu know-how

Cada forma de trabajar es un archivo de texto en `~/.athos/know-how/` (en Finder: **Ir → Ir a la carpeta…** y pegás
`~/.athos/know-how`). Podés abrirlo con cualquier editor. Cada paso tiene **Cuándo**, **Qué hacer** y **Por qué**.

También podés pedirle a Claude en el chat:

> Mostrame mis formas de trabajar.

> Mostrame la forma de trabajar «revisar un contrato de locación».

## 7. Si algo no se ve

| Lo que pasa | Qué hacer |
|---|---|
| No aparece el cuadradito, pero Claude sigue tu forma de trabajar | Tu versión de Claude Desktop todavía no dibuja paneles de extensiones. Athos funciona igual, en texto. Actualizá Claude Desktop. |
| Claude no consulta a Athos | Empezá un chat nuevo, o pedíselo: *«usá mi know-how de Athos para esto»*. En el chat, Claude decide cuándo usar sus herramientas. |
| El cuadradito no cambia mientras Claude trabaja | Cambia cada vez que Claude marca un paso. Si tu Claude Desktop no deja que el panel consulte a Athos solo, se ve al final del paso. |
| Claude Desktop pregunta antes de cada herramienta de Athos | Elegí **Permitir siempre**, o configuralo en **Configuración → Extensiones** (o **Conectores**) → **Athos**. |
| Elige una forma de trabajar que no corresponde | Decíselo a Claude (*«esa no aplica»*). Para que no vuelva a pasar, ajustá el **Cuándo** de esa forma de trabajar en su archivo. |
| La extensión no arranca | Revisá que la Mac tenga Python 3 (la primera vez puede pedir instalar las herramientas de línea de comandos). |

## Privacidad

- Tus formas de trabajar y el historial de Athos quedan en `~/.athos`, en tu computadora.
- Athos no manda nada a ningún servidor. Lo que escribís en el chat lo procesa Claude, como siempre.
- No pongas en una forma de trabajar datos de clientes ni contraseñas: guardá **cómo** trabajás, no **con qué** datos.
