#!/bin/sh
# Prepares the lawyer take: a law office folder with two fictitious contracts, a demo store with the Spanish law
# starters, and OpenCode set to Meta's Muse Spark through Meta Model API. Your real store is untouched.
#
#   sh demo/lawyer-setup.sh && vhs demo/lawyer.tape
#
# The take: the lawyer reviews a lease in Claude Code pasting their own checklist, Athos keeps it; then OpenCode on
# Muse Spark reviews a services agreement from a one-line request, following that checklist. Run it again before each
# take. The Meta key is read at record time from ~/.athos/.env into the recording shell, never written anywhere.
set -eu

DEMO="${ATHOS_DEMO_LAW:-$HOME/athos-demo-law}"
rm -rf "$DEMO"
mkdir -p "$DEMO/home" "$DEMO/estudio"
date -u +%Y-%m-%dT%H:%M:%SZ > "$DEMO/home/import-since"
d="$DEMO/estudio"

cat > "$d/contrato-locacion.md" << 'TXT'
# CONTRATO DE LOCACIÓN (FICTICIO)

Entre INMOBILIARIA EJEMPLO S.A. ("la Locadora") y ANA PRUEBA ("la Locataria") se celebra el presente contrato.

1. OBJETO. La Locadora da en locación el inmueble de Calle Ficticia 123, depto. 4, para vivienda.
2. PLAZO. Dos años desde el 1 de diciembre de 2026, renovable automáticamente salvo aviso de la Locataria con 180 días.
3. PRECIO. 30.000 unidades por mes, ajustables cada tres meses según el índice que la Locadora determine.
4. DEPÓSITO. Seis meses de alquiler, que la Locadora podrá retener sin expresión de causa al finalizar.
5. RESCISIÓN. La Locadora puede rescindir con 15 días de aviso. La Locataria no puede rescindir antes del vencimiento.
6. REPARACIONES. Todas, incluidas las estructurales, a cargo de la Locataria.
7. CESIÓN. La Locadora puede ceder el contrato sin consentimiento de la Locataria.
8. JURISDICCIÓN. Los tribunales que elija la Locadora.
TXT

cat > "$d/contrato-servicios.md" << 'TXT'
# CONTRATO DE SERVICIOS (FICTICIO)

Entre CLIENTE EJEMPLO S.R.L. ("el Cliente") y ESTUDIO DE DISEÑO PRUEBA ("el Proveedor").

1. OBJETO. El Proveedor diseñará la identidad visual del Cliente según el anexo A.
2. PLAZO. Doce meses, renovable automáticamente por períodos iguales salvo aviso del Proveedor con 90 días.
3. PRECIO. 5.000 unidades por mes; el Cliente pagará a los 120 días de recibida cada factura.
4. GARANTÍA. El Proveedor deposita 10.000 unidades, que el Cliente podrá retener si considera insatisfactorio el trabajo.
5. RESCISIÓN. El Cliente puede rescindir con 7 días de aviso. Si el Proveedor rescinde, pagará tres meses de precio.
6. PROPIEDAD INTELECTUAL. Todo lo creado pertenece al Cliente desde su creación, se pague o no.
7. RESPONSABILIDAD. El Proveedor responde por cualquier daño, directo o indirecto, sin límite.
8. JURISDICCIÓN. Los tribunales del domicilio del Cliente.
TXT

cat > "$d/opencode.json" << 'TXT'
{ "$schema": "https://opencode.ai/config.json",
  "provider": { "meta": { "npm": "@ai-sdk/openai-compatible", "name": "Meta Model API",
    "options": { "baseURL": "https://api.meta.ai/v1", "apiKey": "{env:MODEL_API_KEY}" },
    "models": { "muse-spark-1.3": { "name": "Muse Spark 1.3" } } } },
  "model": "meta/muse-spark-1.3" }
TXT

# The athos command: this checkout (the recording puts its bin first on PATH).
ATHOS="$(cd "$(dirname "$0")/.." && pwd)/bin/athos"
ATHOS_HOME="$DEMO/home" python3 "$ATHOS" start --lang es --profile law >/dev/null
echo "Lawyer demo ready in $DEMO ($(ls "$DEMO/home/know-how" | grep -vc Index) ways of working)."
