# Tu checklist es know-how: cómo guardarlo y llevarlo a cualquier IA

*English: [checklist-en.md](checklist-en.md)*

Casi todo trabajo profesional tiene un checklist: lo que un abogado revisa en un contrato, lo que un contador cierra a
fin de mes, lo que una persona de recursos humanos prepara antes de que alguien empiece, lo que una editora chequea
antes de publicar. Ese checklist es lo más valioso que le podés enseñar a una IA, y lo más fácil de perder: queda
en un chat y la próxima vez hay que volver a explicarlo.

Athos lo detecta y lo guarda.

## Cómo funciona

1. **Trabajás con tu checklist.** Lo nombrás (*«con mi checklist»*, *«seguí el protocolo»*), lo pegás como lista, o
   la IA abre un archivo que se llama, por ejemplo, `checklist-cierre.md`.
2. **Athos se da cuenta.** Al terminar la tarea, le pregunta a la IA si vale la pena guardarlo, aunque la tarea no haya
   cambiado ningún archivo (una revisión solo lee y responde). La pregunta dice por qué: *«esta tarea siguió un
   checklist, y eso es know-how valioso»*.
3. **Queda como forma de trabajar.** Un archivo de texto tuyo, en `~/.athos/know-how`, con un paso por ítem: cuándo
   aplica, qué hacer y por qué. Lo podés leer y corregir.
4. **La próxima vez se aplica solo.** Cuando un pedido coincide, la IA arranca diciendo qué forma de trabajar tuya
   sigue y cómo la aplica a este caso, y no tenés que volver a pegar el checklist.
5. **Funciona en todas tus herramientas.** Claude, Muse Code de Meta, OpenCode y Codex leen las mismas formas de
   trabajar.

Si una forma de trabajar ya guió la tarea, Athos no pregunta de nuevo por el checklist: lo que corresponde es mejorarla,
y la IA lo hace cuando la tarea enseñó algo nuevo.

## Un ejemplo para probar en cinco minutos

Con Athos instalado (ver [la guía para abogados](abogado.md), paso 1), en una carpeta de prueba:

```
Revisá el cierre de octubre con mi checklist:
- conciliar cada cuenta bancaria con el extracto
- facturas emitidas vs. cobradas: listar las vencidas hace más de 30 días
- gastos sin comprobante: marcarlos, no inventarlos
- resumen de una página para el cliente, con las tres cosas a resolver
Los datos están en movimientos.csv y facturas.csv.
```

Al terminar, Athos pregunta si guardar el checklist. Decí que sí. La próxima vez: *«Hacé el cierre de noviembre»*.

## Cómo escribir un buen checklist para la IA

- **Un ítem, una acción que se pueda comprobar.** *«Listar las facturas vencidas hace más de 30 días»* y no *«revisar
  facturas»*.
- **Decí qué no tiene que hacer.** *«Marcarlos, no inventarlos»*, *«la decisión es del cliente»*.
- **Incluí el formato de lo que esperás.** Una tabla, un resumen de una página, columnas concretas.
- **Agregá el porqué cuando no es obvio.** La IA aplica mejor una regla cuando sabe para qué está.

## Lo que Athos no hace

- No decide por vos: guarda tu forma de trabajar y la IA la sigue, pero la responsabilidad profesional sigue siendo
  tuya.
- No envía tus checklists a ningún lado: viven en tu computadora.
- No inventa ítems: guarda los que vos usaste. Si después querés agregar uno, editá el archivo.
