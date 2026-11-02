---
id: responder-tickets-de-soporte-con-tu-politica
title: Responder tickets de soporte con la política de tu equipo
when: responder los tickets de soporte del día (devoluciones, cancelaciones, pedidos demorados, cobros dobles, amenazas de contracargo) antes de que salgan las respuestas
profession: ops
lang: es
bench: support-tickets
measured: "5/5 con esta página, 0/5 sin ella"
---

## #plazo_de_devolucion
**When:** un cliente pide devolver un producto.
**Do:** contar el plazo de devolución (ejemplo: 30 días) desde la fecha de entrega, nunca desde la de compra. Dentro del plazo, devolver el precio del producto; el envío, solo si llegó dañado o roto.
**If:** el ticket amenaza con un contracargo, defensa del consumidor o un abogado → [[responder-tickets-de-soporte-con-tu-politica#escalar]]
**Because:** alguien que compró hace más de un mes puede seguir dentro del plazo; el envío se devuelve solo cuando la falla es nuestra.
**Links:** [[responder-tickets-de-soporte-con-tu-politica#planes]]

## #planes
**When:** un cliente cancela una suscripción.
**Do:** un plan anual devuelve los meses enteros que no usó, contando el mes en curso como usado. Un plan mensual nunca se devuelve: sigue activo hasta el fin del mes pagado; decir hasta cuándo.
**Because:** es la política del equipo; devolver un plan mensual es una decisión que soporte no toma.
**Links:** [[responder-tickets-de-soporte-con-tu-politica#escalar]]

## #escalar
**When:** un ticket amenaza con un contracargo, una denuncia en defensa del consumidor o un abogado.
**Do:** no decidirlo: pasarlo a quien lidera soporte, no devolver nada y avisarle al cliente que le van a responder en un día hábil, sin prometer la devolución.
**Because:** esos tickets tienen un riesgo que es de quien lidera.
**Links:** [[responder-tickets-de-soporte-con-tu-politica#demoras]]

## #demoras
**When:** un pedido está demorado o sigue en camino.
**Do:** nunca prometer una fecha ni un día («mañana», «el viernes»); decir que volvemos a escribir dentro de las 24 horas hábiles con la novedad del correo. Si es la segunda demora del cliente en 90 días, darle un crédito en la tienda (ejemplo: 10 % del precio del producto).
**Because:** una fecha prometida que el correo no cumple es un segundo reclamo.
**Links:** [[responder-tickets-de-soporte-con-tu-politica#datos_de_tarjeta]]

## #datos_de_tarjeta
**When:** un cliente manda un número de tarjeta o pregunta por un cobro.
**Do:** nunca repetir el número, ni siquiera en el resumen interno. Pedirle que nunca mande números de tarjeta y pedir solo los últimos cuatro dígitos y la fecha del cobro.
**If:** muchos clientes reportan el mismo cobro erróneo → [[avisar-a-clientes-de-un-incidente-de-pagos]]
**Because:** los números de tarjeta no se guardan en tickets ni en resúmenes.
**Links:** [[responder-tickets-de-soporte-con-tu-politica#firma]]

## #firma
**When:** cada respuesta está escrita.
**Do:** responder en el idioma del cliente y cerrar con la firma del equipo en una línea aparte (ejemplo: `— Equipo de soporte`). Escribir un resumen corto para quien lidera soporte con los escalados.
**Because:** quien lidera lee el resumen; el cliente lee una sola voz.
