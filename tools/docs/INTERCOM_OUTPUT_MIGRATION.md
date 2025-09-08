# Intercom Output Directory Migration

## Overview
This document records the migration of Intercom report outputs from the dedicated `tools/intercom_reports/` directory to the unified `tools/outputs/` directory structure.

## Changes Made

### 1. Updated Script Default Output Directories

The following scripts were updated to use `tools/outputs` as the default output directory instead of `intercom_reports`:

- `tools/scripts/intercom/intercom_analytics.py`
  - Changed default `output_dir` parameter from `'intercom_reports'` to `'tools/outputs'`
  - Updated command-line argument default from `'intercom_reports'` to `'tools/outputs'`

- `tools/scripts/intercom/run_intercom_analysis.py`
  - Changed default `--output-dir` argument from `'intercom_reports'` to `'tools/outputs'`

### 2. Updated Hardcoded Output Paths

The following scripts had hardcoded absolute paths updated:

- `tools/scripts/intercom/working_sla_analysis.py`
- `tools/scripts/intercom/thursday_analysis.py`
- `tools/scripts/intercom/august_2025_batch_analysis.py`
- `tools/scripts/intercom/complete_friday_analysis.py`
- `tools/scripts/intercom/final_sla_analysis.py`
- `tools/scripts/intercom/full_cycle_sla_analysis.py`

All paths changed from:
```
/Users/virulana/openai-cookbook/tools/intercom_reports/
```
to:
```
/Users/virulana/openai-cookbook/tools/outputs/
```

### 3. Updated Input File References

The following scripts were updated to read from the new outputs directory:

- `tools/scripts/intercom/label_analysis.py`
- `tools/scripts/intercom/corrected_sla_analysis.py`
- `tools/scripts/intercom/csat_comprehensive_analysis.py`

### 4. File Migration

All existing files from `tools/intercom_reports/` were moved to `tools/outputs/`:

- JSON analysis files (e.g., `august_2025_analysis_20250829_225811.json`)
- CSV data files (e.g., `csat.csv`, `conversation_metrics.csv`)
- PNG visualization files (e.g., `conversation_volume.png`, `first_response_time.png`)
- All other Intercom-related output files

### 5. Directory Cleanup

The now-empty `tools/intercom_reports/` directory was removed.

## Benefits

1. **Unified Output Structure**: All tool outputs now go to the same `tools/outputs/` directory
2. **Consistency**: Follows the same pattern as other tools (HubSpot, Mixpanel, Google Ads)
3. **Easier Management**: Single location for all output files
4. **Better Organization**: Reduces directory clutter in the tools folder

## Future Usage

All new Intercom scripts should:
- Use `tools/outputs` as the default output directory
- Accept `--output-dir` parameter to allow customization
- Follow the same naming conventions as other tools

## Migration Date
September 2, 2025
