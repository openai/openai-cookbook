# Colppy 2030 Bold Goals - Prosperity Calculation

## Overview

This document describes the tools and processes for calculating prosperity metrics for **Colppy 2030 Bold Goals**. One critical piece of information required is **company creation dates** from government registries (RNS - Registro Nacional de Sociedades).

## Purpose

Calculate prosperity metrics by analyzing:
- Company creation dates (from RNS government registry)
- Time from company creation to first Colppy deal close
- Conversion patterns by industry, geography, and company type
- Strategic insights for targeting and lead scoring

## Key Data Point: Company Creation Date

**Source**: RNS (Registro Nacional de Sociedades) - Argentine government registry
**Field**: `fecha_contrato_social` or `fecha_hora_contrato_social`
**Format**: YYYY-MM-DD
**Coverage**: ~2.4M companies in Argentina

## Workflow

### Step 1: Export HubSpot Data

Export all won companies from HubSpot with:
- `CUIT` column (company tax ID)
- `First deal closed won date` column
- Other relevant company data

**Export Location**: HubSpot → Companies → Export
**Required Fields**: CUIT, First deal closed won date

### Step 2: Run Creation to Close Timing Analysis

```bash
cd tools/scripts
python analyze_creation_to_close_timing_v2.py \
    --input ../outputs/hubspot-export.csv \
    --output ../outputs/prosperity_analysis_TIMESTAMP.csv
```

**What it does**:
1. Extracts CUITs from HubSpot export
2. Looks up creation dates in RNS dataset (~2.4M records)
3. Calculates time from creation to deal close
4. Adds enrichment data (company type, province, industry)

**Processing Time**: ~5-10 minutes for 3,000 companies
**Match Rate**: Typically 75-80% (some CUITs are individuals, not companies)

### Step 3: Use Results for Prosperity Calculations

The output CSV contains:
- `rns_creation_date` - **Use this for prosperity calculations**
- `time_to_close_days/months/years` - Conversion timing metrics
- `rns_tipo_societario` - Company type (SRL, SA, etc.)
- `rns_provincia` - Geographic data
- All original HubSpot columns

## Script: `analyze_creation_to_close_timing_v2.py`

### Location
`/tools/scripts/analyze_creation_to_close_timing_v2.py`

### Dependencies
- `rns_dataset_lookup.py` (must be in same directory)
- RNS dataset files in `rns_datasets/` directory
- pandas library

### Usage Examples

```bash
# Basic usage
python analyze_creation_to_close_timing_v2.py --input hubspot-export.csv

# Specify output file
python analyze_creation_to_close_timing_v2.py \
    --input hubspot-export.csv \
    --output prosperity_results.csv

# Quiet mode (no progress updates)
python analyze_creation_to_close_timing_v2.py \
    --input hubspot-export.csv \
    --quiet
```

### Input Requirements

CSV file with:
- **Required**: `CUIT` column (company tax identifier)
- **Required**: `First deal closed won date` column
- **Optional**: Any other HubSpot columns (preserved in output)

### Output Columns

**Original Columns**: All columns from input CSV

**Added Columns**:
- `cuit_normalized` - Normalized CUIT (digits only)
- `cuit_original` - Original CUIT format
- `rns_found` - Whether found in RNS (True/False)
- `rns_creation_date` - **Company creation date (YYYY-MM-DD) - USE FOR PROSPERITY**
- `rns_razon_social` - Official company name
- `rns_tipo_societario` - Company type
- `rns_provincia` - Province
- `time_to_close_days` - Days from creation to close
- `time_to_close_months` - Months from creation to close
- `time_to_close_years` - Years from creation to close
- `time_to_close_formatted` - Human-readable format

## Typical Results

Based on analysis of 2,467 companies:

- **Median time-to-close**: 5.7 years
- **Mean time-to-close**: 10.6 years
- **Fast converters (<1 year)**: 19.3%
- **Mature companies (>10 years)**: 34.1%

### Distribution
- < 6 months: 12.0%
- 6-12 months: 7.2%
- 1-2 years: 8.9%
- 2-5 years: 18.8% (sweet spot)
- 5-10 years: 19.0%
- 10-20 years: 19.8%
- > 20 years: 14.3%

## RNS Dataset Management

### Downloading RNS Dataset

The RNS dataset must be downloaded before running the analysis:

```bash
cd tools/scripts
python rns_dataset_lookup.py --download-sample  # Sample dataset
# OR download full dataset manually from:
# https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
```

### Dataset Location
- **Path**: `tools/scripts/rns_datasets/`
- **Format**: CSV or ZIP containing CSV
- **Size**: ~860MB per semester file
- **Update Frequency**: Monthly

### Dataset Structure

Key columns:
- `cuit` - Company tax ID
- `fecha_hora_contrato_social` - Creation date (with time)
- `razon_social` - Company name
- `tipo_societario` - Company type
- `dom_legal_provincia` - Province

## Use Cases

### 1. Prosperity Calculation (Primary)

**Goal**: Get company creation dates for prosperity metrics

**Process**:
1. Export won companies from HubSpot
2. Run timing analysis script
3. Extract `rns_creation_date` column
4. Use in prosperity calculations

### 2. Strategic Analysis

**Goal**: Understand conversion patterns

**Insights**:
- Which industries convert fastest?
- What company age is optimal for targeting?
- Geographic patterns in conversion timing
- Company type preferences

### 3. Lead Scoring

**Goal**: Prioritize leads based on company age

**Application**:
- Companies 1-5 years old: Higher score
- Companies >10 years old: Lower score
- Industry-specific adjustments

## Troubleshooting

### Low Match Rate (<50%)

**Possible Causes**:
- CUITs are individual CUITs (start with 20-27), not companies (start with 30, 33)
- CUITs not registered in RNS
- Dataset is outdated

**Solutions**:
- Filter for company CUITs only (30-XXXXXXXX-X or 33-XXXXXXXX-X)
- Download latest RNS dataset
- Verify CUIT format

### Dataset Not Found

**Error**: "Dataset not found" or "No CSV file found in ZIP"

**Solution**:
```bash
cd tools/scripts
python rns_dataset_lookup.py --download-sample
# OR manually download from RNS portal
```

### Processing Slow

**For large datasets (>5,000 companies)**:
- Processing takes ~10-15 minutes
- Progress bar shows current status
- Can run in background

## Future Use

This script will be used regularly for:
- **Quarterly**: Prosperity calculations for Colppy 2030 Bold Goals
- **Annual**: Comprehensive prosperity reporting
- **Strategic Planning**: Market analysis and targeting
- **Lead Scoring**: Model updates based on conversion patterns

## Related Documentation

- **Script Documentation**: `/tools/scripts/README_CREATION_TO_CLOSE_TIMING.md`
- **CUIT Lookup**: `/tools/scripts/README_CUIT_CREATION_DATE.md`
- **RNS Dataset**: `/tools/docs/CUIT_CREATION_DATE_LOOKUP.md`

## Quick Reference

```bash
# 1. Export from HubSpot (with CUIT and First deal closed won date)
# 2. Run analysis
cd tools/scripts
python analyze_creation_to_close_timing_v2.py --input ../outputs/hubspot-export.csv

# 3. Use rns_creation_date column for prosperity calculations
```

## Author & Date

Created: December 2025
Purpose: Colppy 2030 Bold Goals - Prosperity Metrics
Maintained by: CEO Office









