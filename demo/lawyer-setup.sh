#!/bin/sh
# Prepares the lawyer take: a law office folder with two fictitious contracts and the lawyer's checklist, a demo store
# with the law starters, and OpenCode set to Meta's Muse Spark through Meta Model API. Your real store is untouched.
#
#   sh demo/lawyer-setup.sh en && vhs demo/lawyer-en.tape      (English, the README GIF)
#   sh demo/lawyer-setup.sh es && vhs demo/lawyer.tape         (Spanish, the guide for lawyers)
#
# The take: the lawyer reviews a lease in Claude Code with their own checklist file, Athos keeps it; then OpenCode on
# Muse Spark reviews a services agreement from a one-line request, following that checklist. Run it again before each
# take. The Meta key is read at record time from ~/.athos/.env into the recording shell, never written anywhere.
set -eu
LANG_DEMO="${1:-es}"

DEMO="${ATHOS_DEMO_LAW:-/Users/Shared/athos-demo-law}"   # outside your home: no user name on screen
rm -rf "$DEMO"
if [ "$LANG_DEMO" = en ]; then d="$DEMO/office"; else d="$DEMO/estudio"; fi
mkdir -p "$DEMO/home" "$d"
date -u +%Y-%m-%dT%H:%M:%SZ > "$DEMO/home/import-since"

if [ "$LANG_DEMO" = en ]; then
cat > "$d/lease.md" << 'TXT'
# RESIDENTIAL LEASE (FICTITIOUS)

Between EXAMPLE PROPERTIES LLC ("the Landlord") and ANN SAMPLE ("the Tenant").

1. PREMISES. The Landlord leases 123 Fictional Street, apt. 4, as a residence.
2. TERM. Two years from December 1, 2026, renewing automatically unless the Tenant gives 180 days' notice.
3. RENT. 3,000 units per month, adjusted every three months by an index the Landlord chooses.
4. DEPOSIT. Six months' rent, which the Landlord may keep at the end without giving a reason.
5. TERMINATION. The Landlord may terminate on 15 days' notice. The Tenant may not terminate before the end of the term.
6. REPAIRS. All repairs, structural ones included, are the Tenant's.
7. ASSIGNMENT. The Landlord may assign this lease without the Tenant's consent.
8. JURISDICTION. The courts the Landlord chooses.
TXT

cat > "$d/services-agreement.md" << 'TXT'
# SERVICES AGREEMENT (FICTITIOUS)

Between EXAMPLE CLIENT INC. ("the Client") and SAMPLE DESIGN STUDIO ("the Provider").

1. SCOPE. The Provider will design the Client's visual identity as set out in schedule A.
2. TERM. Twelve months, renewing automatically for equal periods unless the Provider gives 90 days' notice.
3. FEES. 5,000 units per month; the Client pays 120 days after receiving each invoice.
4. SECURITY. The Provider deposits 10,000 units, which the Client may keep if it finds the work unsatisfactory.
5. TERMINATION. The Client may terminate on 7 days' notice. If the Provider terminates, it pays three months' fees.
6. INTELLECTUAL PROPERTY. Everything created belongs to the Client from creation, paid for or not.
7. LIABILITY. The Provider is liable for any damage, direct or indirect, without limit.
8. JURISDICTION. The courts of the Client's domicile.
TXT

cat > "$d/my-checklist.md" << 'TXT'
# My checklist for reviewing contracts

- Parties, scope, term, price and payment, governing law and jurisdiction: say if any is missing.
- Deposit or security: amount and conditions for its return.
- Early termination and notice, for both sides: flag it if it is one-sided.
- Payment: days to pay and late interest.
- Liability: always capped; never unlimited.
- Automatic renewal, assignment and jurisdiction.
- Return a table: clause, issue, proposed wording, priority (must / should / minor).
- What to negotiate is the client's decision: propose, don't decide.
TXT
else

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

cat > "$d/mi-checklist.md" << 'TXT'
# Mi checklist para revisar contratos

- Partes, objeto, plazo, precio y forma de pago, ley y jurisdicción: si falta alguno, decirlo.
- Depósito o garantía: monto y condiciones de devolución.
- Rescisión anticipada y preaviso, para las dos partes: marcar si es asimétrica.
- Pago: plazo en días e intereses por mora.
- Responsabilidad: siempre con tope; nunca ilimitada.
- Renovación automática, cesión y jurisdicción.
- Devolver una tabla: cláusula, problema, propuesta, prioridad (imprescindible / conveniente / menor).
- La decisión de qué negociar es del cliente: proponer, no decidir.
TXT

fi

cat > "$d/opencode.json" << 'TXT'
{ "$schema": "https://opencode.ai/config.json",
  "provider": { "meta": { "npm": "@ai-sdk/openai-compatible", "name": "Meta Model API",
    "options": { "baseURL": "https://api.meta.ai/v1", "apiKey": "{env:MODEL_API_KEY}" },
    "models": { "muse-spark-1.3": { "name": "Muse Spark 1.3" } } } },
  "model": "meta/muse-spark-1.3" }
TXT

# The athos command: this checkout (the recording puts its bin first on PATH).
ATHOS="$(cd "$(dirname "$0")/.." && pwd)/bin/athos"
ATHOS_HOME="$DEMO/home" python3 "$ATHOS" start --lang "$LANG_DEMO" --profile law >/dev/null
echo "Lawyer demo ready in $DEMO ($(ls "$DEMO/home/know-how" | grep -vc Index) ways of working)."
