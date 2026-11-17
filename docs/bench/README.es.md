# Resultados del bench, 1 de noviembre de 2026

*English: [README.md](README.md)*

Las corridas en bruto detrás de los números del README, una línea JSON por corrida:
[results-2026-11-01.jsonl](results-2026-11-01.jsonl). Cada línea tiene el caso, el agente y el modelo, si se le dio el
know-how, el veredicto (`g` bien, `f` falló) según la comprobación propia del caso, las etapas hechas, lo que faltó, el
tiempo, los tokens y el costo. Nada de un veredicto viene del agente: el `check.py` de cada caso lee lo que dejó la
corrida (archivos, git, tests).

## Muse Spark de Meta a través de Meta Model API, 5 corridas por brazo

| Caso | Área | Con el know-how | Sin él | Costo por corrida (con) |
|---|---|---|---|---|
| expense-review | operaciones de finanzas, 10 etapas | 5/5 (10/10 etapas) | 0/5 (6/10) | $0.037 |
| tile-plan | un método de planificación, 8 etapas | 5/5 (8/8) | 0/5 (5/8) | $0.022 |
| monthly-report | datos | 5/5 | 0/5 | $0.026 |
| release | código | 5/5 | 2/5 | $0.026 |
| device-setup | dispositivos | 5/5 | 0/5 | $0.008 |
| **Total** | | **25/25** | **2/25** | |

## Los pesos abiertos de Meta: Muse Spark Open a través de OpenRouter, 2 de noviembre, 5 corridas por brazo

`meta/muse-spark-open` (mixture of experts de pesos abiertos, 816B) a través de OpenRouter, que lo sirvió desde
proveedores de inferencia como BaseTen y Fireworks, en el propio ciclo de Athos (`athos bench --agents openrouter`): el
modelo lee los archivos del caso, sigue el know-how paso a paso con herramientas y escribe lo que lee la comprobación.

| Caso | Área | Con el know-how | Sin él | Costo por corrida (con) |
|---|---|---|---|---|
| release | código | 5/5 | 0/5 | $0.020 |
| monthly-report | datos | 5/5 | 0/5 | $0.018 |
| device-setup | dispositivos | 5/5 | 0/5 | $0.010 |
| tile-plan | un método de planificación | 5/5 (8/8 etapas) | 0/5 (5/8) | $0.018 |
| expense-review | operaciones de finanzas | 5/5 (10/10 etapas) | 0/5 | $0.028 |
| contract-transfer | derecho | 5/5 | 0/5 | $0.016 |
| support-tickets | atención al cliente | 5/5 (10/10 etapas) | 0/5 (4/10) | $0.024 |
| **Total** | | **35/35** | **0/35** | |

Las corridas están en [results-2026-11-02-openrouter.jsonl](results-2026-11-02-openrouter.jsonl), con el costo al
precio de lista de OpenRouter (US$1,25 / 4,25 por millón de tokens de entrada y de salida). Para correrlo: una
`OPENROUTER_API_KEY` en `~/.athos/.env`, y después
`athos bench expense-review --agents openrouter --runs 1 --without`.

## Los ejemplos medidos de la galería, 2 de noviembre: Muse Spark a través de Meta Model API, 5 corridas por brazo

| Caso | Quién | Con la página | Sin ella | Lo que les faltó a las corridas sin ella |
|---|---|---|---|---|
| expense-review | un contador | 5/5 (10/10 etapas) | 0/5 (6/10) | el recargo de la tarjeta en los gastos en el exterior, el tope de comidas |
| contract-transfer | un abogado | 5/5 | 0/5 | las columnas y las prioridades de la tabla, la fila de la ley aplicable, `Push first:`, dejarle la decisión al cliente |
| support-tickets | un equipo de soporte | 5/5 | 0/5 (4/10 etapas) | el plazo contado desde la entrega, el envío solo por daños, el crédito por la segunda demora, no prometer fechas, los números de tarjeta, la firma |

Son los tres ejemplos que la [galería](../../gallery/) muestra primero, cada uno con su resultado en la página. Las
corridas están en [results-2026-11-02.jsonl](results-2026-11-02.jsonl).

## Los ejemplos de periodismo y ciencia de la galería, 3 de noviembre: Muse Spark Open a través de OpenRouter, 5 corridas por brazo

| Caso | Quién | Con la página | Sin ella | Lo que les faltó a las corridas sin ella |
|---|---|---|---|---|
| source-check | una redacción | 5/5 (8/8 etapas) | 0/5 (5/8) | el derecho a réplica con su plazo (en todas las corridas), descartar una afirmación cuya segunda fuente la escuchó de la primera o cuya única fuente es un competidor, la descripción de la fuente anónima |
| small-sample | un laboratorio | 5/5 (8/8 etapas) | 0/5 (7/8) | por qué un test no paramétrico (n menor que 30) y la semilla en el informe; una corrida informó medias en vez de medianas. Sin la página el modelo ya elegía Mann-Whitney: acá la diferencia es chica |

Con estos, cada profesión de la galería muestra un resultado medido. $0.021 y $0.033 por corrida con la página. Las
corridas están en [results-2026-11-03-openrouter.jsonl](results-2026-11-03-openrouter.jsonl).

## Los agentes de Meta en la revisión de gastos, 2 corridas por brazo

| Muse Spark vía | Con el know-how | Sin él | Tiempo mediano | Costo por corrida |
|---|---|---|---|---|
| Meta Model API (directo) | 5/5 (10/10 etapas) | 0/5 (6/10) | 16 s | $0.037 |
| Muse Code | 2/2 (10/10) | 0/2 (6/10) | 94 s | $0.49 |
| OpenCode | 2/2 (10/10) | 0/2 (6/10) | 33 s | $0.22 |

Sin el know-how, los tres omiten las mismas etapas: el recargo de la tarjeta en los gastos en el exterior y el tope de
comidas (y, por lo tanto, las aprobaciones y los totales que dependen de ellos).

## Correlo vos

Con una clave de Meta Model API en `MODEL_API_KEY` (unos $0.07 por una corrida en cada brazo):

```sh
athos bench expense-review --agents meta --runs 1 --without
athos bench report
```

`athos bench --list` muestra todos los casos; `--agents muse,opencode` corre el mismo caso en Muse Code y OpenCode.
