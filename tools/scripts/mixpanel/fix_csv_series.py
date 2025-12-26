#!/usr/bin/env python3
"""
Fix CSV files with long series columns by summarizing them better.
"""

import csv
import sys
import json
from pathlib import Path

def summarize_series_value(value: str, max_length: int = 400) -> str:
    """Summarize a series JSON string to be shorter."""
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            total_keys = len(data)
            
            # Extract overall/total if available
            overall = None
            if '$overall' in data:
                overall_data = data['$overall']
                if isinstance(overall_data, dict) and 'all' in overall_data:
                    overall = overall_data['all']
                elif not isinstance(overall_data, dict):
                    overall = overall_data
            
            # Create concise summary
            if overall is not None:
                summary = f"Total: {overall} | {total_keys} data points"
            else:
                # Sample first key-value pair
                first_key = list(data.keys())[0] if data else None
                if first_key:
                    sample = {first_key: data[first_key]}
                    json_str = json.dumps(sample, ensure_ascii=False)
                    if len(json_str) > max_length - 50:
                        json_str = json_str[:max_length - 50]
                    summary = json_str + f" ... [{total_keys} total keys]"
                else:
                    summary = f"{total_keys} data points"
            
            if len(summary) > max_length:
                return summary[:max_length] + " ..."
            return summary
        else:
            # Not a dict, return as is (truncated)
            if len(value) > max_length:
                return value[:max_length] + " ... [truncated]"
            return value
    except (json.JSONDecodeError, TypeError):
        # Not valid JSON, just truncate
        if len(value) > max_length:
            return value[:max_length] + " ... [truncated]"
        return value

def fix_csv(input_file: str, output_file: str = None):
    """Fix CSV file by summarizing long series columns."""
    if output_file is None:
        output_file = input_file.replace('.csv', '_fixed.csv')
    
    with open(input_file, 'r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        rows = list(reader)
    
    if not rows:
        print(f"❌ Error: CSV file is empty")
        return
    
    # Find series columns
    header = rows[0]
    series_indices = [i for i, col in enumerate(header) if 'series' in col.lower()]
    
    if not series_indices:
        print("ℹ️  No series columns found, file may already be optimized")
        return
    
    print(f"📊 Processing {len(rows)-1} data rows")
    print(f"📋 Found {len(series_indices)} series column(s)")
    
    # Process rows
    fixed_rows = [header]  # Keep header as is
    
    for row_idx, row in enumerate(rows[1:], start=1):
        fixed_row = list(row)
        for col_idx in series_indices:
            if col_idx < len(fixed_row):
                original = fixed_row[col_idx]
                if len(original) > 400:
                    fixed_row[col_idx] = summarize_series_value(original, max_length=400)
                    print(f"  Row {row_idx}, Col {col_idx+1}: {len(original)} → {len(fixed_row[col_idx])} chars")
        fixed_rows.append(fixed_row)
    
    # Write fixed CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerows(fixed_rows)
    
    print(f"✅ Fixed CSV saved to: {output_file}")
    
    # Verify
    with open(output_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        fixed_rows_check = list(reader)
        max_cell = max(len(cell) for row in fixed_rows_check for cell in row)
        print(f"✅ Max cell length: {max_cell} chars")
        print(f"✅ Status: {'OK' if max_cell < 50000 else 'WARNING'}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_csv_series.py <input_csv> [output_csv]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(input_file).exists():
        print(f"❌ Error: File not found: {input_file}")
        sys.exit(1)
    
    fix_csv(input_file, output_file)






