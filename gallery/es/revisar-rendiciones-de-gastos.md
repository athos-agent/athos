---
id: revisar-rendiciones-de-gastos
title: Revisar rendiciones de gastos como el equipo de finanzas
when: revisar las rendiciones de gastos del mes de los empleados (varias monedas, comprobantes, topes de comidas) antes de pagarlas, dejando las excepciones a quien lidera finanzas
profession: finance
lang: es
bench: expense-review
measured: "5/5 con esta página, 0/5 sin ella"
---

## #leer_rendiciones
**When:** con el archivo de rendiciones del mes y los tipos de cambio a mano.
**Do:** tomar cada fila como una rendición y respetar el orden del archivo. Dos rendiciones con el mismo empleado, fecha, monto y moneda son un duplicado: quedarse con la primera y rechazar las siguientes con «duplicado de <primer id>».
**If:** una rendición está en otra moneda → [[revisar-rendiciones-de-gastos#moneda_extranjera]]
**Because:** el mismo comprobante enviado dos veces es el error más común del mes.
**Links:** [[revisar-rendiciones-de-gastos#no_reintegrables]]

## #no_reintegrables
**When:** sin duplicados.
**Do:** rechazar las categorías que la política nunca paga (por ejemplo alcohol o gastos personales, para cambiar por los tuyos).
**Because:** lo decide la política, no el monto.
**Links:** [[revisar-rendiciones-de-gastos#moneda_extranjera]]

## #moneda_extranjera
**When:** una rendición no está en la moneda de la empresa. Este paso no aplica a las que sí lo están.
**Do:** usar el tipo de cambio del mes de la fecha del gasto (un gasto de septiembre usa el de septiembre, aunque se revise en octubre), sumar la comisión de la tarjeta por moneda extranjera (por ejemplo 1,5 %) y redondear a centavos. Desde acá, comparar todos los topes en la moneda de la empresa, nunca en la del gasto.
**Because:** un taxi por debajo del tope en euros puede pasarlo en dólares; la comisión es lo que de verdad pagó el empleado.
**Links:** [[revisar-rendiciones-de-gastos#comprobantes_y_topes]]

## #comprobantes_y_topes
**When:** todos los montos están en la moneda de la empresa.
**Do:** una rendición por encima del tope sin comprobante (por ejemplo 75,00) no se rechaza: se le pide el comprobante al empleado y se paga 0 hasta que llegue. Las comidas se pagan hasta el tope (por ejemplo 60,00 por rendición); si lo pasan, se paga el tope y se dice «tope de 60». El resto se aprueba por su monto.
**Because:** un comprobante que falta es una pregunta para el empleado, no un rechazo.
**Links:** [[revisar-rendiciones-de-gastos#decisiones_abiertas]]

## #decisiones_abiertas
**When:** todas las rendiciones tienen una decisión.
**Do:** sumar lo que se paga a cada empleado. Listar para quien lidera finanzas cada rendición cuya nota pide una excepción y cada una que espera comprobante, por id. La regla se aplica igual (la comida queda con tope): las excepciones las decide quien lidera finanzas, nunca quien revisa.
**Because:** quien revisa aplica la política; quien es dueño de la política decide las excepciones.
