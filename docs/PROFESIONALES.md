# Athos para profesionales (abogacía, entrenamiento deportivo y cualquier oficio)

No hace falta programar. Si sabés explicarle a un colega nuevo cómo hacés tu trabajo, ya sabés usar Athos.

## Qué hace, en una frase

Cada vez que trabajás con una IA (Claude, Codex, Muse Code de Meta u OpenCode), le explicás cómo hacés las cosas: tu checklist, tu
formato, lo que nunca hay que olvidar. Athos guarda esas **formas de trabajar** como archivos de texto tuyos, en tu
computadora, y se las da a la IA la próxima vez, para que no tengas que repetirlas.

## Empezar sin terminal (recomendado)

1. Instalá **Claude Desktop** y entrá con tu cuenta.
2. Abrí la pestaña **Code** y elegí la carpeta donde están los documentos con los que vas a trabajar (una carpeta
   de prueba, al principio).
3. Escribí en el chat:
   ```
   /plugin install athos --marketplace athos-agent/athos
   ```
   y reiniciá Claude Desktop cuando te lo pida.
4. Pedile a Claude, con tus palabras: *«Corré `athos start --lang es --profile law`»* (o `--profile sports`, u
   `other` para otra profesión). Eso agrega formas de trabajar de ejemplo de tu profesión y te dice cómo seguir.

Athos necesita Python 3, que en una Mac se instala solo la primera vez que algo lo pide (aceptá la instalación de las
herramientas de línea de comandos).

## Empezar desde una terminal

Si ya usás `claude`, `codex`, `muse` u `opencode` en una terminal:

```
curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
athos start
```

`athos start` te pregunta el idioma y tu profesión. Para Muse Code y OpenCode, instalá también su plugin (los comandos
están en el [README](../README.md#install)). Después abrí la herramienta en la carpeta de tus documentos: Athos
funciona igual en las cuatro.

**Guías paso a paso:** [para abogados](guides/abogado.md) · [para entrenadores](guides/entrenador.md) ·
[tu checklist es know-how](guides/checklist.md).

## El día a día

- **Pedí como le pedirías a un colega.** *«Revisá este contrato con mi checklist»*, *«Planificá la semana de este
  atleta con mis reglas»*. Si Athos tiene una forma de trabajar para eso, la IA la sigue sola.
- **La primera vez, explicá.** Cuando una tarea no tiene todavía su forma de trabajar, explicale a la IA cómo la
  hacés. Al terminar, Athos le pregunta si vale la pena guardarla, y queda para la próxima. Si trabajaste con un
  checklist, pregunta siempre: un checklist es know-how valioso.
- **Sabés qué método se aplica.** Cuando una forma de trabajar tuya coincide con el pedido, la IA arranca diciendo
  cuál sigue y cómo la aplica a este caso.
- **Marcá cómo salió.** Después de cada tarea aparecen tres botones: **Salió bien**, **Lo corregí**, **Falló**. Con
  esas marcas Athos sabe qué formas de trabajar te sirven y en qué modelo.
- **Cambialas cuando quieras.** Son archivos de texto en `~/.athos/know-how`. Abrilos con cualquier editor (o con
  [Obsidian](https://obsidian.md), donde se ven como una wiki) y escribí tu manera de hacer las cosas. Cada cambio
  guarda la versión anterior.

## Los ejemplos que trae

Son formas de trabajar genéricas para empezar, **no son asesoramiento legal**: todas dejan las decisiones
profesionales en tus manos y le piden a la IA que pregunte en vez de decidir.

| Profesión | Forma de trabajar |
|---|---|
| Abogacía | Armar el argumento de un escrito según el auditorio (a quién convencer, premisas acordadas, técnicas, objeciones, orden) |
| Abogacía | Revisar un contrato con tu checklist (cláusula por cláusula, tabla de observaciones) |
| Entrenamiento | Planificar la semana de entrenamiento con tus reglas (cargas calculadas con código, objetivo, días duros, descanso después de la tirada larga) |
| Entrenamiento | Escribir el informe post partido en tu formato (números con su fuente, tres cosas bien y tres a corregir) |

Reemplazalas por las tuyas: la mejor forma de trabajar es la que ya usás.

## Tus datos

- **Tus formas de trabajar no salen de tu computadora.** Athos no tiene servidor ni cuenta; no envía nada.
- **La IA sí ve lo que le mostrás.** Claude, Codex, Muse y los modelos de OpenCode procesan en la nube los documentos que abrís en la sesión.
  Con datos de clientes o datos personales: anonimizá (sin nombres, documentos ni fechas de nacimiento) o usá un modelo que
  corre en tu computadora, sin internet (`athos delegate`, con [Ollama](https://ollama.com)).
- **Muse Code:** dejá apagado el modo *Contributor* (`/settings`), salvo que quieras que Meta entrene con tus sesiones.
- La responsabilidad profesional sigue siendo tuya: la IA propone, vos decidís y firmás.
