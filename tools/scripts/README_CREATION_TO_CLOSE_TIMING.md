# Company Creation to Deal Close Timing Analysis

## Overview

This script analyzes the time between company creation (from RNS - Registro Nacional de Sociedades) and when companies become Colppy customers (first deal closed won date from HubSpot). This analysis is critical for **Colppy 2030 Bold Goals - Prosperity calculations**, as it provides essential data on company creation dates and conversion timing patterns.

## Purpose

- **Primary Use**: Calculate prosperity metrics for Colppy 2030 Bold Goals
- **Key Data Point**: Company creation date from government registries (RNS)
- **Analysis**: Time from company creation to first Colppy deal close
- **Strategic Value**: Identify conversion patterns, optimal company age for targeting, and industry/geographic insights

## Script: `analyze_creation_to_close_timing_v2.py`

### Description

Compares company creation dates from the RNS (Registro Nacional de Sociedades) dataset with HubSpot's "First deal closed won date" to calculate how long it takes companies to become Colppy customers after their legal formation.

### Requirements

- Python 3.x
- pandas
- RNS dataset (downloaded via `rns_dataset_lookup.py`)
- HubSpot CSV export with:
  - `CUIT` column (company tax ID)
  - `First deal closed won date` column

### Usage

```bash
# Basic usage
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv

# Specify output file
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv --output results.csv

# Quiet mode (no progress updates)
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv --quiet
```

### Input File Format

The script expects a HubSpot CSV export with the following columns:
- **Required**: `CUIT` - Company tax identifier
- **Required**: `First deal closed won date` - Date of first closed won deal
- **Optional**: Other HubSpot columns (preserved in output)

### Output

The script generates a CSV file with:
- All original HubSpot columns
- `cuit_normalized` - Normalized CUIT (digits only)
- `cuit_original` - Original CUIT format
- `rns_found` - Whether CUIT was found in RNS dataset (True/False)
- `rns_creation_date` - Company creation date from RNS (YYYY-MM-DD)
- `rns_razon_social` - Official company name from RNS
- `rns_tipo_societario` - Company type (SRL, SA, etc.)
- `rns_provincia` - Province from RNS
- `time_to_close_days` - Days from creation to deal close
- `time_to_close_months` - Months from creation to deal close
- `time_to_close_years` - Years from creation to deal close
- `time_to_close_formatted` - Human-readable format (e.g., "5.7 years (68 months, 2095 days)")

### Progress Feedback

The script provides real-time progress updates:
```
🔍 Processing 1500/3211 (46.7%) - Company Name
```

### Example Output

```
======================================================================
Company Creation to First Deal Close Analysis
======================================================================

📂 Reading HubSpot data from: hubspot-export.csv
✓ Loaded 3,216 companies

📋 Extracting CUITs...
✓ Found 3,211 valid CUITs to lookup

📊 Loading RNS dataset (this may take a moment)...
  Loading CSV file...
✓ Loaded 2,435,103 records from RNS dataset

🔍 Looking up CUITs and calculating timing...
======================================================================
  🔍 Processing 3211/3211 (100.0%) - Last Company

💾 Exporting results...

======================================================================
✅ Analysis Complete!
   Total companies: 3,216
   Valid CUITs: 3,211
   CUITs found in RNS: 2,554 (79.5%)
   Timing calculated: 2,554 (79.5%)

📁 Results exported to: ../outputs/creation_to_close_analysis_TIMESTAMP.csv
======================================================================

📊 Timing Statistics:
   Average: 3865 days (127.0 months, 10.58 years)
   Minimum: 0 days (0.0 months)
   Maximum: 45600 days (1498.0 months, 124.8 years)
   Median: 2095 days
```

## Key Insights from Analysis

### Typical Results (Based on 2,467 companies analyzed)

- **Median time-to-close**: 5.7 years (2,095 days)
- **Mean time-to-close**: 10.6 years (3,865 days)
- **Fast converters (<1 year)**: 19.3% of companies
- **Mature companies (>10 years)**: 34.1% of companies

### Distribution Patterns

- **< 6 months**: 12.0% - Very fast adopters
- **6-12 months**: 7.2%
- **1-2 years**: 8.9%
- **2-5 years**: 18.8% - **Sweet spot for targeting**
- **5-10 years**: 19.0%
- **10-20 years**: 19.8%
- **> 20 years**: 14.3% - Mature companies

### Fastest Converting Industries

1. Seguridad e Higiene - 0.4 years
2. Apuestas y casinos - 1.2 years
3. Venta y mantenimiento de hardware - 1.9 years
4. Industria textil, moda, indumentaria - 4.8 years
5. Video Juegos, gaming y tecnología - 5.1 years

### Company Type Insights

- **SAS (Simplificada)**: 2.3 years average - Fastest
- **SRL**: 8.4 years average - Most common
- **SA**: 12.3 years average
- **ASOCIACION CIVIL**: 34.0 years average - Slowest

## Use Cases

### 1. Colppy 2030 Bold Goals - Prosperity Calculation

**Purpose**: Determine company creation dates for prosperity metrics

**Process**:
1. Export all won companies from HubSpot with "First deal closed won date"
2. Run script to get creation dates from RNS
3. Use `rns_creation_date` for prosperity calculations
4. Analyze timing patterns for strategic insights

### 2. Lead Scoring & Prioritization

**Purpose**: Use company age to score and prioritize leads

**Application**:
- Companies 1-5 years old: Higher score (faster conversion)
- Companies >10 years old: Lower score (slower conversion)
- Industry-specific scoring based on conversion patterns

### 3. Market Segmentation

**Purpose**: Identify optimal target segments

**Segments**:
- **Fast Track**: <1 year old companies
- **Sweet Spot**: 1-5 year old companies
- **Mature Market**: >10 year old companies

### 4. Sales Strategy

**Purpose**: Tailor messaging based on company age

**Approach**:
- New companies: Focus on growth, scalability, modern solutions
- Mature companies: Focus on efficiency, modernization, cost savings

## Related Scripts

- `rns_dataset_lookup.py` - Downloads and manages RNS datasets
- `lookup_cuits_from_csv.py` - Basic CUIT lookup from CSV

## Dependencies

- `rns_dataset_lookup.py` - Must be in same directory
- RNS dataset files in `rns_datasets/` directory
- pandas library

## File Locations

- **Script**: `/tools/scripts/analyze_creation_to_close_timing_v2.py`
- **RNS Lookup**: `/tools/scripts/rns_dataset_lookup.py`
- **Output**: `/tools/outputs/creation_to_close_analysis_*.csv`

## Notes

- The RNS dataset contains ~2.4M company records
- Match rate typically: 75-80% (some CUITs are individuals, not companies)
- Processing time: ~5-10 minutes for 3,000 companies
- Dataset is updated periodically (check RNS portal for latest)

## Future Use

This script will be used regularly for:
- Quarterly prosperity calculations
- Annual Colppy 2030 Bold Goals reporting
- Strategic planning and market analysis
- Lead scoring model updates

## Troubleshooting

**Issue**: "CUIT column not found"
- **Solution**: Ensure CSV has `CUIT` column (case-insensitive)

**Issue**: "No valid CUITs found"
- **Solution**: Check CUIT format in CSV (should be XX-XXXXXXXX-X or digits only)

**Issue**: "Dataset not found"
- **Solution**: Run `rns_dataset_lookup.py` to download dataset first

**Issue**: Low match rate (<50%)
- **Solution**: Verify CUITs are company CUITs (start with 30, 33) not individual CUITs (start with 20-27)

## Author

Created for Colppy 2030 Bold Goals - Prosperity Metrics
Date: December 2025










