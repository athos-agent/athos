---
id: analizar-una-inversion-con-las-reglas-de-mi-comite
title: Analizar una inversión con las reglas de mi comité
when: un cliente trae una inversión, un fondo, un fideicomiso o una operación inmobiliaria para analizar; preparar la tabla de riesgos y rendimiento neto que un asesor o contador revisa antes de dar su opinión
profession: finance
lang: es
---

## #datos_afuera
**When:** antes de pegar el prospecto o los datos del cliente.
**Do:** preguntá si el material tiene la identidad del cliente, números de cuenta o identificaciones fiscales; si los tiene, proponé sacarlos, pasar la tarea por [[connector:pii-guard]] o usar un modelo local.
**Because:** un modelo en la nube ve todo lo que se le muestra; los datos financieros del cliente son confidenciales.
**Links:** [[analizar-una-inversion-con-las-reglas-de-mi-comite#hechos]]

## #hechos
**When:** con el material a mano.
**Do:** resumí en cinco líneas: qué se compra, el vehículo, la moneda, el plazo y la salida, los costos (entrada, administración, salida). Decí qué falta.
**Links:** [[analizar-una-inversion-con-las-reglas-de-mi-comite#jurisdicciones]]

## #jurisdicciones
**When:** con los hechos claros.
**Do:** anotá en qué países están el inversor, el activo y el vehículo.
**If:** no están todos en el mismo país → [[revisar-el-tratamiento-fiscal-entre-paises]]
**Because:** el rendimiento neto de una inversión entre países depende de tratados y retenciones que el prospecto nunca muestra.
**Links:** [[analizar-una-inversion-con-las-reglas-de-mi-comite#numeros]]

## #numeros
**When:** con los hechos y el tratamiento fiscal.
**Do:** calculá con código el rendimiento neto después de costos e impuestos en tres escenarios (malo, esperado, bueno) con los supuestos de MI comité (ejemplos para reemplazar por los tuyos: inflación, camino del tipo de cambio, vacancia en inmuebles). Mostrá las fórmulas.
**Because:** la aritmética se hace con código; los supuestos son del comité, no del prospecto.
**Links:** [[analizar-una-inversion-con-las-reglas-de-mi-comite#riesgos]]

## #riesgos
**When:** con los números hechos.
**Do:** una tabla: riesgo, qué tan probable, cuánto cuesta, cómo mitigarlo (liquidez, moneda, contraparte, concentración, legal). Después, las preguntas abiertas para el cliente.
**Because:** esta es la tabla que lee el comité.
**Links:** [[analizar-una-inversion-con-las-reglas-de-mi-comite#opinion]]

## #opinion
**When:** con la tabla lista.
**Do:** dejá la recomendación a la persona: listá en qué se apoyaría una opinión, nunca la des en su nombre.
**Because:** el asesoramiento financiero e impositivo es responsabilidad del profesional matriculado.
