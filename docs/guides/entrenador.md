# Guía para entrenadores: tu método, en todas tus herramientas de IA

*English: [coach.md](coach.md)*

Esta guía es para quien entrena atletas o equipos y quiere que la IA planifique y escriba informes **con su método**,
no con reglas genéricas. No hace falta programar.

## Lo que vas a lograr

1. La IA planifica la semana con **tus reglas**: cómo calculás la carga, cuándo bajás, cuántos días duros, qué va
   después de la tirada larga.
2. Las explicás **una sola vez**. La próxima vez basta con *«planificá la semana de Juan»*.
3. Lo mismo funciona en **Claude**, en **Muse Code de Meta**, en **OpenCode** (con el modelo que elijas) y en
   **Codex**.
4. Las decisiones que son del atleta (una carrera de prueba, el ritmo objetivo) quedan abiertas, como vos las dejarías.

## Por qué vale la pena: lo medimos

Le pedimos a Muse Spark, el modelo de Meta, que planifique la semana de un atleta a partir de cuatro semanas de
registro. **Con** el método del entrenador guardado en Athos: 3 de 3 planes bien, los 9 pasos cumplidos. **Sin** él:
0 de 3. Sin el método, nunca bajó la carga después de una semana con un pico, que es justo lo que un entrenador no se
olvida. (Caso `training-week` del bench público; 3 corridas por brazo.)

## 1. Instalar (10 minutos, sin terminal)

1. Instalá **Claude Desktop** y entrá con tu cuenta.
2. Creá una carpeta, por ejemplo `Atletas`, con el registro de un atleta (una planilla exportada como CSV: fecha,
   tipo de sesión, minutos, esfuerzo percibido del 1 al 10).
3. En Claude Desktop abrí la pestaña **Code**, elegí esa carpeta y escribí:
   ```
   /plugin install athos --marketplace athos-agent/athos
   ```
   Reiniciá cuando te lo pida.
4. Escribile a Claude: *«Corré `athos start --lang es --profile sports`»*. Eso agrega dos formas de trabajar de
   ejemplo: **planificar la semana de entrenamiento** y **escribir el informe post-partido**.

## 2. Tu primera planificación: enseñale tus reglas

La primera vez, escribí tus reglas como se las dirías a un ayudante:

```
Planificá la semana que viene para el atleta de atleta.json con el registro de log.csv.
Mis reglas:
- carga de cada sesión = minutos × esfuerzo (1 a 10); calculala con código, no a ojo
- si la última semana supera 1,3 veces el promedio de las cuatro, la próxima baja 10%; si no, sube 10% como máximo
- máximo dos días duros (esfuerzo 7 o más) y nunca seguidos
- una sola tirada larga; el día siguiente, descanso o muy suave
- carrera de prueba y ritmo objetivo los decide el atleta: dejalos como preguntas
```

Lo que vas a ver:

- La IA arranca diciendo qué forma de trabajar sigue y cómo la aplica a este atleta.
- Calcula las cargas con código, y no de memoria, y te muestra los números.
- Mientras trabaja, debajo del cuadro de texto aparecen los pasos que sigue, en orden.
- Al terminar, como la tarea siguió una lista de reglas, Athos le pregunta a la IA si vale la pena guardarla. Tus
  reglas quedan como forma de trabajar.

La próxima vez: *«Planificá la semana de Juan»*.

## 3. El informe post-partido

Lo mismo con tu formato de informe: *«Escribí el informe del partido con stats.csv y mis notas»*. La forma de trabajar
de ejemplo pide números con su fuente, tres cosas bien y tres a corregir, y deja las decisiones de equipo en tus manos.
Cambiala por tu formato.

## 4. Marcá cómo salió

Después de cada tarea: **Salió bien**, **Lo corregí** o **Falló**. Con esas marcas ves qué forma de trabajar te sirve
y en qué herramienta.

## 5. Lo mismo, en tus otras herramientas

| Herramienta | Cómo se instala |
|---|---|
| Comando `athos` (lo necesitan las de abajo) | `curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh \| sh` |
| **Muse Code** (Meta) | `muse plugins marketplace add athos https://github.com/athos-agent/athos`, después `muse plugins install athos@athos` y `muse plugins approve athos` |
| **OpenCode** (cualquier modelo) | `athos opencode install` y reiniciar OpenCode |
| **Codex** | `codex plugin marketplace add athos-agent/athos` y `codex plugin add athos@athos` |

## 6. Datos de tus atletas

- **Tus formas de trabajar no salen de tu computadora.** Athos no tiene servidor ni cuenta.
- **La IA sí ve lo que le mostrás.** Los registros de entrenamiento pueden incluir datos de salud: usá iniciales en vez
  de nombres, o un modelo que corre en tu computadora (`athos delegate` con [Ollama](https://ollama.com)).
- **Muse Code:** dejá apagado el modo *Contributor* (`/settings`).
- La IA propone y vos decidís: ante una lesión o un síntoma, lo que cuenta es tu criterio y el de un profesional de
  la salud, no el plan.

## 7. Hacelo tuyo

Tus formas de trabajar están en `~/.athos/know-how`. Abrilas con cualquier editor y escribí tu método: tus umbrales,
tus tipos de sesión, tu manera de periodizar. Cada cambio guarda la versión anterior.

¿Un caso de tu deporte que te gustaría ver? Abrí un issue en
[github.com/athos-agent/athos](https://github.com/athos-agent/athos/issues).
