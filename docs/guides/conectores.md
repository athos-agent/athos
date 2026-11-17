# Conectores: cuando una forma de trabajar necesita un servicio

*English: [connectors.md](connectors.md)*

Algunas formas de trabajar necesitan algo fuera del agente para hacerse bien. Una revisión de contratos no debería
mandarle a un modelo en la nube el nombre, el email o la cuenta bancaria de un cliente: un gateway que los enmascara
antes es parte de *cómo* trabaja ese abogado. Athos llama a ese servicio un **conector**.

Una forma de trabajar pide un conector en el paso que lo necesita, con `[[connector:<nombre>]]`. Cuando esa forma de
trabajar se carga, Athos comprueba el conector y se lo dice al modelo y a vos:

- **Activo**: al modelo se le dice que los datos personales le pueden llegar como marcadores, por ejemplo
  `[[PERSON_7f3a]]`, y que los deje exactamente como están; el panel muestra **🔒 los datos personales pasan por
  pii-guard**.
- **No está corriendo**: al modelo se le dice que no procese datos personales de clientes y que te pida arrancarlo o
  anonimizar; el panel muestra **⚠ pii-guard no está activo**.

Athos nunca arranca un servicio ni cambia la configuración de un agente por su cuenta: el servicio lo corrés vos, y vos
elegís qué agente pasa por él.

## El primer conector: pii-guard

[pii-guard](https://github.com/watt-mind/pii-guard) (Watt Mind, Apache-2.0) es un gateway compatible con OpenAI que corre
en tu computadora. Los nombres, emails, direcciones, documentos y cuentas bancarias se vuelven marcadores reversibles
antes de que el pedido salga, y vuelven con los valores reales en la respuesta. Paquetes de idioma: húngaro, inglés,
alemán, polaco.

### 1. Arrancá pii-guard (en su propia terminal)

Necesita [uv](https://docs.astral.sh/uv/) y una clave del modelo que está detrás (acá, Meta Model API):

```bash
export META_API_KEY="<your key>"          # or read it from where you keep it
uvx --python 3.12 --from 'wattmind-pii-guard[ner] @ git+https://github.com/watt-mind/pii-guard' pii-guard up --upstream meta
```

La primera vez baja unos 2 GB (PyTorch y su modelo de nombres). Está listo cuando escucha en `127.0.0.1:8787`; dejá
esa terminal abierta. Para comprobarlo: `curl -s http://127.0.0.1:8787/v1/status`.

### 2. Avisale a Athos

```bash
athos connector add pii-guard     # writes ~/.athos/connectors/pii-guard.md (readable, editable)
athos connector check pii-guard   # active / not running
athos connector list
```

### 3. Pedilo en una forma de trabajar

En el paso donde entran datos de clientes, nombralo. Las formas de trabajar de ejemplo de abogacía
(`athos start --profile law`) ya lo hacen:

```markdown
## #data_out
**When:** before pasting or opening the contract.
**Do:** confirm whether it holds client data; if so, propose anonymising, running the task through
[[connector:pii-guard]], or a local model.
```

### 4. Pasá tu agente por él

pii-guard funciona con los agentes sin cambiarlos: solo cambia la base URL del modelo. En OpenCode, un proveedor en
`opencode.json`:

```json
{ "provider": { "pii-guard": { "npm": "@ai-sdk/openai-compatible", "name": "pii-guard → Meta",
    "options": { "baseURL": "http://127.0.0.1:8787/v1", "apiKey": "unused" },
    "models": { "muse-spark-1.3": {} } } },
  "model": "pii-guard/muse-spark-1.3" }
```

Para otros agentes, `athos connector wire pii-guard <agente>` muestra el comando propio de pii-guard (codex,
muse-code, claude-code); mirá las [guías de integración](https://github.com/watt-mind/pii-guard/tree/develop/docs/integrations)
de pii-guard.

### Cómo se ve

Probado con OpenCode 1.19.5 sobre Muse Spark 1.3 y un contrato de locación ficticio con dos personas, dos emails, un
teléfono, una dirección, una fecha de nacimiento y una cuenta bancaria. pii-guard enmascaró todo antes de que saliera
el pedido; la respuesta volvió sin marcadores y con los valores reales; la barra lateral de OpenCode mostró
*Following «Review a contract against your checklist» · All 4 steps applied · 🔒 data through pii-guard*.

## Escribí el tuyo

Un conector es un archivo markdown en `~/.athos/connectors/<nombre>.md`:

```markdown
---
name: my-gateway
kind: gateway                      # gateway (model traffic), tool (an MCP server) or command (a local CLI)
what: one line the person and the model read
check: http://127.0.0.1:9000/health  # Athos calls it (1 s); no check = always active
start: the command you run to start it
---
Notes for you and for the model.
```

pii-guard es pseudonimización, no anonimización ni una garantía de cumplimiento legal: lo que sus detectores no ven,
pasa. Qué datos de un cliente entran en una tarea lo seguís decidiendo vos.
