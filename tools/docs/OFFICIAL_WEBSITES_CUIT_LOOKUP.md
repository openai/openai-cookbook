# Official Websites for CUIT Creation Date Lookup

## 🎯 Best Option: Open Data Portal (Recommended)

### RNS Open Data Portal
**URL**: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades

**What it provides:**
- Complete RNS database as downloadable CSV/ZIP files
- Includes: CUIT, razón social, **fecha de contrato social** (creation date), domicilio fiscal/legal, tipo societario
- Updated monthly
- No authentication required
- No scraping needed!

**Available datasets:**
- **Sample (1000 records)**: Direct CSV download
- **Full datasets by semester**: 2019-2025 (ZIP files)
- **Non-profit associations**: Separate datasets

**Download URLs:**
- Sample: https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/6096331b-0511-4728-b01b-6c6b535f4c2b/download/registro-nacional-sociedades-muestreo.csv
- Latest full dataset: Check portal for most recent semester

**Usage:**
```python
from rns_dataset_lookup import RNSDatasetLookup

lookup = RNSDatasetLookup()
lookup.download_sample_dataset()  # Download sample
result = lookup.lookup_cuit("30712293841")
```

---

## Official Government Websites

### 1. Registro Nacional de Sociedades (RNS)

**Main Website:**
- **URL**: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
- **Purpose**: Search for companies by CUIT or name
- **Provides**: Fecha de contrato social, razón social, domicilio, tipo societario
- **Access**: Public search interface (may require JavaScript)

**Open Data Portal** (Better option!):
- **URL**: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
- **Purpose**: Download complete datasets
- **Format**: CSV/ZIP files
- **Update frequency**: Monthly
- **License**: Creative Commons Attribution 4.0

---

### 2. Inspección General de Justicia (IGJ)

**Main Website:**
- **URL**: https://www.argentina.gob.ar/justicia/igj
- **Purpose**: For companies registered in CABA (Ciudad Autónoma de Buenos Aires)
- **Provides**: Registration data, creation dates, compliance information

**TAD Platform (Trámites a Distancia):**
- **URL**: https://www.argentina.gob.ar/servicio/realizar-un-pedido-de-informes-la-inspeccion-general-de-justicia
- **Purpose**: Request official reports
- **Access**: Requires authentication (Clave Fiscal)
- **Note**: For requesting official certificates, not bulk lookups

---

### 3. ARCA (Agencia de Recaudación y Control Aduanero)

**Main Website:**
- **URL**: https://arca.gob.ar
- **Purpose**: Tax and registration administration
- **Note**: Replaced AFIP for some functions

**ARCA Portal:**
- Requires Clave Fiscal authentication
- Provides tax and registration information
- May have API access for authorized users

---

## Implementation Recommendations

### ✅ Recommended Approach: Use Open Data Portal

1. **Download RNS datasets** from the open data portal
2. **Load into local database/index** for fast lookups
3. **Use `rns_dataset_lookup.py`** script for bulk processing

**Advantages:**
- ✅ No scraping needed
- ✅ Complete, official data
- ✅ Fast bulk lookups
- ✅ No rate limiting
- ✅ Reliable and legal

**Implementation:**
```bash
# Download sample dataset
python rns_dataset_lookup.py --download-sample

# Lookup single CUIT
python rns_dataset_lookup.py --cuit 30712293841

# Bulk lookup from CSV
python rns_dataset_lookup.py --file cuits.csv
```

---

### ⚠️ Alternative: Web Scraping (If needed)

If you need real-time data or the open data portal doesn't have recent updates:

1. **RNS Website Scraping**
   - URL: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
   - Requires: Playwright (JavaScript rendering)
   - May require: Authentication for some queries
   - Use: `cuit_creation_date_lookup.py` (scraping implementation)

2. **IGJ Website Scraping**
   - URL: https://www.argentina.gob.ar/justicia/igj
   - Requires: Playwright + possibly authentication
   - Limited to: CABA companies only

**Note**: Scraping should be a last resort. Always prefer the open data portal!

---

## Dataset Structure

The RNS datasets typically include these columns:

- `cuit` or `cuit_cdi`: Tax identification number
- `razon_social` or `denominacion_social`: Company name
- `fecha_contrato_social`: **Creation date** (this is what we need!)
- `tipo_societario`: Company type (SA, SRL, etc.)
- `domicilio_fiscal`: Tax address
- `domicilio_legal`: Legal address
- `dom_legal_provincia`: Province
- `fecha_actualizacion`: Last update date

---

## Quick Start

1. **Download sample dataset:**
   ```bash
   python rns_dataset_lookup.py --download-sample
   ```

2. **Test lookup:**
   ```bash
   python rns_dataset_lookup.py --cuit 30712293841
   ```

3. **Bulk process:**
   ```bash
   python rns_dataset_lookup.py --file your_cuits.csv
   ```

---

## Contact Information

**RNS Contact:**
- Email: rscq@jus.gob.ar
- Website: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades

**Open Data Portal:**
- Email: datosjusticia@jus.gov.ar
- Portal: https://datos.jus.gob.ar

---

## Legal & Usage Notes

- ✅ Open data portal datasets are **public and free to use**
- ✅ License: Creative Commons Attribution 4.0
- ✅ No authentication required for downloads
- ⚠️ Respect rate limits if scraping websites
- ⚠️ Check terms of service for web scraping
- ✅ Bulk downloads are preferred over individual queries

---

## Related Files

- `rns_dataset_lookup.py` - Recommended: Uses open data portal
- `cuit_creation_date_lookup.py` - Alternative: Web scraping implementation
- `bulk_cuit_creation_date_lookup.py` - Bulk processing script





