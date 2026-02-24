"""
LLM-powered search over reconciliation data.

Uses OpenAI GPT-4o-mini to interpret natural-language queries against
ARCA + Colppy invoice data and return structured results.
"""

import json
import logging
import os
from typing import AsyncIterator

from openai import AsyncOpenAI, APIError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Sos un asistente de búsqueda para reconciliación de facturas argentinas.
Ayudás a encontrar y analizar comprobantes de dos fuentes:
- ARCA (autoridad fiscal argentina, ex-AFIP)
- Colppy (ERP contable)

Los datos contienen {n_total} comprobantes del {fecha_desde} al {fecha_hasta}.
- {n_matched} matcheados (CAE + monto coinciden)
- {n_discrepancies} con discrepancias (only_arca, only_colppy, amount_mismatch, currency_mismatch, etc.)

Campos ARCA: numero, fecha_emision, tipo_comprobante, cuit_contraparte, \
denominacion_contraparte, moneda, importe_total, cod_autorizacion (CAE)
Campos Colppy: nroFactura, fechaFactura, idTipoComprobante, RazonSocial, \
totalFactura_pesos, cae, idEstadoFactura

Respondé siempre en español. Sé conciso pero informativo.
Cuando listés facturas, mostrá los datos clave (número, contraparte, monto, estado).

IMPORTANTE: Al final de tu respuesta, incluí un bloque JSON con los CAEs de las \
facturas que mencionaste, así:

```json
{{"matched_caes": ["12345678901234", "98765432109876"]}}
```

Si no mencionás facturas específicas, usá `{{"matched_caes": []}}`.
"""


def _build_invoice_context(
    discrepancies: list[dict],
    matched_pairs: list[dict],
    scope: str,
) -> str:
    """Build compact text representation of invoices for the LLM context."""
    lines = []

    if discrepancies:
        lines.append("=== DISCREPANCIAS ===")
        for d in discrepancies:
            status = d.get("status", "unknown")
            if d.get("arca"):
                a = d["arca"]
                lines.append(
                    f"[{status}] CAE:{a.get('cod_autorizacion','')} "
                    f"N:{a.get('numero','')} {a.get('fecha_emision','')} "
                    f"{a.get('denominacion_contraparte','')} "
                    f"ARCA:${a.get('importe_total',0)}"
                )
            if d.get("colppy"):
                c = d["colppy"]
                src = "  Colppy:" if d.get("arca") else f"[{status}] "
                lines.append(
                    f"{src}CAE:{c.get('cae','')} "
                    f"N:{c.get('nroFactura','')} {c.get('fechaFactura','')} "
                    f"{c.get('RazonSocial','')} "
                    f"Colppy:${c.get('totalFactura_pesos',0)}"
                )
            if d.get("diff_pesos"):
                lines.append(f"  Diferencia: ${d['diff_pesos']}")

    if scope == "all" and matched_pairs:
        lines.append(f"\n=== MATCHEADOS ({len(matched_pairs)}) ===")
        for p in matched_pairs:
            a = p.get("arca", {})
            lines.append(
                f"[matched] CAE:{a.get('cod_autorizacion','')} "
                f"N:{a.get('numero','')} {a.get('fecha_emision','')} "
                f"{a.get('denominacion_contraparte','')} "
                f"${a.get('importe_total',0)}"
            )

    return "\n".join(lines)


async def search_invoices_stream(
    query: str,
    cuit: str,
    fecha_desde: str,
    fecha_hasta: str,
    scope: str,
    conversation: list[dict],
    discrepancies: list[dict],
    matched_pairs: list[dict],
) -> AsyncIterator[str]:
    """
    Stream search results from OpenAI GPT-4o-mini.

    Yields SSE-formatted lines: `data: {...}\n\n`
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        yield f'data: {json.dumps({"type": "error", "content": "OPENAI_API_KEY no configurada en .env"})}\n\n'
        return

    n_disc = len(discrepancies)
    n_matched = len(matched_pairs)
    n_total = n_disc + n_matched

    system = SYSTEM_PROMPT.format(
        n_total=n_total,
        n_matched=n_matched,
        n_discrepancies=n_disc,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    invoice_context = _build_invoice_context(discrepancies, matched_pairs, scope)

    # Build messages: system + invoice context + conversation history + new query
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Datos de facturas para buscar:\n\n{invoice_context}"},
        {"role": "assistant", "content": "Entendido. Tengo los datos de facturas cargados. ¿Qué querés buscar?"},
    ]

    for msg in conversation:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": query})

    client = AsyncOpenAI(api_key=api_key)

    try:
        full_text = ""
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
                yield f'data: {json.dumps({"type": "text", "content": delta.content})}\n\n'

        # Extract CAEs from the JSON block at end of response
        caes = []
        try:
            json_start = full_text.rfind("```json")
            json_end = full_text.rfind("```", json_start + 7)
            if json_start >= 0 and json_end > json_start:
                json_str = full_text[json_start + 7:json_end].strip()
                parsed = json.loads(json_str)
                caes = parsed.get("matched_caes", [])
        except (json.JSONDecodeError, ValueError):
            pass

        yield f'data: {json.dumps({"type": "matches", "caes": caes})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'

    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        yield f'data: {json.dumps({"type": "error", "content": f"Error de API OpenAI: {e}"})}\n\n'
    except Exception as e:
        logger.error("Search error: %s", e)
        yield f'data: {json.dumps({"type": "error", "content": f"Error: {e}"})}\n\n'
