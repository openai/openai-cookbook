# CUIT Search Scripts Usage Guide

## Overview

We now have flexible scripts for searching CUIT information for any firm or company in Argentina using cuitonline.com.

## Available Scripts

### 1. `search_firm_cuit.py` - Single Firm Search

Search for any firm/company by name with automatic variations.

#### Basic Usage:
```bash
python search_firm_cuit.py "Firm Name"
```

#### Examples:
```bash
# Basic search
python search_firm_cuit.py "PwC Argentina"

# Search with limited variations
python search_firm_cuit.py --variations 5 "KPMG"

# Use different scraping method
python search_firm_cuit.py --method selenium "Deloitte"

# Run with browser visible (not headless)
python search_firm_cuit.py --no-headless "Ernst & Young"
```

#### Options:
- `--method`: Choose scraping method (requests/selenium/playwright)
- `--variations`: Limit number of name variations to try (default: 10)
- `--no-headless`: Show browser window during search
- `--export`: Export results (default: True)

### 2. `batch_firm_search.py` - Multiple Firms Search

Search for multiple firms at once from a file or command line.

#### From File:
```bash
# Search all firms listed in a text file
python batch_firm_search.py --file firms.txt

# Search from CSV file
python batch_firm_search.py --file accounting_firms.csv
```

#### From Command Line:
```bash
# Search multiple firms directly
python batch_firm_search.py --firms "PwC" "KPMG" "Deloitte" "EY"
```

#### Options:
- `--file/-f`: Read firms from a file
- `--firms/-l`: List firms directly
- `--method/-m`: Scraping method (default: playwright)
- `--variations/-v`: Max variations per firm (default: 5)
- `--output/-o`: Output filename prefix

## Name Variation Algorithm

The scripts automatically generate smart variations of firm names:

1. **Original name** - Always searched first
2. **Remove common suffixes** - S.A., SRL, & Asociados, etc.
3. **Add accounting prefixes** - Estudio, Estudio Contable, etc.
4. **Split by separators** - Try parts of names with &, y, commas
5. **Word combinations** - First/last words, first two words

Example for "Fratantoni, Diez & Asociados":
- Fratantoni, Diez & Asociados (original)
- Fratantoni, Diez (without suffix)
- Fratantoni (first part)
- Diez (second part)
- Estudio Fratantoni
- Estudio Contable Fratantoni

## Output Files

### Single Search Output:
- `outputs/{firm_name}_{timestamp}.csv` - Spreadsheet format
- `outputs/{firm_name}_{timestamp}.json` - Full JSON data

### Batch Search Output:
- `outputs/batch_search_summary_{timestamp}.txt` - Human-readable summary
- `outputs/batch_search_all_results_{timestamp}.csv` - All CUITs in spreadsheet
- `outputs/batch_search_complete_{timestamp}.json` - Complete data with metadata

## Understanding CUIT Prefixes

- **20-**: Individual male
- **27-**: Individual female  
- **23-**: Individual (other)
- **24-**: Individual (other)
- **30-**: Company/Corporation
- **33-**: Company (other type)

## Examples

### Search Big 4 Accounting Firms:
```bash
python batch_firm_search.py --firms "PwC Argentina" "KPMG Argentina" "Deloitte Argentina" "EY Argentina"
```

### Search Local Accounting Firms:
```bash
# Create a file: local_firms.txt
echo "Estudio Carballeira" > local_firms.txt
echo "Fratantoni, Diez & Asociados" >> local_firms.txt
echo "Estudio Contable Rodriguez" >> local_firms.txt

# Run batch search
python batch_firm_search.py --file local_firms.txt
```

### Quick Single Search:
```bash
# Just get the CUIT for one firm quickly
python search_firm_cuit.py "BDO Argentina" --variations 3
```

## Tips

1. **Start with exact name**: Use the firm's official name first
2. **Try variations**: If no results, try simpler versions
3. **Check individuals**: Some firms might be registered under partner names
4. **Use batch for efficiency**: Search multiple firms at once
5. **Export results**: Always exported automatically for record keeping

## Troubleshooting

### No results found:
- Try a simpler name (just last name or main word)
- Check spelling
- Firm might not be on cuitonline.com
- Try searching for individual partners

### Too many results:
- Use more specific search terms
- Add city or location if known
- Filter results by CUIT type (30- for companies)

### Script errors:
- Make sure Playwright is installed: `pip install playwright && playwright install`
- Check internet connection
- Try different method: `--method requests`

## Integration with Other Tools

Results can be used with:
- `automated_cuit_enrichment.py` - Update HubSpot CRM
- `afip_cuit_lookup.py` - Validate with official AFIP API
- Excel/Google Sheets - Import CSV files directly
- Any system that accepts CSV or JSON

## Performance

- Single search: ~5-10 seconds
- Batch search: ~5 seconds per firm
- Rate limited to avoid blocking
- Playwright method most reliable but slower