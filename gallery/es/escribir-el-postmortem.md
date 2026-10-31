---
id: escribir-el-postmortem
title: Escribir el postmortem de un incidente
when: un incidente está resuelto y el equipo escribe qué pasó, por qué y qué lo va a evitar
profession: ops
lang: es
---

## #cronologia
**When:** con el servicio normal otra vez.
**Do:** escribí la cronología con horarios (detección, escalamiento, contención, causa encontrada, arreglo, normalidad), sacada del canal del incidente y de las herramientas, no de memoria.
**Links:** [[escribir-el-postmortem#causa]]

## #causa
**When:** con la cronología.
**Do:** nombrá la causa y la trampa detrás (por qué nada la detectó antes). Sin culpables: sistemas y decisiones, no personas.
**Links:** [[escribir-el-postmortem#acciones]]

## #acciones
**When:** con la causa escrita.
**Do:** acordá como mucho tres acciones que lo eviten o lo detecten antes, cada una con responsable y fecha.
**Because:** un postmortem con diez acciones no termina ninguna.
