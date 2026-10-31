# Sumá tu forma de trabajar a la galería

La galería muestra formas de trabajar que cualquiera puede llevarse a su Athos con un clic
([mirala](https://athos-agent.github.io/athos/)). Cada una es una página con los pasos que sigue un profesional, y las
ramas que toma solo cuando el caso lo pide. Si tenés un checklist del que estás orgulloso, compartilo acá.
[In English](CONTRIBUTING.md).

## Qué hace buena a una página

- **Una forma de trabajar real de tu área**, escrita como los pasos que seguís de verdad, en el orden en que los
  seguís. Tus criterios y tu formato, no un resumen de manual.
- **Al menos una rama**: un paso que pasa a otra página, siempre (`**Calls:**`) o solo en algunos casos
  (`**If:** <condición> → [[página]]`). Para eso está la galería: mostrar el método abriéndose solo donde el caso lo
  necesita.
- **Ficticia**: sin clientes, personas, empresas, casos ni datos reales.
- **Deja la decisión profesional a la persona**: lista en qué se apoyaría una opinión, nunca la da en su nombre.
- **En inglés y en español**: la misma página en `gallery/en/` y en `gallery/es/`. Si solo podés escribir en uno,
  abrí el pull request igual y avisá: te ayudamos con el otro.
- **Por ahora no se aceptan**: temas médicos o de salud, ni nada que dé un consejo legal, impositivo o de inversión en
  nombre de alguien.

## El formato

Cada página es un archivo markdown con el nombre de su id (`gallery/es/<id>.md`), el mismo formato que Athos guarda en
`~/.athos/know-how/`, más `profession` y `lang`:

```markdown
---
id: verificar-una-fuente
title: Verificar una fuente antes de publicar
when: una fuente da información para una nota y hay que chequearla antes de publicarla
profession: journalism
lang: es
---

## #quien
**When:** con la información de la fuente a mano.
**Do:** anotá quién es la fuente, cómo sabe lo que dice y qué gana si se publica.
**Links:** [[verificar-una-fuente#anonima]]

## #anonima
**When:** con el rol de la fuente claro.
**Do:** anotá si la fuente pide no ser nombrada.
**If:** la fuente es anónima → [[confirmar-dos-veces-una-fuente-anonima]]
**Because:** los lectores no pueden juzgar una fuente anónima, así que la redacción tiene que haberla juzgado por ellos.
```

- `profession` es uno de `law`, `finance`, `journalism`, `science`, `ops`, `sports`, `other`.
- Cada paso (`## #id_del_paso`) tiene **When** y **Do**; **Because** y **Links** cuando ayudan. Los nombres de los
  campos van en inglés, el texto en tu idioma.
- Cada página a la que un paso lleva o pasa tiene que estar también en la galería, en el mismo idioma.

## Empezar desde tu Athos

Si la forma de trabajar ya está en tu Athos, empezá desde ahí: `athos show <id>` la muestra. Copiala en
`gallery/es/<id>.md`, agregale `profession` y `lang`, y sacale la sección `## History`, las líneas `projects`,
`created`, `last_used`, `origin` y `version`, y todo lo que nombre a un cliente, persona o proyecto real.

## Revisarla y enviarla

1. Hacé un fork del repositorio y agregá tus páginas en `gallery/en/` y `gallery/es/`.
2. Regenerá la galería: `python3 bin/athos gallery build` (actualiza `gallery/gallery.json` y `gallery/index.html`).
3. Corré los chequeos: `python3 -m unittest tests.test_gallery` (las páginas se leen bien, los links llevan a páginas
   que existen, cada entrada tiene una rama y los dos idiomas tienen los mismos ejemplos).
4. Abrí un pull request con la plantilla **gallery**. Cuando se mergea, la página de la galería se actualiza sola y
   cualquiera puede agregar tu forma de trabajar con `athos add <id>`.

¿Sin tiempo para un pull request? [Proponé una idea](https://github.com/athos-agent/athos/issues/new?template=gallery-idea.yml)
y contá los pasos con tus palabras.
