"""
WSAA (Web Service de Autenticación y Autorización) client for AFIP.

Obtains token and sign for AFIP SOAP services (e.g. veconsumerws) using
X.509 certificate authentication.

Based on AFIP WSAA flow:
  1. Create TRA (Ticket de Requerimiento de Acceso) XML
  2. Sign TRA with certificate + private key (PKCS7)
  3. Call WSAA loginCms to obtain token and sign
"""
import email
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
except ImportError:
    x509 = None  # type: ignore

import requests

WSAA_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
WSAA_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
SERVICE_VECONSUMERWS = "veconsumerws"
DEFAULT_TTL = 2400  # seconds


def _create_tra(
    service: str = SERVICE_VECONSUMERWS,
    ttl: int = DEFAULT_TTL,
    homologacion: bool = True,
) -> bytes:
    """Create Ticket de Requerimiento de Acceso (TRA) XML.
    Per WSAA spec: destination for homologation is cn=wsaahomo,o=afip,c=ar,serialNumber=CUIT 33693450239
    """
    now = datetime.now(timezone.utc)
    gen_time = now.timestamp() - ttl
    exp_time = now.timestamp() + ttl

    def to_c(ts: float) -> str:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "-00:00"

    unique_id = str(int(now.timestamp()))
    dest = (
        "cn=wsaahomo,o=afip,c=ar,serialNumber=CUIT 33693450239"
        if homologacion
        else "cn=wsaa,o=afip,c=ar,serialNumber=CUIT 33693450239"
    )
    tra = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <destination>{dest}</destination>
    <uniqueId>{unique_id}</uniqueId>
    <generationTime>{to_c(gen_time)}</generationTime>
    <expirationTime>{to_c(exp_time)}</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>"""
    return tra.encode("utf-8")


def _sign_tra(tra: bytes, cert_path: str, key_path: str, passphrase: str = "") -> str:
    """
    Sign TRA with PKCS7 and return base64 CMS for WSAA.
    Tries OpenSSL first (better compatibility with AFIP), then cryptography.
    """
    import shutil
    import subprocess
    import tempfile

    cert_path = str(Path(cert_path).resolve())
    key_path = str(Path(key_path).resolve())

    # Try OpenSSL first - AFIP WSAA often works better with OpenSSL-signed CMS
    openssl = shutil.which("openssl")
    if openssl:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(tra)
            tra_path = f.name
        try:
            # WSAA spec: SHA1+RSA for CMS. Include AFIP CA chain so WSAA can verify.
            cmd = [
                openssl, "smime", "-sign",
                "-signer", cert_path,
                "-inkey", key_path,
                "-md", "sha1",
                "-outform", "DER", "-nodetach",
                "-in", tra_path,
            ]
            # Add AFIP homologation CA chain so WSAA can verify the certificate
            cert_dir = Path(cert_path).parent
            for name in ("ComputadoresTest.cacert_2022-2030.crt", "ComputadoresTest.cacert_2022-2030.pem"):
                chain_path = cert_dir / name
                if chain_path.exists():
                    cmd.extend(["-certfile", str(chain_path)])
                    break
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0:
                import base64
                return base64.b64encode(result.stdout).decode("ascii")
        except Exception:
            pass
        finally:
            Path(tra_path).unlink(missing_ok=True)

    # Fallback to cryptography
    if x509 is None:
        raise RuntimeError("Install cryptography: pip install cryptography")

    key_data = Path(key_path).read_bytes()
    cert_data = Path(cert_path).read_bytes()

    password = passphrase.encode("utf-8") if passphrase else None
    private_key = serialization.load_pem_private_key(key_data, password, default_backend())
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())

    # WSAA spec: SHA1+RSA for CMS (spec may be outdated but try for compatibility)
    p7 = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra)
        .add_signer(cert, private_key, hashes.SHA1())
        .sign(serialization.Encoding.SMIME, [pkcs7.PKCS7Options.Binary])
    )

    msg = email.message_from_bytes(p7)
    for part in msg.walk():
        ct = part.get_content_type()
        fn = part.get_filename() or ""
        if "pkcs7" in ct or "pkcs7-signature" in ct or fn.startswith("smime.p7"):
            payload = part.get_payload(decode=False)
            if payload:
                return payload
    raise RuntimeError("PKCS7 part not found in signed output")


def _call_wsaa(cms: str, url: str = WSAA_HOMO) -> dict[str, Any]:
    """Call WSAA loginCms and return parsed token/sign."""
    soap_envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '""',
    }

    resp = requests.post(url, data=soap_envelope.encode("utf-8"), headers=headers, timeout=30)

    if resp.status_code != 200:
        # Parse SOAP Fault for clearer error
        if "faultstring" in resp.text:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)
            for el in root.iter():
                tag = el.tag.split("}")[-1] if el.tag and "}" in el.tag else (el.tag or "")
                if tag == "faultstring" and el.text:
                    raise RuntimeError(f"WSAA rechazó la solicitud: {el.text}")
        resp.raise_for_status()

    # Parse token and sign from response.
    # The loginCmsReturn element contains HTML-encoded XML that must be unescaped.
    import html
    import xml.etree.ElementTree as ET

    root = ET.fromstring(resp.content)
    token_el = None
    sign_el = None

    # First, try to find loginCmsReturn and parse the inner XML
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "loginCmsReturn" and el.text:
            inner_xml = html.unescape(el.text)
            inner_root = ET.fromstring(inner_xml)
            for child in inner_root.iter():
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "token" and child.text:
                    token_el = child
                elif ctag == "sign" and child.text:
                    sign_el = child
            break

    # Fallback: try direct namespace lookup
    if token_el is None or sign_el is None:
        token_el = root.find(".//{http://wsaa.view.sua.dvadac.desein.afip.gov}token")
        sign_el = root.find(".//{http://wsaa.view.sua.dvadac.desein.afip.gov}sign")

    if token_el is None or sign_el is None:
        raise RuntimeError(f"WSAA response missing token/sign: {resp.text[:500]}")
    return {"token": token_el.text, "sign": sign_el.text}


# In-memory token cache: {service: {"token": str, "sign": str, "expires": float}}
_token_cache: dict[str, dict[str, Any]] = {}


def get_credentials(
    cert_path: str | None = None,
    key_path: str | None = None,
    service: str = SERVICE_VECONSUMERWS,
    homologacion: bool = True,
) -> dict[str, Any]:
    """
    Obtain token and sign for AFIP SOAP services.
    Caches tokens in memory to avoid "already has a valid TA" errors.

    Args:
        cert_path: Path to .crt or .pem certificate (from WSASS)
        key_path: Path to private key .key
        service: AFIP service name (veconsumerws for DFE consumirComunicacion)
        homologacion: Use homologación (True) or producción (False)

    Returns:
        {"token": str, "sign": str}

    Raises:
        RuntimeError: If cert/key missing or WSAA call fails
    """
    import time

    cert_path = cert_path or os.getenv("ARCA_CERT_PATH")
    key_path = key_path or os.getenv("ARCA_KEY_PATH")
    if homologacion and os.getenv("ARCA_HOMOLOGACION", "").lower() == "false":
        homologacion = False
    if not cert_path or not key_path:
        raise RuntimeError(
            "Certificate and key required. Set ARCA_CERT_PATH and ARCA_KEY_PATH, "
            "or pass cert_path and key_path. Run scripts/generate_csr.py and complete WSASS setup."
        )
    cert_path = str(Path(cert_path).expanduser().resolve())
    key_path = str(Path(key_path).expanduser().resolve())
    if not Path(cert_path).exists():
        raise RuntimeError(f"Certificate not found: {cert_path}")
    if not Path(key_path).exists():
        raise RuntimeError(f"Private key not found: {key_path}")

    # Return cached token if still valid (with 60s safety margin)
    cache_key = f"{service}:{'homo' if homologacion else 'prod'}"
    cached = _token_cache.get(cache_key)
    if cached and cached.get("expires", 0) > time.time() + 60:
        return {"token": cached["token"], "sign": cached["sign"]}

    url = WSAA_HOMO if homologacion else WSAA_PROD
    tra = _create_tra(service=service, ttl=DEFAULT_TTL, homologacion=homologacion)
    cms = _sign_tra(tra, cert_path, key_path)

    try:
        result = _call_wsaa(cms, url=url)
    except RuntimeError as e:
        if "ya posee un TA valido" in str(e) and cached:
            return {"token": cached["token"], "sign": cached["sign"]}
        raise

    # Cache the token with expiration
    _token_cache[cache_key] = {
        "token": result["token"],
        "sign": result["sign"],
        "expires": time.time() + DEFAULT_TTL,
    }
    return result
