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

## 4. Pedir algo y mirar el panel

Escribí un pedido que coincida con una forma de trabajar tuya:

> Revisá este contrato de locación: [texto]

Antes de empezar, Claude consulta a Athos y se abre un **panel de Athos** chico en la conversación. Mientras Claude
sigue una de tus formas de trabajar, muestra:

```
■ Athos está colaborando                      (verde)
Revisar un contrato de locación
 ✓ Revisar partes y plazo
 ▶ Revisar la cláusula de actualización   [ Cambiar este paso ]
 ○ Revisar la rescisión
 ○ Armar la tabla de riesgos
```

- **✓** paso hecho, **▶** el paso en el que está Claude ahora, **○** lo que falta. Un paso que lleva a otra forma de
  trabajar tuya muestra sus pasos con sangría debajo, marcados *tomado* o *no hizo falta*.
- El panel se actualiza solo mientras Claude avanza.

Si ninguna forma de trabajar corresponde al pedido, Claude anota los pasos que da, y el panel los muestra como una
forma de trabajar nueva en borrador:

```
■ Athos está aprendiendo                      (rojo)
 ✓ Leer las cláusulas
 ▶ Verificar la garantía
[ Guardar como forma de trabajar ]
```

Si no corresponde nada y no se está armando nada, el panel queda vacío. Cuando la tarea termina, el cuadrado se va.
El panel habla el idioma en el que escribís, español o inglés.

## 5. Corregir y mejorar sin escribir comandos

- **[Cambiar este paso]**: se abre un campo. Escribí cómo tiene que cambiar el paso en el que está Claude (por ejemplo
  *«además, comparar con el índice ICL»*) y tocá **Enviar**. Athos lo escribe en ese paso de tu forma de trabajar
  (queda una versión nueva) y va al chat como mensaje tuyo, así Claude sigue la tarea con el cambio.
- **[Guardar como forma de trabajar]**: aparece cuando hubo pasos nuevos, también después de terminar la tarea. Athos
  los guarda como forma de trabajar tuya: una nueva con el nombre de tu pedido, o pasos nuevos agregados a la que
  siguió Claude.

En el chat solo guardan estos dos botones: Claude mismo nunca guarda tus formas de trabajar ahí.

¿Querés el panel anterior, más grande (saludo, estrellas en cada paso, un resumen al final, **Fijar al costado**)?
Agregá `"ui": "classic"` en `~/.athos/config.json`.

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
