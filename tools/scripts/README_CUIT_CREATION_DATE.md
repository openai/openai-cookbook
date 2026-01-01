# Quick Start: CUIT Creation Date Lookup

## Overview

Get creation dates (fecha de constitución) for Argentine CUITs from government registries.

**🎯 RECOMMENDED: Use the Open Data Portal** - Much better than scraping!

**Official Websites:**
- **RNS Open Data Portal**: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
- **RNS Website**: https://www.argentina.gob.ar/justicia/registro-nacional-sociedades
- **IGJ Website**: https://www.argentina.gob.ar/justicia/igj

## Quick Setup

### Option 1: Open Data Portal (Recommended - No Scraping!)

```bash
# Install dependencies
pip install pandas requests

# Download sample dataset
python rns_dataset_lookup.py --download-sample

# Lookup single CUIT
python rns_dataset_lookup.py --cuit 30712293841

# Bulk lookup from CSV
python rns_dataset_lookup.py --file cuits.csv
```

### Option 2: Web Scraping (Alternative)

```bash
# Install dependencies
pip install playwright beautifulsoup4 requests
playwright install chromium

# Optional: Set AFIP credentials (for company names)
export TUSFACTURAS_API_KEY="your_key"
export TUSFACTURAS_USER_TOKEN="your_token"
export TUSFACTURAS_API_TOKEN="your_token"

# Run bulk lookup
python bulk_cuit_creation_date_lookup.py --input example_cuits.csv
```

## Usage

### 1. Prepare your CUIT list

Create a CSV file with CUITs:

```csv
cuit
30712293841
20123456789
30987654321
```

### 2. Run lookup (Open Data Portal - Recommended)

```bash
cd tools/scripts
python rns_dataset_lookup.py --file cuits.csv
```

### 3. Check results

Results are saved to `rns_lookup_results_TIMESTAMP.csv`

## Output Format

| cuit | creation_date | source | razon_social | error | error_message |
|------|---------------|--------|--------------|-------|---------------|
| 30712293841 | 2010-05-15 | rns | Company Name | False | |

## Important Notes

⚠️ **The RNS and IGJ websites may require:**
- JavaScript rendering (Playwright handles this)
- Authentication (Clave Fiscal) for some queries
- Specific search patterns

**The implementation is a framework** - you may need to customize selectors based on actual website structure.

## Alternative: Third-Party APIs

If scraping doesn't work, consider:
- **Facture.ar API**: https://docs.facture.ar
- **Commercial data providers**: Nosis, Informes Empresariales
- **Manual search**: RNS website for small batches

## Troubleshooting

- **"Playwright not available"**: Run `pip install playwright && playwright install chromium`
- **"Creation date not found"**: Website structure may have changed or requires authentication
- **Rate limiting**: Increase `--rate-limit` parameter

## Related Scripts

### Creation to Close Timing Analysis

For **Colppy 2030 Bold Goals - Prosperity calculations**, use the timing analysis script:

```bash
# Analyze time from company creation to first deal close
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv
```

This script:
- Compares RNS creation dates with HubSpot "First deal closed won date"
- Calculates time-to-close metrics
- Provides company creation dates for prosperity calculations
- Generates comprehensive analysis with industry/geographic insights

**Full Documentation**: See `README_CREATION_TO_CLOSE_TIMING.md`

## Full Documentation

See: `../docs/CUIT_CREATION_DATE_LOOKUP.md`

