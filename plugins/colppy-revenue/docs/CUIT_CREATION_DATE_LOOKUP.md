# CUIT Creation Date Lookup Service

## Overview

This service retrieves creation dates (fecha de constitución) for Argentine CUITs from multiple government sources:

### Official Websites

1. **RNS (Registro Nacional de Sociedades)**
   - **Official Website**: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
   - **Open Data Portal**: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
   - **Best Option**: Download complete datasets (CSV/ZIP) from open data portal
   - Provides: CUIT, razón social, fecha de contrato social (creation date), domicilio, etc.

2. **IGJ (Inspección General de Justicia)**
   - **Official Website**: https://www.argentina.gob.ar/justicia/igj
   - **TAD Platform**: For requesting reports (requires authentication)
   - For companies registered in CABA (Ciudad Autónoma de Buenos Aires)

3. **ARCA/AFIP**
   - Used for validation and company name lookup (does not provide creation dates)
   - Via TusFacturas.app API (requires credentials)

### Recommended Approach

**Use the Open Data Portal** - The RNS dataset is available as downloadable CSV/ZIP files:
- Complete datasets by semester (2019-2025)
- Includes: CUIT, razón social, fecha de contrato social, domicilio fiscal/legal
- Updated monthly
- No scraping needed - direct download!

## Important Limitations

⚠️ **Current Status**: The RNS and IGJ websites are complex and may require:
- Authentication (Clave Fiscal)
- JavaScript rendering (requires Playwright)
- Specific search patterns
- Rate limiting to avoid blocking

**The implementation provided is a framework that may need customization based on:**
- Changes to government website structures
- Authentication requirements
- Anti-scraping measures

## Installation

### Prerequisites

1. **Python 3.8+**
2. **Playwright** (recommended for JavaScript-heavy sites):
   ```bash
   pip install playwright
   playwright install chromium
   ```

3. **Required packages**:
   ```bash
   pip install requests beautifulsoup4
   ```

4. **Optional: AFIP Service** (for company name lookup):
   - Requires TusFacturas.app account with ARCA link
   - Set environment variables:
     ```bash
     export TUSFACTURAS_API_KEY="your_key"
     export TUSFACTURAS_USER_TOKEN="your_token"
     export TUSFACTURAS_API_TOKEN="your_token"
     ```

## Usage

### Single CUIT Lookup

```python
from cuit_creation_date_lookup import CUITCreationDateLookup

service = CUITCreationDateLookup()
result = service.lookup_cuit("30712293841")

if result.creation_date:
    print(f"Creation date: {result.creation_date}")
    print(f"Source: {result.source}")
    print(f"Company: {result.razon_social}")
```

### Bulk Lookup from CSV

```bash
# Create input CSV with CUITs
echo "cuit" > cuits.csv
echo "30712293841" >> cuits.csv
echo "20123456789" >> cuits.csv

# Run bulk lookup
python bulk_cuit_creation_date_lookup.py --input cuits.csv --output results.csv
```

### Input CSV Format

**Simple format:**
```csv
cuit
30712293841
20123456789
30987654321
```

**With additional columns (preserved in output):**
```csv
cuit,company_name,notes
30712293841,Company A,Important client
20123456789,Company B,Follow up needed
```

### Command Line Options

```bash
python bulk_cuit_creation_date_lookup.py \
    --input cuits.csv \
    --output results.csv \
    --no-playwright \    # Disable Playwright (faster but may miss data)
    --no-afip \          # Disable AFIP service
    --rate-limit 3.0     # Seconds between requests
```

## Output Format

The output CSV includes:

- `cuit`: CUIT number
- `creation_date`: Creation date in YYYY-MM-DD format
- `source`: Source of the data (`rns`, `igj`, etc.)
- `razon_social`: Company name (if available from AFIP)
- `error`: Boolean indicating if lookup failed
- `error_message`: Error description if lookup failed
- All original columns from input CSV

## Alternative Solutions

### 1. Third-Party APIs

**Facture.ar API** (may require subscription):
- Documentation: https://docs.facture.ar/api-reference/cuits/obtener-cuits
- May provide creation dates for some CUITs

