"""
Libro IVA Digital — AFIP fixed-position format converter.

Format from official AFIP PDF: libro-iva-digital-diseno-registros.pdf
- Ventas Cabecera: 266 chars (LIBRO_IVA_DIGITAL_VENTAS_CBTE)
- Ventas Alícuotas: 62 chars (LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS) — one per comprobante
- Compras Cabecera: 325 chars (LIBRO_IVA_DIGITAL_COMPRAS_CBTE)
- Compras Alícuotas: 84 chars (LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS)

Tablas: Libro-IVA-Digital-Tablas-del-Sistema.pdf
- Código documento 80 = CUIT
- Alícuota 0005 = 21%
- Moneda PES = Pesos argentinos
- Código operación 0 = No corresponde
"""
import csv
import io
import re
import zipfile
from typing import Any

# AFIP constants from tablas
CODIGO_DOC_CUIT = "80"
ALICUOTA_21 = "0005"  # 21% — AFIP tabla: 0005 = 21,00%
MONEDA_PES = "PES"
TIPO_CAMBIO_PESOS = "0001000000"  # 1.0 (4 int 6 dec)
CODIGO_OPERACION_NORMAL = "0"


def _parse_fecha(val: str) -> str:
    """Convert fecha to AAAAMMDD."""
    if not val or not str(val).strip():
        return "00000000"
    s = str(val).strip().replace(" ", "")
    if re.match(r"^\d{8}$", s):
        return s
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
    if m:
        d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        return f"{y}{mo}{d}"
    return "00000000"


def _importe_to_fixed(val: Any, length: int = 15) -> str:
    """13 enteros + 2 decimales, sin punto. E.g. 1234.56 -> 000000000123456"""
    try:
        n = float(str(val).replace(",", ".").replace(" ", ""))
        cents = int(round(n * 100))
        s = str(cents).zfill(length)
        return s[-length:] if len(s) > length else s.rjust(length, "0")
    except (ValueError, TypeError):
        return "0" * length


def _pad(s: str, length: int, align: str = "left") -> str:
    s = str(s)[:length] if s else ""
    return s.rjust(length)[:length] if align == "right" else s.ljust(length)[:length]


def _cuit_clean(cuit: str) -> str:
    return "".join(c for c in str(cuit) if c.isdigit())[:11].zfill(11)


# ─────────────────────────────────────────────────────────────────────────────
# Ventas Cabecera (266 chars) — AFIP spec exact
# ─────────────────────────────────────────────────────────────────────────────

def _build_ventas_cabecera(
    fecha: str,
    tipo: str,
    pv: str,
    nro_desde: str,
    nro_hasta: str,
    cod_doc: str,
    cuit: str,
    denom: str,
    imp_total: str,
    cant_alicuotas: str = "1",
) -> str:
    """
    Build one Ventas Cabecera record (266 chars).
    Fields 10-16, 21: zeros. Field 17: PES. Field 18: 1.0. Field 20: 0. Field 22: fecha.
    """
    # 124-138: conceptos que no integran precio neto gravado
    # 139-153: percepción a no categorizados
    # 154-228: exentas, percepciones, tributos — zeros
    # 229-231: moneda PES
    # 232-241: tipo cambio
    # 242: cant alícuotas
    # 243: código operación
    # 244-258: otros tributos
    # 259-266: fecha vencimiento (use fecha for now)
    rec = (
        fecha  # 1-8
        + tipo.zfill(3)[:3]  # 9-11
        + pv.zfill(5)[:5]  # 12-16
        + _pad(nro_desde.replace("-", ""), 20, "right")  # 17-36
        + _pad(nro_hasta.replace("-", ""), 20, "right")  # 37-56
        + cod_doc.ljust(2)[:2]  # 57-58
        + _pad(cuit, 20, "right")  # 59-78
        + _pad(denom, 30, "left")[:30]  # 79-108
        + imp_total  # 109-123
        + "0" * 15  # 124-138 conceptos no integran
        + "0" * 15  # 139-153 percepción no categorizados
        + "0" * 15  # 154-168 exentas
        + "0" * 15  # 169-183 percepciones nacionales
        + "0" * 15  # 184-198 percepciones IB
        + "0" * 15  # 199-213 percepciones municipales
        + "0" * 15  # 214-228 impuestos internos
        + MONEDA_PES.ljust(3)[:3]  # 229-231
        + TIPO_CAMBIO_PESOS.ljust(10)[:10]  # 232-241
        + cant_alicuotas[:1]  # 242
        + CODIGO_OPERACION_NORMAL  # 243
        + "0" * 15  # 244-258 otros tributos
        + fecha  # 259-266 fecha vencimiento
    )
    return rec[:266]


