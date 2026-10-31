---
id: atender-un-incidente-en-produccion
title: Atender un incidente en producción donde suelen estar las trampas
when: un servicio está caído, lento o dando errores en producción; saltó una alerta o los usuarios reportan una falla, y hay que encontrar la causa y contener el daño antes que nada
---

## #contener_primero
**When:** apenas se reporta el incidente.
**Do:** escribí en tres líneas qué falla, desde cuándo y a quién afecta (todos, una región, un cliente). Proponé la contención segura más rápida (volver atrás el último deploy, apagar el feature flag, pasar al respaldo) y preguntale a la persona antes de correr cualquier cosa que cambie producción.
**Because:** frenar el daño va antes que entenderlo; un cambio en producción lo decide quien está de guardia, nunca el agente.
**Links:** [[atender-un-incidente-en-produccion#que_cambio]]

## #que_cambio
**When:** con el daño contenido, o si todavía no se puede contener.
**Do:** listá todo lo que cambió en la hora anterior al primer error: deploys, cambios de configuración y de flags, certificados y claves vencidos, migraciones de base de datos, picos de tráfico, el estado de las dependencias. Leelo de las herramientas (registro de deploys, git log, la página de estado del proveedor), no de memoria.
**Because:** la mayoría de los incidentes viene después de un cambio; los que no, suelen ser un vencimiento (certificado, token, cuota) del que nadie se acordaba.
**Links:** [[atender-un-incidente-en-produccion#evidencia]]

## #evidencia
**When:** con la lista de cambios.
**Do:** confirmá o descartá cada candidato con evidencia: tasa de errores y latencia por versión, la primera línea de log de la falla, un pedido que la reproduce. Citá las líneas; nunca concluyas de un tablero que no leíste.
**Because:** una causa verosímil sin probar manda al equipo a arreglar lo que no era.
**Links:** [[atender-un-incidente-en-produccion#arreglo]]

## #arreglo
**When:** con la causa probada.
**Do:** proponé el arreglo más chico y cómo verificarlo en producción (qué métrica tiene que volver a la normalidad y por cuánto tiempo). La persona lo aprueba y lo corre.
**Links:** [[atender-un-incidente-en-produccion#postmortem]]

## #postmortem
**When:** con el servicio normalizado.
**Do:** escribí la línea de tiempo (detección, contención, causa, arreglo, con horas), la trampa que lo causó y una acción que evite que vuelva a pasar, con responsable. Sin culpas: sistemas y decisiones, no personas.
**Because:** lo que un ingeniero aprendió a los golpes es know-how del equipo solo si queda escrito donde el próximo lo va a encontrar.
