# WSAA Certificate Setup for veconsumerws

**Note:** The primary PDF download method uses the DFE REST API (`GET /api/v1/communications/{id}/{idArchivo}`) and does not require WSAA. See `docs/ARCHITECTURE.md` for the current flow.

This document describes optional setup for **veconsumerws** SOAP — use only if you need SOAP-based access (e.g. REST API unavailable in your environment). To download PDF attachments via veconsumerws, you need WSAA certificate authentication.

## Overview

1. **Adherirse a WSASS** (first time only) via Administrador de Relaciones
2. **Generate CSR** (Certificate Signing Request) with your CUIT
3. **Upload CSR to WSASS** (AFIP certificate portal)
4. **Download certificate** and associate it with **veconsumerws**
5. **Configure paths** in `.env`

## Step 0: Adherirse a WSASS (first time only)

1. Go to **Administrador de Relaciones**: https://auth.afip.gob.ar/contribuyente_/login.xhtml?action=SYSTEM&system=adminrel
2. Log in with **Clave Fiscal de persona física** (no empresa). Nivel 2 o superior.
3. Click **Adherir servicio** → **Servicios interactivos** → **WSASS**
4. Cerrar sesión y volver a acceder. WSASS aparecerá en "Mis Servicios".

## Step 1: Generate CSR

From the `arca-prototype` directory:

```bash
# Using env var (recommended)
ARCA_CUIT=20268448536 python scripts/generate_csr.py

# Or pass CUIT as argument
python scripts/generate_csr.py 20268448536

# Optional: specify output directory
python scripts/generate_csr.py 20268448536 ./certs
```

This creates:
- `certs/arca_private.key` — **Keep secret.** Never commit.
- `certs/arca_request.csr` — Upload this to WSASS.

## Step 2: Upload CSR to WSASS

1. Log in to **WSASS**: https://auth.afip.gob.ar/contribuyente_/login.xhtml  
   Use your **Clave Fiscal** (same as DFE login).

2. Go to **Certificados** / **Administración de certificados**.

3. **Crear nuevo certificado**:
   - Upload the `arca_request.csr` file
   - Select service: **veconsumerws** (Consumir Comunicaciones de Ventanilla Electrónica)
   - Submit

4. **Download** the certificate (`.crt` or `.pem`).

## Step 3: Place Certificate, Key, and CA Chain

```bash
mkdir -p arca-prototype/certs
# Copy the downloaded cert to certs/arca.crt (or arca.pem)
# The private key is already in certs/arca_private.key from step 1
# Download AFIP homologation chain and extract to certs/:
#   https://www.afip.gob.ar/ws/WSASS/Cadena_de_certificacion_homo_2022_2034.zip
#   Extract ComputadoresTest.cacert_2022-2030.crt to certs/
```

## Step 4: Configure .env

Add to your `.env`:

```env
ARCA_CERT_PATH=certs/arca.crt
ARCA_KEY_PATH=certs/arca_private.key
ARCA_HOMOLOGACION=true
```

For production, set `ARCA_HOMOLOGACION=false` and use production certificates.

## Step 5: Verify

When certificates are configured, `POST /api/arca/attachments/download` will try **veconsumerws** first. If successful, PDFs are fetched via SOAP (no Playwright/UI automation needed).

## Troubleshooting

- **"Certificate not found"**: Ensure `ARCA_CERT_PATH` and `ARCA_KEY_PATH` point to existing files.
- **WSAA error**: Verify the certificate is associated with **veconsumerws** (or the service you need) in WSASS.
- **"Certificado no emitido por AC de confianza"**: WSAA does not trust your certificate's issuer. For homologación: ensure you use the certificate from WSASS (not production). If the error persists, contact **webservices-desa@arca.gob.ar** with your CUIT and the exact error; AFIP may need to verify your certificate in their trust store.
- **veconsumerws URL**: The default endpoint may need adjustment. If you receive a different URL from AFIP (manual or support), set `ARCA_VECONSUMERWS_URL` in `.env`.
- **Contact**: For testing env issues: webservices-desa@arca.gob.ar. For production: sri@arca.gob.ar.

## References

- AFIP WSCCOMU manual: https://www.afip.gob.ar/ws/WSCComu/vecuwsconcomunicaciones.pdf
- AFIP web services: https://www.afip.gob.ar/ws/
