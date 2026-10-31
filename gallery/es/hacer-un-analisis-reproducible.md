---
id: hacer-un-analisis-reproducible
title: Hacer un análisis reproducible
when: analizar datos de un experimento o una encuesta de forma que otra persona obtenga el mismo resultado con los mismos archivos
profession: science
lang: es
---

## #crudos
**When:** al llegar los datos.
**Do:** dejá los archivos crudos de solo lectura y anotá sus nombres, sus checksums y de dónde vienen.
**Links:** [[hacer-un-analisis-reproducible#limpieza]]

## #limpieza
**When:** antes de mirar cualquier resultado.
**Do:** escribí cada regla de limpieza como código (exclusiones, valores atípicos, faltantes), cada una con su motivo.
**Because:** las reglas que se deciden después de ver los resultados los tuercen.
**Links:** [[hacer-un-analisis-reproducible#muestra]]

## #muestra
**When:** con los datos limpios.
**Do:** contá el n por grupo y revisá los supuestos de la prueba prevista (normalidad, igualdad de varianzas).
**If:** n < 30 en algún grupo, o fallan los supuestos → [[elegir-una-prueba-no-parametrica]]
**Because:** con muestras chicas los supuestos de una prueba t no se pueden verificar y su valor p engaña.
**Links:** [[hacer-un-analisis-reproducible#informe]]

## #informe
**When:** con la prueba corrida.
**Do:** informá tamaños de efecto con intervalos de confianza, no solo valores p; el script, las versiones de los paquetes y la semilla van con los resultados.
**Because:** un resultado que nadie puede volver a correr es una anécdota.
