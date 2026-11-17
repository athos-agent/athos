# Por qué existe Athos

*English: [WHY.md](WHY.md)*

## El know-how que armás con la IA todavía no es tuyo

Ahora uso agentes de programación para casi todo, y la mayor parte no es software. Una tarea que empieza como
«publicá este paquete», «mové estos registros» o «fijate por qué ese dispositivo dejó de reportar» termina escribiendo
código, corriendo herramientas y hablando con máquinas en el camino. Después de unas semanas te das cuenta de que el
resultado real no es el código. Es el know-how: los pasos que funcionaron, la convención que nadie escribió, el error
que no vas a volver a cometer.

Ese know-how vive en un chat, dentro de un agente. Abrís una sesión nueva y desapareció. Cambiás de agente y explicás
todo desde cero. El modelo ayudó a construirlo, pero de la sesión nunca sale nada que puedas leer, editar o llevarte.

Choqué contra la pared una noche: después de un buen trabajo intenté que el agente escribiera lo que habíamos
descubierto, y el intento quedó marcado como destilación. Razonable del lado del proveedor del modelo. Pero volvió
concreta la pregunta: ¿de quién es este conocimiento, y dónde vive?

## Por qué ningún laboratorio va a construir esto

Cada laboratorio tiene una buena razón para dejar tu know-how en su plataforma. Las funciones de memoria son reales, y
mejoran, pero cada una recuerda para su propio agente, en su propio formato, en sus propios servidores. Ninguna tiene
motivos para que lo que le enseñaste funcione igual de bien en el agente de la competencia, ni para avisarte que un
modelo más barato hace tu tarea igual de bien.

Así que la capa tiene que ser neutral, y tiene que ser tuya: archivos markdown simples en tu máquina, que cualquier
agente puede leer, que podés abrir en un editor y que nada sube a ningún lado salvo que vos los muevas.

## Qué hace Athos

- **Captura.** Cuando una tarea en Claude Code enseña algo reusable, Athos le pide al agente que lo escriba como una
  *pieza*: cuándo aplica, y los pasos, los criterios y los errores a evitar, con las palabras que funcionaron. Cada
  reuso puede mejorar la pieza, con un historial de versiones.
- **Lleva.** Las mismas piezas se cargan en Codex y en Muse Code (como skills que leen los dos), así que el siguiente
  agente hace la tarea con un pedido de una línea en vez de una página de instrucciones.
- **Mide, sobre tu trabajo.** Los benchmarks miden las pruebas de otros. Athos registra cada tarea que corrés, con
  cualquier agente y modelo, y vos marcás cada una como bien, corregida o fallida. Por pieza y por agente muestra la
  tasa de éxito y cuánto más cortos se volvieron tus pedidos comparados con la primera vez.
- **Delega.** Una tarea que ya dominás puede ir a un modelo más chico y más barato, en tu propia máquina o a través de
  Meta Model API, en el propio ciclo chico de Athos, que pregunta antes de cada comando.

## Cómo se ve hoy

En la tarea de la demo (publicar un paquete chico de Python: dos strings de versión, una entrada arriba en el
changelog, un test para la opción nueva, un commit y un tag anotado), el primer pedido, el que enseña las convenciones,
tiene 440 caracteres. Después, Claude Code, Codex y Muse Code hicieron cada uno la siguiente publicación con un pedido
de 80 caracteres, sin explicar nada: 82% más corto, todas marcadas como bien.

Delegada a Muse Spark a través de Meta Model API, la misma publicación tardó 13 segundos. En mi primera medición costó
unos US$0,04, contra US$0,22 del agente frontier haciéndola: más o menos la quinta parte, con el mismo resultado. Más
barato, no más rápido: el agente frontier fue igual de rápido. Un modelo local chico también llegó, gratis y varias
veces más lento. Son corridas sueltas, todavía no un benchmark; `athos bench`, que repite cada tarea varias veces por
modelo, es lo próximo que estoy construyendo.

## Por qué ahora

Cambiaron tres cosas a la vez. Los agentes de programación se volvieron de uso general: ahora hacen trabajo cotidiano
en cualquier área, y eso hace que valga la pena guardar el know-how que acumulan. Hay varios agentes serios, así que
quedar atado a uno pasó a ser un costo real. Y los modelos más chicos se volvieron lo bastante buenos para tareas que
ya dominás, si reciben tu know-how junto con el pedido.

## Lo que no está resuelto

- **Cargar es comparar palabras.** Una pieza se carga cuando el pedido usa las mismas palabras que su título y su
  «when» (no solo palabras que empiezan igual), así que rara vez trae una que no corresponde, pero puede perderse una
  pieza que el pedido describe con otras palabras.
- **Los números son tempranos.** Una tarea, un puñado de corridas. Prefiero mostrar eso a redondearlo para arriba.
- **Las marcas las ponés vos.** Nada inventa un veredicto: una tarea que no marcás queda sin evaluar.

## La apuesta

Si los agentes siguen mejorando, lo escaso no es el modelo, es lo que les enseñaste sobre cómo trabajás. Eso debería
ser un archivo tuyo, que se mueve con vos y que te dice, sobre tus propias tareas, por qué modelo vale la pena pagar.

Athos es una alfa temprana y open source bajo Apache 2.0. Probalo en una tarea real, contame qué se rompe y abrí un
issue con lo que querrías que haga: https://github.com/athos-agent/athos

## Agradecimientos

La charla de Garry Tan en Startup School 2026 ([video](https://www.youtube.com/watch?v=eRrc1pUY5oU)) plantea la idea
sobre la que está construido Athos: las skills que les enseñás a los agentes deberían ser tuyas, y cada tarea debería
dejar una. También empujó a Athos a mantener limpia su memoria, buscando consejos que se contradicen y proponiendo qué
retirar (0.1.23). Gracias por compartir estas ideas abiertamente. Si querés una biblioteca personal de skills, vale la
pena mirar su GBrain; Athos se enfoca en medir qué skills funcionan, en qué agente y modelo, y en pasarles las ya
dominadas a modelos más baratos.