# ─────────────────────────────────────────────────────────────────────────────
# Ventas Alícuotas (62 chars) — one per comprobante
# ─────────────────────────────────────────────────────────────────────────────

def _build_ventas_alicuota(
    tipo: str,
    pv: str,
    nro: str,
    imp_neto: str,
    alicuota: str,
    imp_iva: str,
) -> str:
    """Build one Ventas Alícuotas record (62 chars)."""
    return (
        tipo.zfill(3)[:3]  # 1-3
        + pv.zfill(5)[:5]  # 4-8
        + _pad(nro.replace("-", ""), 20, "right")  # 9-28
        + imp_neto  # 29-43
        + alicuota.zfill(4)[:4]  # 44-47
        + imp_iva  # 48-62
    )[:62]


# ─────────────────────────────────────────────────────────────────────────────
# Compras Cabecera (325 chars) — different structure
# ─────────────────────────────────────────────────────────────────────────────

def _build_compras_cabecera(
    fecha: str,
    tipo: str,
    pv: str,
    nro_desde: str,
    cod_doc: str,
    cuit: str,
    denom: str,
    imp_total: str,
    credito_fiscal: str,
    cant_alicuotas: str = "1",
) -> str:
    """
    Build one Compras Cabecera record (325 chars).
    Pos 37-52: Despacho importación (16) — blank for compras normales.
    """
    despacho = " " * 16  # 37-52
    rec = (
        fecha  # 1-8
        + tipo.zfill(3)[:3]  # 9-11
        + pv.zfill(5)[:5]  # 12-16
        + _pad(nro_desde.replace("-", ""), 20, "right")  # 17-36
        + despacho  # 37-52
        + cod_doc.ljust(2)[:2]  # 53-54
        + _pad(cuit, 20, "right")  # 55-74
        + _pad(denom, 30, "left")[:30]  # 75-104
        + imp_total  # 105-119
        + "0" * 15  # 120-134 conceptos no integran
        + "0" * 15  # 135-149 exentas
        + "0" * 15  # 150-164 percepciones IVA
        + "0" * 15  # 165-179 percepciones otros nacionales
        + "0" * 15  # 180-194 percepciones IB
        + "0" * 15  # 195-209 percepciones municipales
        + "0" * 15  # 210-224 impuestos internos
        + MONEDA_PES.ljust(3)[:3]  # 225-227
        + TIPO_CAMBIO_PESOS.ljust(10)[:10]  # 228-237
        + cant_alicuotas[:1]  # 238
        + CODIGO_OPERACION_NORMAL  # 239
        + credito_fiscal  # 240-254 crédito fiscal computable
        + "0" * 15  # 255-269 otros tributos
        + "0" * 11  # 270-280 CUIT emisor/corredor
        + " " * 30  # 281-310 denominación emisor
        + "0" * 15  # 311-325 IVA comisión
    )
    return rec[:325]


# ─────────────────────────────────────────────────────────────────────────────
# Compras Alícuotas (84 chars)
# ─────────────────────────────────────────────────────────────────────────────

def _build_compras_alicuota(
    tipo: str,
    pv: str,
    nro: str,
    cod_doc: str,
    cuit: str,
    imp_neto: str,
    alicuota: str,
    imp_iva: str,
) -> str:
    """Build one Compras Alícuotas record (84 chars)."""
    return (
        tipo.zfill(3)[:3]  # 1-3
        + pv.zfill(5)[:5]  # 4-8
        + _pad(nro.replace("-", ""), 20, "right")  # 9-28
        + cod_doc.ljust(2)[:2]  # 29-30
        + _pad(cuit, 20, "right")  # 31-50
        + imp_neto  # 51-65
        + alicuota.zfill(4)[:4]  # 66-69
        + imp_iva  # 70-84
    )[:84]


# ─────────────────────────────────────────────────────────────────────────────
# CSV conversion (user upload)
# ─────────────────────────────────────────────────────────────────────────────

