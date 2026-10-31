---
id: analizar-un-experimento-de-forma-reproducible
title: Analizar los datos de un experimento para que otro laboratorio pueda repetirlo
when: analizar los datos de un experimento o una campaña de mediciones (resultados de laboratorio, secuenciación, sensores, ensayos de materiales) para un paper, un informe o una decisión, de modo que el mismo análisis se pueda volver a correr sobre otros datos
---

## #crudos_intactos
**When:** antes de tocar los datos.
**Do:** copiá los archivos crudos a una carpeta donde el análisis nunca escribe, y anotá sus nombres, tamaños y checksums. Todo el trabajo se hace en un script, nunca a mano en una planilla.
**Because:** un resultado que no se puede rastrear hasta datos crudos intactos no se puede reproducir.
**Links:** [[analizar-un-experimento-de-forma-reproducible#reglas_de_limpieza]]

## #reglas_de_limpieza
**When:** al limpiar los datos.
**Do:** aplicá MIS reglas, escritas antes de mirar los resultados. Ejemplos para reemplazar por las tuyas: descartar las corridas cuyo control falló; marcar como atípicos los puntos a más de 3 desvíos absolutos de la mediana, e informarlos, nunca borrarlos en silencio; el límite de detección del instrumento es el piso.
**Because:** las pequeñas decisiones de limpieza que los papers omiten son donde se pierde la reproducibilidad; decidirlas después de ver el resultado es como se cuela el sesgo.
**Links:** [[analizar-un-experimento-de-forma-reproducible#analisis]]

## #analisis
**When:** con los datos limpios.
**Do:** calculá con código el análisis planificado, con todos los parámetros en un solo lugar al principio del script (semilla, umbrales, versiones de las librerías). Mostrá tamaños de efecto con sus intervalos, no solo valores p.
**Because:** la aritmética se hace con código; un parámetro escondido en una celda es un parámetro que nadie puede repetir.
**Links:** [[analizar-un-experimento-de-forma-reproducible#control]]

## #control
**When:** con los resultados.
**Do:** volvé a correr el script entero desde la copia cruda en una carpeta limpia y confirmá que los números son idénticos. Listá qué se excluyó y por qué.
**Links:** [[analizar-un-experimento-de-forma-reproducible#paquete]]

## #paquete
**When:** con el análisis final.
**Do:** dejá juntos el script, los parámetros, la lista de exclusiones y esta forma de trabajar, para que otro laboratorio pueda correr el mismo método sobre sus datos. Qué significan los resultados y qué afirmar lo decide la persona.
**Because:** un método que viaja con el paper es un protocolo que otros pueden usar, no un relato que tienen que creer.
