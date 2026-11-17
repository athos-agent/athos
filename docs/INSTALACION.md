# Instalar Athos

*English: [INSTALL.md](INSTALL.md)*

Elegí según cómo usás la IA. La primera forma no necesita terminal ni saber programar; las otras son para quien ya
trabaja con Claude Code, con una terminal o con otro agente de programación. Todas leen y escriben la misma carpeta,
`~/.athos`, así que podés empezar con una y sumar las otras después.

1. [Claude Desktop, el chat de siempre (sin terminal)](#1-claude-desktop-el-chat-de-siempre-sin-terminal)
2. [Claude Code, o la pestaña Code de Claude Desktop](#2-claude-code-o-la-pestaña-code-de-claude-desktop)
3. [El comando `athos` (terminal, OpenCode, delegar)](#3-el-comando-athos-terminal-opencode-delegar)
4. [Codex, Muse Code, OpenCode](#4-codex-muse-code-opencode)
5. [Actualizar](#5-actualizar) · [Desinstalar](#6-desinstalar) · [Privacidad](#7-privacidad)

## 1. Claude Desktop, el chat de siempre (sin terminal)

**Lo que necesitás:** Claude Desktop en una Mac o en Linux, con tu cuenta, y Python 3.9 o más nuevo. La Mac ya trae
Python 3; la primera vez que se usa, puede pedirte instalar las "herramientas de línea de comandos": aceptá. Windows
todavía no está soportado.

1. Descargá [**athos.mcpb**](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb) de la última
   versión de Athos.
2. Hacé **doble clic** en el archivo. Claude Desktop se abre y te muestra la extensión: tocá **Instalar**. (También
   podés arrastrar el archivo a Claude Desktop → **Configuración → Extensiones**.)
3. **Cerrá Claude Desktop** del todo (⌘Q en la Mac) y volvé a abrirlo. Verificá que **Athos** aparezca activado en
   **Configuración → Extensiones**, y abrí un **chat nuevo**: los chats que ya estaban abiertos no ven la extensión.
4. Opcional, recomendado: descargá
   [**athos-skill.zip**](https://github.com/athos-agent/athos/releases/latest/download/athos-skill.zip) de la misma
   versión y subilo en **Personalizar → Skills**. Sin la skill, Claude usa Athos solo si se lo nombrás; la skill le dice
   cuáles son tus tareas. Volvé a subirla cuando hayas guardado formas de trabajar nuevas.

**Lo que vas a ver.** Mientras Claude trabaja en un pedido, una sola línea corta en la conversación:

```
■ Athos está aprendiendo                      (rojo)
■ Athos está colaborando                      (verde)
```

Rojo mientras Athos anota una forma de trabajar nueva, verde mientras Claude sigue una de las tuyas. Cuando nada
corresponde, o la tarea terminó, no se muestra nada.

**Guarda solo.** Cuando una tarea de varios pasos no siguió ninguna de tus formas de trabajar, el chat guarda lo que
enseñó como una forma de trabajar **tuya**, sin preguntar; cuando la tarea siguió una tuya y sumó pasos, mejora esa (la
versión anterior se conserva). Antes de guardar, Athos rechaza lo que parece privado (correos, enlaces, números de
documento, carpetas de tu computadora, los nombres de tus proyectos). Para ver lo que guardó, preguntá *«¿qué formas
de trabajar tengo?»*. Para apagarlo, poné esto en `~/.athos/config.json` (crealo si no existe):

```json
{ "autolearn": { "chat": "off" } }
```

**Permisos.** La primera vez que se usa cada herramienta de Athos, Claude Desktop te pide permiso. Elegí **Permitir
siempre**, o configuralo una vez en **Configuración → Extensiones** (o **Conectores**) → **Athos** → permisos de las
herramientas. Los nombres pueden variar un poco según la versión.

Paso a paso, con un primer ejemplo: [la guía de Claude Desktop](guides/claude-desktop.md).

## 2. Claude Code, o la pestaña Code de Claude Desktop

En Claude Code (en una terminal, o en la pestaña **Code** de Claude Desktop), escribí:

```
/plugin install athos --marketplace athos-agent/athos
```

Reiniciá Claude Code (o Claude Desktop) cuando te lo pida. Después pedile a Claude que corra `athos start`: te
pregunta el idioma y tu profesión y agrega formas de trabajar de ejemplo.

**Lo que vas a ver:** un cuadradito a la derecha, al pie del cuadro de texto: un ■ rojo «Athos está aprendiendo» o un
■ verde «Athos está colaborando», y nada mientras Athos no hace nada. Los detalles:
[REFERENCE](REFERENCE.es.md#lo-que-ves-un-cuadradito).

## 3. El comando `athos` (terminal, OpenCode, delegar)

El comando hace falta para OpenCode, para trabajar desde una terminal y para `athos delegate` (pasarle una tarea a un
modelo más chico o local). Necesita Python 3.11 o más nuevo, y nada más:

```sh
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start          # language, profession, example ways of working
```

El instalador pone Athos en `~/.athos/app` y el comando en `~/.local/bin/athos`; si esa carpeta no está en tu `PATH`,
te muestra la línea para agregarla. Nunca toca tu know-how en `~/.athos/know-how`.

## 4. Codex, Muse Code, OpenCode

**Codex:**

```
codex plugin marketplace add athos-agent/athos
codex plugin add athos@athos
```

En la app de escritorio de Codex el plugin trae los hooks de Athos; en la CLI de Codex agregalos una vez con
`athos codex install`, y después escribí `/hooks` en Codex y aprobá las entradas de Athos.

**Muse Code:**

```
muse plugins marketplace add athos https://github.com/athos-agent/athos
muse plugins install athos@athos
muse plugins approve athos
```

**OpenCode**, con el comando `athos` del paso 3:

```
athos opencode install       then restart OpenCode
```

Más sobre cada agente: [REFERENCE, Instalar](REFERENCE.es.md#instalar).

## 5. Actualizar

Actualizá el comando `athos` y los plugins juntos: un Athos más viejo lee solo la parte reciente de un historial que
uno más nuevo ya archivó. `athos doctor` te dice qué agente quedó atrasado y qué hacer.

| Dónde | Cómo se actualiza |
|---|---|
| El chat de Claude Desktop | descargá el [athos.mcpb](https://github.com/athos-agent/athos/releases/latest/download/athos.mcpb) más nuevo e instalalo como en el paso 1; subí también el `athos-skill.zip` más nuevo |
| Claude Code | `/plugin` y actualizá athos |
| El comando `athos` | corré de nuevo la línea `curl … install.sh \| sh` |
| Codex | `athos codex install` de nuevo |
| OpenCode | `athos opencode install` de nuevo, y reiniciá OpenCode |
| Muse Code | las tres líneas `muse plugins` del paso 4, de nuevo |

## 6. Desinstalar

Sacar Athos de un agente nunca borra tu know-how: queda en `~/.athos`.

| Qué | Cómo se saca |
|---|---|
| La extensión de Claude Desktop | desactivá o quitá **Athos** en **Configuración → Extensiones**; quitá la skill en **Personalizar → Skills** |
| El plugin de Claude Code | `/plugin` y quitá athos |
| OpenCode | `athos opencode uninstall`, y reiniciá OpenCode |
| Los hooks de Codex | `athos codex uninstall`; quitá también el plugin de los plugins de Codex |
| Muse Code | quitá el plugin athos de los plugins de Muse Code |
| Los subagentes de trayectoria de un repositorio | `athos wiki agents --uninstall` |
| La copia propia de un proyecto (`.athos/`) | `athos project remove` |
| El comando `athos` | `rm -rf ~/.athos/app ~/.local/bin/athos` |

Para borrar todo, tu know-how incluido, borrá la carpeta `~/.athos`. Si capaz la querés recuperar, copiala antes:
`athos export <carpeta>`.

## 7. Privacidad

Tus formas de trabajar, el registro de lo que decidió Athos y su configuración quedan en `~/.athos`, en tu
computadora, como archivos que podés leer y editar. Athos no tiene servidor ni cuenta, no tiene telemetría y no manda
nada fuera de tu computadora salvo que se lo pidas (compartir con la galería, un modelo en la nube que elegís para
`athos delegate` o `athos bench`). La IA con la que trabajás sí ve lo que le mostrás. En un repositorio que otros
pueden leer, corré `athos public on`: ahí Athos carga y nombra solo las piezas de ese proyecto y no guarda ninguna
palabra de tus pedidos.
