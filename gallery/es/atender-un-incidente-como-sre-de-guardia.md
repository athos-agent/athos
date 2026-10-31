---
id: atender-un-incidente-como-sre-de-guardia
title: Atender un incidente como SRE de guardia
when: saltó una alerta o los usuarios reportan errores, lentitud o una caída en producción, y quien está de guardia tiene que contenerlo y encontrar la causa
profession: ops
lang: es
---

## #alcance
**When:** al reportarse el incidente.
**Do:** escribí en tres líneas qué falla, desde cuándo y para quién; fijá la severidad con la escala del equipo (ejemplo para reemplazar por la tuya: SEV1 todos los usuarios, SEV2 una función o región, SEV3 degradado).
**Links:** [[atender-un-incidente-como-sre-de-guardia#pagos]]

## #pagos
**When:** con el alcance claro.
**Do:** fijate si el checkout, los cobros o la facturación están entre lo que falla (la tasa de errores de los endpoints de pago, la página de estado del proveedor de pagos).
**If:** afecta los pagos → [[avisar-a-clientes-de-un-incidente-de-pagos]]
**Because:** los clientes que no pueden pagar o cobrar tienen que enterarse por nosotros primero, y soporte y finanzas necesitan las mismas palabras.
**Links:** [[atender-un-incidente-como-sre-de-guardia#contener]]

## #contener
**When:** con el alcance y la severidad.
**Do:** proponé la contención segura más rápida (volver atrás el último deploy, apagar el flag, pasar al respaldo) y preguntale a la persona antes de correr cualquier cosa que cambie producción.
**Because:** un cambio en producción es decisión de quien está de guardia, nunca del agente.
**Links:** [[atender-un-incidente-como-sre-de-guardia#causa]]

## #causa
**When:** con el daño contenido.
**Do:** listá qué cambió en la hora previa al primer error (deploys, configuración, flags, certificados por vencer, tráfico) desde las herramientas, y confirmá o descartá cada candidato con una línea de log o una métrica citada.
**Because:** una causa sin probar manda al equipo a arreglar lo que no era.
**Links:** [[atender-un-incidente-como-sre-de-guardia#cierre]]

## #cierre
**When:** con el servicio normal otra vez.
**Do:** dejá escrito qué pasó y qué lo evita la próxima vez.
**Calls:** [[escribir-el-postmortem]]
