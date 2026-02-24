"""
veconsumerws (WSCCOMU) client — Consumir Comunicaciones de Ventanilla Electrónica.

Calls consumirComunicacion with incluirAdjuntos=true to retrieve base64 PDF attachments.
Requires WSAA certificate authentication (token + sign).

Service: WSCCOMU — Consumir Comunicaciones de Ventanilla Electrónica
Manual: https://www.afip.gob.ar/ws/WSCComu/vecuwsconcomunicaciones.pdf
WSID for WSAA: veconsumerws

If the WSDL URL is not available, contact webservices-desa@arca.gob.ar (testing)
or sri@arca.gob.ar (production) to obtain it.
"""
import base64
import os
import xml.etree.ElementTree as ET
from typing import Any

import requests

from backend.services.wsaa_client import get_credentials

# Configurable via env — obtain from AFIP manual or support
VECONSUMERWS_HOMO = os.getenv(
    "ARCA_VECONSUMERWS_URL",
    "https://wswhomo.afip.gov.ar/wsccomunicaciones/ComunicacionesService",
)
VECONSUMERWS_PROD = os.getenv(
    "ARCA_VECONSUMERWS_PROD_URL",
    "https://stable-middleware-tecno-ext.afip.gob.ar/ve-ws/services/veconsumer",
)


def consumir_comunicacion(
    id_comunicacion: int,
    cuit: str,
    incluir_adjuntos: bool = True,
    homologacion: bool = True,
    cert_path: str | None = None,
    key_path: str | None = None,
) -> dict[str, Any]:
    """
    Call veconsumerws consumirComunicacion to retrieve a communication and its attachments.

    Args:
        id_comunicacion: Communication ID (e.g. from DFE notifications API)
        cuit: 11-digit CUIT
        incluir_adjuntos: If True, response includes base64 PDF content in adjuntos.adjunto
        homologacion: Use homologación (True) or producción (False)
        cert_path: Path to WSAA certificate (optional, uses ARCA_CERT_PATH)
        key_path: Path to private key (optional, uses ARCA_KEY_PATH)

    Returns:
        Dict with Comunicacion (including adjuntos.adjunto as list of base64 strings if incluir_adjuntos)

    Raises:
        RuntimeError: If credentials missing or SOAP call fails
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        raise ValueError("CUIT debe tener 11 dígitos")

    creds = get_credentials(
        cert_path=cert_path,
        key_path=key_path,
        service="veconsumerws",
        homologacion=homologacion,
    )

    url = VECONSUMERWS_HOMO if homologacion else VECONSUMERWS_PROD
    # Ensure we have a SOAP endpoint (some services use .asmx or no path)
    if not url.endswith(".asmx") and "/" not in url.split("//")[-1].split("/")[-1]:
        url = url.rstrip("/")

    # Build SOAP envelope per WSDL at stable-middleware-tecno-ext.afip.gob.ar
    ns_ws = "http://ve.tecno.afip.gov.ar/domain/service/ws"
    ns_types = "http://ve.tecno.afip.gov.ar/domain/service/ws/types"
    ns_core = "http://core.tecno.afip.gov.ar/model/ws/types"

    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
  xmlns:ws="{ns_ws}" xmlns:types="{ns_types}" xmlns:core="{ns_core}">
  <soapenv:Header/>
  <soapenv:Body>
    <types:consumirComunicacion>
      <authRequest>
        <core:token>{creds["token"]}</core:token>
        <core:sign>{creds["sign"]}</core:sign>
        <core:cuitRepresentada>{cuit_clean}</core:cuitRepresentada>
      </authRequest>
      <idComunicacion>{id_comunicacion}</idComunicacion>
      <incluirAdjuntos>{str(incluir_adjuntos).lower()}</incluirAdjuntos>
    </types:consumirComunicacion>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
    }

    post_url = url.replace("?wsdl", "").replace("?WSDL", "")
    resp = requests.post(post_url, data=envelope.encode("utf-8"), headers=headers, timeout=60)
    resp.raise_for_status()

    return _parse_consumir_response(resp.text, incluir_adjuntos)


def _parse_consumir_response(soap_text: str, expect_adjuntos: bool) -> dict[str, Any]:
    """Parse consumirComunicacion SOAP response and extract Comunicacion + adjuntos."""
    root = ET.fromstring(soap_text)

    # Handle SOAP Fault
    fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
    if fault is not None:
        faultstring = fault.find("faultstring")
        msg = faultstring.text if faultstring is not None else soap_text[:500]
        raise RuntimeError(f"veconsumerws SOAP Fault: {msg}")

    # Find return / Comunicacion — namespace may vary
    result = {}
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "adjunto" and elem.text:
            result.setdefault("adjuntos", []).append(elem.text)
        elif tag == "adjuntos" and len(elem) > 0:
            for child in elem:
                ct = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ct == "adjunto" and child.text:
                    result.setdefault("adjuntos", []).append(child.text)
        elif tag in ("idComunicacion", "asunto", "mensaje", "estado", "estadoDesc"):
            result[tag] = elem.text
        elif tag == "comunicacion" or tag == "Comunicacion":
            # Nested structure
            sub = {}
            for c in elem:
                ct = c.tag.split("}")[-1] if "}" in c.tag else c.tag
                if ct == "adjuntos":
                    adj = []
                    for a in c:
                        at = a.tag.split("}")[-1] if "}" in a.tag else a.tag
                        if at == "adjunto" and a.text:
                            adj.append(a.text)
                    sub["adjuntos"] = adj
                elif c.text:
                    sub[ct] = c.text
            result["comunicacion"] = sub
            if "adjuntos" in sub:
                result["adjuntos"] = sub["adjuntos"]

    return result


def get_attachment_pdfs(
    id_comunicacion: int,
    cuit: str,
    homologacion: bool = True,
) -> list[bytes]:
    """
    Convenience: fetch communication and return list of PDF bytes (decoded from base64).

    Returns:
        List of PDF byte strings. Empty if no attachments or call fails.
    """
    try:
        data = consumir_comunicacion(
            id_comunicacion=id_comunicacion,
            cuit=cuit,
            incluir_adjuntos=True,
            homologacion=homologacion,
        )
    except (RuntimeError, ValueError) as e:
        raise e

    adjuntos = data.get("adjuntos") or []
    if isinstance(data.get("comunicacion"), dict):
        adjuntos = data["comunicacion"].get("adjuntos") or adjuntos

    pdfs = []
    for b64 in adjuntos:
        if b64:
            try:
                pdfs.append(base64.b64decode(b64))
            except Exception:
                pass
    return pdfs
