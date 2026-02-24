# Libro IVA Digital — Formato AFIP

Formato basado en la documentación oficial de AFIP.

## Fuentes oficiales

- **Diseño de registros:** https://www.afip.gob.ar/iva/documentos/libro-iva-digital-diseno-registros.pdf
- **Tablas del sistema:** https://www.afip.gob.ar/iva/documentos/Libro-IVA-Digital-Tablas-del-Sistema.pdf

## Estructura de archivos

AFIP requiere **dos archivos** para importación:
1. **Cabecera** (comprobantes)
2. **Alícuotas** (desglose IVA por comprobante)

El orden entre cabecera y alícuotas debe coincidir.

## Ventas

### Cabecera (266 caracteres)

| Pos  | Campo | Observaciones |
|------|-------|---------------|
| 1-8 | Fecha comprobante | AAAAMMDD |
| 9-11 | Tipo comprobante | Tabla Comprobantes Ventas |
| 12-16 | Punto de venta | 5 dígitos |
| 17-36 | Número comprobante | 20 chars |
| 37-56 | Número comprobante hasta | 20 chars |
| 57-58 | Código documento comprador | 80 = CUIT |
| 59-78 | Número identificación comprador | 20 chars, ceros a izquierda |
| 79-108 | Denominación comprador | 30 chars |
| 109-123 | Importe total operación | 15 chars (13 int + 2 dec, sin punto) |
| 124-138 | Conceptos que no integran precio neto | 15 chars |
| 139-153 | Percepción a no categorizados | 15 chars |
| 154-228 | Exentas, percepciones, tributos | 15 chars c/u |
| 229-231 | Código moneda | PES = pesos |
| 232-241 | Tipo de cambio | 4 int 6 dec |
| 242 | Cantidad alícuotas IVA | 1 char |
| 243 | Código operación | 0 = No corresponde |
| 244-258 | Otros tributos | 15 chars |
| 259-266 | Fecha vencimiento/pago | AAAAMMDD |

### Alícuotas (62 caracteres)

| Pos | Campo |
|-----|-------|
| 1-3 | Tipo comprobante |
| 4-8 | Punto de venta |
| 9-28 | Número comprobante |
| 29-43 | Importe neto gravado |
| 44-47 | Alícuota IVA (0005 = 21%) |
| 48-62 | Impuesto liquidado |

## Compras

### Cabecera (325 caracteres)

Estructura distinta a ventas. Pos 37-52: Despacho de importación (blank para compras normales). Pos 240-254: Crédito Fiscal Computable.

### Alícuotas (84 caracteres)

Incluye código documento y CUIT vendedor.

## Códigos

- **Documento:** 80 = CUIT
- **Moneda:** PES = Pesos argentinos
- **Alícuota 21%:** 0005
- **Operación normal:** 0