def csv_to_libro_iva_ventas(csv_content: str | bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Convert CSV to Ventas Cabecera lines. Returns (cabecera_lines, errors)."""
    cab, _, err = csv_to_libro_iva_ventas_full(csv_content)
    return cab, err


def csv_to_libro_iva_ventas_full(csv_content: str | bytes) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Convert CSV to Ventas Cabecera + Alícuotas. Returns (cabeceras, alicuotas, errors)."""
    if isinstance(csv_content, bytes):
        csv_content = csv_content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_content))
    cabeceras = []
    alicuotas = []
    errors = []
    col_map = {
        "fecha": "fecha", "fecha_emision": "fecha", "tipo": "tipo_comp", "tipo_comp": "tipo_comp",
        "tipo_comprobante": "tipo_comp", "punto_venta": "punto_venta", "pv": "punto_venta",
        "numero": "numero_desde", "numero_desde": "numero_desde", "numero_hasta": "numero_hasta",
        "cuit": "cuit_contraparte", "cuit_contraparte": "cuit_contraparte", "cuit_comprador": "cuit_contraparte",
        "denominacion": "denominacion", "razon_social": "denominacion", "comprador": "denominacion",
        "importe_total": "importe_total", "total": "importe_total",
        "importe_neto": "importe_neto", "neto": "importe_neto",
        "importe_iva": "importe_iva", "iva": "importe_iva",
    }
    for i, row in enumerate(reader):
        row_num = i + 2
        try:
            r = {col_map.get(k, k): (v or "").strip() for k, v in row.items() if k}
            fecha = _parse_fecha(r.get("fecha", ""))
            tipo = str(r.get("tipo_comp", "1"))
            pv = str(r.get("punto_venta", "0"))
            nro_desde = str(r.get("numero_desde", ""))
            nro_hasta = str(r.get("numero_hasta", r.get("numero_desde", "")))
            cuit = _cuit_clean(r.get("cuit_contraparte", ""))
            denom = r.get("denominacion", "")
            tot = float(str(r.get("importe_total", "0")).replace(",", ".") or "0")
            imp_neto = tot / 1.21
            imp_iva = tot * 0.21 / 1.21
            cabecera = _build_ventas_cabecera(
                fecha, tipo, pv, nro_desde, nro_hasta, CODIGO_DOC_CUIT, cuit, denom,
                _importe_to_fixed(tot),
            )
            alicuota = _build_ventas_alicuota(
                tipo, pv, nro_desde,
                _importe_to_fixed(imp_neto), ALICUOTA_21, _importe_to_fixed(imp_iva),
            )
            cabeceras.append(cabecera)
            alicuotas.append(alicuota)
        except Exception as e:
            errors.append({"row": row_num, "error": str(e), "data": dict(row)})
    return cabeceras, alicuotas, errors


def csv_to_libro_iva_compras(csv_content: str | bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Convert CSV to Compras Cabecera lines. Returns (cabecera_lines, errors)."""
    cab, _, err = csv_to_libro_iva_compras_full(csv_content)
    return cab, err


def csv_to_libro_iva_compras_full(csv_content: str | bytes) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Convert CSV to Compras Cabecera + Alícuotas. Returns (cabeceras, alicuotas, errors)."""
    if isinstance(csv_content, bytes):
        csv_content = csv_content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_content))
    cabeceras = []
    alicuotas = []
    errors = []
    col_map = {
        "fecha": "fecha", "fecha_emision": "fecha", "tipo": "tipo_comp", "tipo_comp": "tipo_comp",
        "punto_venta": "punto_venta", "pv": "punto_venta",
        "numero_desde": "numero_desde", "numero_hasta": "numero_hasta",
        "cuit": "cuit_contraparte", "cuit_contraparte": "cuit_contraparte", "cuit_vendedor": "cuit_contraparte",
        "denominacion": "denominacion", "razon_social": "denominacion",
        "importe_total": "importe_total", "total": "importe_total",
    }
    for i, row in enumerate(reader):
        row_num = i + 2
        try:
            r = {col_map.get(k, k): (v or "").strip() for k, v in row.items() if k}
            fecha = _parse_fecha(r.get("fecha", ""))
            tipo = str(r.get("tipo_comp", "1"))
            pv = str(r.get("punto_venta", "0"))
            nro_desde = str(r.get("numero_desde", ""))
            cuit = _cuit_clean(r.get("cuit_contraparte", ""))
            denom = r.get("denominacion", "")
            tot = float(str(r.get("importe_total", "0")).replace(",", ".") or "0")
            imp_neto = tot / 1.21
            imp_iva = tot * 0.21 / 1.21
            cabecera = _build_compras_cabecera(
                fecha, tipo, pv, nro_desde, CODIGO_DOC_CUIT, cuit, denom,
                _importe_to_fixed(tot), _importe_to_fixed(imp_iva),
            )
            alicuota = _build_compras_alicuota(
                tipo, pv, nro_desde, CODIGO_DOC_CUIT, cuit,
                _importe_to_fixed(imp_neto), ALICUOTA_21, _importe_to_fixed(imp_iva),
            )
            cabeceras.append(cabecera)
            alicuotas.append(alicuota)
        except Exception as e:
            errors.append({"row": row_num, "error": str(e), "data": dict(row)})
    return cabeceras, alicuotas, errors


def build_afip_file(lines: list[str], encoding: str = "latin-1") -> bytes:
    """Build file content. Uses ANSI/Latin-1 per AFIP."""
    content = "\r\n".join(lines)
    return content.encode(encoding, errors="replace")


