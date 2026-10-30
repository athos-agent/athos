# Conectores: cuando una forma de trabajar necesita un servicio

*English: [connectors.md](connectors.md)*

Algunas formas de trabajar necesitan algo fuera del agente para hacerse bien. Una revisión de contratos no debería
mandarle a un modelo en la nube el nombre, el email o la cuenta bancaria de un cliente: un gateway que los enmascara
antes es parte de *cómo* trabaja ese abogado. Athos llama a ese servicio un **conector**.

Una forma de trabajar lo pide en el paso que lo necesita, con `[[connector:<nombre>]]`. Cuando se carga, Athos comprueba
el conector y se lo dice al modelo y a vos:

- **Activo**: el modelo sabe que los datos personales le pueden llegar como marcadores (`[[PERSON_7f3a]]`) y que los
  tiene que dejar intactos; el panel muestra **🔒 los datos personales pasan por pii-guard**.
- **No está corriendo**: el modelo no procesa datos personales de clientes y te pide arrancarlo o anonimizar; el panel
  muestra **⚠ pii-guard no está activo**.

Athos nunca arranca un servicio ni cambia la configuración de un agente por su cuenta: el servicio lo corrés vos, y vos
elegís qué agente pasa por él.

## El primer conector: pii-guard

[pii-guard](https://github.com/watt-mind/pii-guard) (Watt Mind, Apache-2.0) es un gateway compatible con OpenAI que corre
en tu computadora: enmascara nombres, emails, direcciones, documentos y cuentas antes de que el pedido salga, y los
repone en la respuesta. Idiomas: húngaro, inglés, alemán, polaco (español todavía no).

1. **Arrancalo en su propia terminal** (necesita [uv](https://docs.astral.sh/uv/) y una clave del modelo, acá Meta):
   ```bash
   export META_API_KEY="<tu clave>"
   uvx --python 3.12 --from 'wattmind-pii-guard[ner] @ git+https://github.com/watt-mind/pii-guard' pii-guard up --upstream meta
   ```
   La primera vez baja unos 2 GB. Está listo cuando escucha en `127.0.0.1:8787`; dejá esa terminal abierta.
2. **Avisale a Athos**: `athos connector add pii-guard` y `athos connector check pii-guard`.
3. **Pedilo en tu forma de trabajar** con `[[connector:pii-guard]]` en el paso donde entran datos de clientes (las piezas
   de ejemplo de abogacía ya lo hacen).
4. **Pasá tu agente por él**: solo cambia la base URL del modelo. Para OpenCode, el `opencode.json` de
   [connectors.md](connectors.md#4-send-your-agent-through-it); para otros, `athos connector wire pii-guard <agente>`.

Probado con OpenCode y Muse Spark sobre un contrato ficticio con dos personas, emails, teléfono, dirección, fecha de
nacimiento y cuenta: pii-guard enmascaró todo antes de que saliera, la respuesta volvió con los datos reales y la barra
lateral de OpenCode mostró *🔒 data through pii-guard*.

Cómo escribir tu propio conector: [connectors.md](connectors.md#write-your-own). pii-guard es pseudonimización, no
anonimización ni una garantía legal: lo que sus detectores no ven, pasa. Qué datos de un cliente entran en una tarea lo
seguís decidiendo vos.
