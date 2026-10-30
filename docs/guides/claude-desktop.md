# Athos en Claude Desktop: tu know-how en el chat, con su panel

*English: [claude-desktop-en.md](claude-desktop-en.md)*

Este tutorial es para quien usa el **chat** de Claude Desktop (no la pestaña Code). No hace falta programar ni escribir
comandos. Al terminar, cada vez que le pidas algo a Claude:

1. Athos busca **tu** forma de hacer esa tarea y Claude la sigue.
2. Se abre un **panel** en la conversación que muestra, paso por paso, cómo Claude recorre tu forma de trabajar, como
   cuando muestra lo que va pensando.
3. Desde el panel podés **ajustar un paso** o **guardar los pasos nuevos**, y la próxima vez Claude ya los sabe.

Todo queda en tu computadora, en la carpeta `~/.athos`, como texto que podés leer y editar. Nada se manda a ningún
servidor de Athos.

## 1. Lo que necesitás

- **Claude Desktop** en Mac (o Linux), con tu cuenta.
- **Python 3**, que la Mac ya trae. Si es la primera vez que se usa, la Mac puede pedirte instalar las "herramientas de
  línea de comandos": aceptá.
- El archivo **`athos.mcpb`**, la extensión de Athos para Claude Desktop. Quien te pasó Athos te lo puede mandar; si ya
  tenés Athos instalado en la terminal, `athos desktop` lo crea en la carpeta `dist/` de Athos.

## 2. Instalar (2 minutos)

1. Hacé **doble clic** en `athos.mcpb`. Claude Desktop se abre y te muestra la extensión: tocá **Instalar**.
   (También podés arrastrar el archivo a Claude Desktop → **Configuración → Extensiones**.)
2. Verificá que **Athos** aparezca activado en **Configuración → Extensiones**.
3. Abrí un **chat nuevo**. Los chats que ya estaban abiertos no ven la extensión.

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

## 4. Pedir algo y mirar el panel

Escribí un pedido que coincida con una forma de trabajar tuya:

> Revisá este contrato de locación: [texto]

Antes de empezar, Claude consulta a Athos y se abre el **panel de trayectoria** en la conversación:

```
Buen día, Matías
1 forma de trabajar lista

«Revisar un contrato de locación» v1 · 1/4 pasos · coincidió: contrato, locación
 ✓ #partes-y-plazo
 ▶ #actualizacion
   revisar la cláusula de actualización del alquiler
 ○ #rescision
 ○ #tabla-de-riesgos
 + nuevo: verificar la garantía
Subagentes: …   Skills: …

[ Ajustar paso ]  [ Guardar pasos nuevos ]          [ Fijar al costado ]  [ Pantalla completa ]
```

- **✓** paso hecho, **▶** el paso en el que está Claude ahora (con lo que hace), **○** lo que falta.
- **+ nuevo:** un paso que la tarea necesitó y tu forma de trabajar todavía no tiene.
- **coincidió:** las palabras de tu pedido que hicieron que Athos eligiera esa forma de trabajar.
- El panel se actualiza solo mientras Claude avanza.
- Si no hay ninguna forma de trabajar para el pedido, el panel lo dice y va armando una nueva con los pasos que da Claude.

El panel habla el idioma en el que escribís, español o inglés.

## 5. Corregir y mejorar sin escribir comandos

- **[Ajustar paso]**: se abre un campo debajo del panel. Escribí cómo tiene que cambiar el paso en el que está Claude
  (por ejemplo *«además, comparar con el índice ICL»*) y tocá **Enviar**. Va al chat como mensaje tuyo; Claude mejora
  tu forma de trabajar (queda una versión nueva) y sigue la tarea con el cambio.
- **[Guardar pasos nuevos]**: aparece cuando hubo pasos **+ nuevo**. Claude guarda la tarea con esos pasos incluidos.
- **[Fijar al costado]** y **[Pantalla completa]**: aparecen solo si tu versión de Claude Desktop permite mover el
  panel. Con **Fijar al costado** el panel queda a la vista mientras seguís conversando.

Claude Desktop puede pedirte que confirmes antes de mandar al chat un mensaje del panel o antes de usar una herramienta
de Athos. Es normal.

## 6. Ver y editar tu know-how

Cada forma de trabajar es un archivo de texto en `~/.athos/know-how/` (en Finder: **Ir → Ir a la carpeta…** y pegás
`~/.athos/know-how`). Podés abrirlo con cualquier editor. Cada paso tiene **Cuándo**, **Qué hacer** y **Por qué**.

También podés pedirle a Claude en el chat:

> Mostrame mis formas de trabajar.

> Mostrame la forma de trabajar «revisar un contrato de locación».

## 7. Si algo no se ve

| Lo que pasa | Qué hacer |
|---|---|
| No aparece el panel, pero Claude sigue tu forma de trabajar | Tu versión de Claude Desktop todavía no dibuja paneles de extensiones. Athos funciona igual, en texto. Actualizá Claude Desktop. |
| Claude no consulta a Athos | Empezá un chat nuevo, o pedíselo: *«usá mi know-how de Athos para esto»*. En el chat, Claude decide cuándo usar sus herramientas. |
| El panel no avanza mientras Claude trabaja | Se actualiza cada vez que Claude marca un paso. Si tu Claude Desktop no deja que el panel consulte a Athos solo, se ve al final del paso. |
| Elige una forma de trabajar que no corresponde | Decíselo a Claude (*«esa no aplica»*). Para que no vuelva a pasar, ajustá el **Cuándo** de esa forma de trabajar en su archivo. |
| La extensión no arranca | Revisá que la Mac tenga Python 3 (la primera vez puede pedir instalar las herramientas de línea de comandos). |

## Privacidad

- Tus formas de trabajar y el historial del panel quedan en `~/.athos`, en tu computadora.
- Athos no manda nada a ningún servidor. Lo que escribís en el chat lo procesa Claude, como siempre.
- No pongas en una forma de trabajar datos de clientes ni contraseñas: guardá **cómo** trabajás, no **con qué** datos.