def get_csv_template(tipo: str = "ventas") -> str:
    headers = "fecha,tipo_comp,punto_venta,numero_desde,numero_hasta,cuit_contraparte,denominacion,importe_total"
    example = "20260201,1,4,206682,206682,30123456789,EMPRESA EJEMPLO SRL,12100"
    return headers + "\n" + example


# ─────────────────────────────────────────────────────────────────────────────
# Comprobantes from Mis Comprobantes (DB)
# ─────────────────────────────────────────────────────────────────────────────

def _comprobante_to_ventas_records(c: dict[str, Any]) -> tuple[str, str]:
    """Return (cabecera_line, alicuota_line) for one comprobante."""
    fecha = _parse_fecha(c.get("fecha_emision", ""))
    tipo = str(c.get("tipo_comprobante_codigo") or "1")
    pv = str(c.get("punto_venta") or "0")
    nro_desde = str(c.get("numero_desde", ""))
    nro_hasta = str(c.get("numero_hasta", c.get("numero_desde", "")))
    cuit = _cuit_clean(c.get("cuit_contraparte", ""))
    denom = c.get("denominacion_contraparte", "")
    imp_total = float(c.get("importe_total") or 0)
    imp_neto = imp_total / 1.21
    imp_iva = imp_total * 0.21 / 1.21
    cabecera = _build_ventas_cabecera(
        fecha, tipo, pv, nro_desde, nro_hasta, CODIGO_DOC_CUIT, cuit, denom,
        _importe_to_fixed(imp_total),
    )
    alicuota = _build_ventas_alicuota(
        tipo, pv, nro_desde,
        _importe_to_fixed(imp_neto), ALICUOTA_21, _importe_to_fixed(imp_iva),
    )
    return cabecera, alicuota


def _comprobante_to_compras_records(c: dict[str, Any]) -> tuple[str, str]:
    """Return (cabecera_line, alicuota_line) for one comprobante."""
    fecha = _parse_fecha(c.get("fecha_emision", ""))
    tipo = str(c.get("tipo_comprobante_codigo") or "1")
    pv = str(c.get("punto_venta") or "0")
    nro_desde = str(c.get("numero_desde", ""))
    cuit = _cuit_clean(c.get("cuit_contraparte", ""))
    denom = c.get("denominacion_contraparte", "")
    imp_total = float(c.get("importe_total") or 0)
    imp_neto = imp_total / 1.21
    imp_iva = imp_total * 0.21 / 1.21
    credito = _importe_to_fixed(imp_iva)
    cabecera = _build_compras_cabecera(
        fecha, tipo, pv, nro_desde, CODIGO_DOC_CUIT, cuit, denom,
        _importe_to_fixed(imp_total), credito,
    )
    alicuota = _build_compras_alicuota(
        tipo, pv, nro_desde, CODIGO_DOC_CUIT, cuit,
        _importe_to_fixed(imp_neto), ALICUOTA_21, _importe_to_fixed(imp_iva),
    )
    return cabecera, alicuota


def comprobantes_to_libro_iva(
    comprobantes: list[dict[str, Any]],
    tipo: str = "ventas",
) -> tuple[list[str], list[str]]:
    """
    Convert comprobantes to Libro IVA format.
    Returns (cabecera_lines, alicuota_lines).
    AFIP import requires both files; order must match.
    """
    cabeceras = []
    alicuotas = []
    for c in comprobantes:
        if tipo == "ventas":
            cab, ali = _comprobante_to_ventas_records(c)
        else:
            cab, ali = _comprobante_to_compras_records(c)
        cabeceras.append(cab)
        alicuotas.append(ali)
    return cabeceras, alicuotas


def build_libro_iva_zip(
    cabeceras: list[str],
    alicuotas: list[str],
    tipo: str,
    fecha_desde: str = "",
    fecha_hasta: str = "",
    encoding: str = "latin-1",
) -> bytes:
    """
    Build ZIP with cabecera and alícuotas files for AFIP import.
    File names match AFIP diseño de registros.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if tipo == "ventas":
            cbte_name = "LIBRO_IVA_DIGITAL_VENTAS_CBTE.txt"
            ali_name = "LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS.txt"
        else:
            cbte_name = "LIBRO_IVA_DIGITAL_COMPRAS_CBTE.txt"
            ali_name = "LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS.txt"
        cbte_content = "\r\n".join(cabeceras).encode(encoding, errors="replace")
        ali_content = "\r\n".join(alicuotas).encode(encoding, errors="replace")
        zf.writestr(cbte_name, cbte_content)
        zf.writestr(ali_name, ali_content)
    return buf.getvalue()