**Implementation example:**
```python
import requests

def lookup_facture_ar(cuit: str, api_key: str):
    url = f"https://api.facture.ar/v1/cuits/{cuit}"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    data = response.json()
    return data.get('fecha_constitucion')
```

### 2. Manual RNS/IGJ Search

For small batches, you can manually search:
- **RNS**: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
- **IGJ**: https://www.argentina.gob.ar/justicia/tramites-y-servicios/sociedades

### 3. ARCA Direct Access

If you have Clave Fiscal access:
- ARCA portal: https://arca.gob.ar
- Requires authentication and may have API access

### 4. Commercial Data Providers

Consider commercial services that aggregate government data:
- May have APIs with creation dates
- Usually require subscription
- Examples: Nosis, Informes Empresariales

## Customization Guide

### Adapting RNS Scraper

The RNS website structure may change. To adapt:

1. **Inspect the website**:
   - Open https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
   - Use browser DevTools to inspect search form
   - Identify form fields and submission method

2. **Update selectors** in `_lookup_rns_playwright()`:
   ```python
   # Update these selectors based on actual page structure
   search_input = page.query_selector('input[name="cuit"]')
   submit_button = page.query_selector('button[type="submit"]')
   ```

3. **Extract creation date**:
   - Look for "Fecha de Contrato Social" or similar
   - May be in a table, div, or specific element
   - Update parsing logic accordingly

### Adapting IGJ Scraper

Similar process for IGJ:
1. Inspect IGJ search interface
2. Update selectors and parsing logic
3. Handle authentication if required

## Rate Limiting & Best Practices

- **Default rate limit**: 2 seconds between requests
- **Respectful scraping**: Don't overwhelm government servers
- **Error handling**: Service handles timeouts and errors gracefully
- **Retry logic**: Consider implementing retry for failed requests

## Troubleshooting

### "Playwright not available"
- Install: `pip install playwright && playwright install chromium`

### "Creation date not found"
- Government sites may require authentication
- Website structure may have changed
- CUIT may not be registered in RNS/IGJ
- Try manual search to verify

### "Rate limiting issues"
- Increase `--rate-limit` parameter
- Reduce batch size
- Add delays between batches

### "AFIP service not available"
- This is optional - service works without it
- AFIP only provides company name, not creation date
- Set credentials if you want company names in results

## Legal Considerations

⚠️ **Important**:
- Respect website terms of service
- Don't abuse rate limits
- Consider contacting government agencies for official API access
- Ensure compliance with data protection regulations
- Some data may require authorization to access

## Future Improvements

Potential enhancements:
1. **Caching**: Store results to avoid re-querying
2. **Parallel processing**: Process multiple CUITs concurrently (with rate limiting)
3. **Multiple date sources**: Try different date fields (fecha contrato, fecha inscripción, etc.)
4. **Validation**: Cross-reference dates from multiple sources
5. **API integration**: Integrate with commercial APIs if available

## Support

For issues:
1. Check if government websites are accessible
2. Verify CUIT format (11 digits)
3. Test with a known CUIT manually
4. Review error messages for specific issues
5. Consider manual verification for critical data

## Related Scripts & Analysis

### Creation to Close Timing Analysis

**For Colppy 2030 Bold Goals - Prosperity Calculations**

The `analyze_creation_to_close_timing_v2.py` script extends CUIT creation date lookup to analyze conversion timing:

**Purpose**: Calculate time from company creation (RNS) to first Colppy deal close (HubSpot)

**Key Use Case**: Prosperity metrics for Colppy 2030 Bold Goals - requires company creation dates

**Usage**:
```bash
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv
```

**Output**: CSV with creation dates, timing calculations, and analysis metrics

**Full Documentation**: See `../scripts/README_CREATION_TO_CLOSE_TIMING.md`

## Related Documentation

- [AFIP CUIT Lookup Service](./AFIP_API_README.md) - For company information (not creation dates)
- [CUIT Scraping Tools](../scripts/requirements_scraping.txt) - Dependencies
- [Creation to Close Timing Analysis](../scripts/README_CREATION_TO_CLOSE_TIMING.md) - For prosperity calculations

