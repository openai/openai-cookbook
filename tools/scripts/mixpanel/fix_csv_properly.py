#!/usr/bin/env python3
"""
Properly fix CSV files by reading the raw data and reconstructing with proper escaping.
"""

import csv
import sys
import json
import re
from pathlib import Path

def summarize_series_json(json_str: str, max_length: int = 150) -> str:
    """Summarize a series JSON string to be much shorter."""
    try:
        data = json.loads(json_str)
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
            
            # Create very concise summary (max 150 chars)
            if overall is not None:
                summary = f"Total: {overall} | {total_keys} points"
            else:
                summary = f"{total_keys} data points"
            
            # Ensure it's within limit
            if len(summary) > max_length:
                summary = summary[:max_length-3] + "..."
            return summary
        else:
            summary = json_str[:max_length]
            return summary + (" ..." if len(json_str) > max_length else "")
    except (json.JSONDecodeError, TypeError):
        # Not valid JSON, just truncate
        summary = json_str[:max_length]
        return summary + (" ..." if len(json_str) > max_length else "")

def fix_csv_properly(input_file: str, output_file: str = None):
    """Fix CSV file by properly parsing and summarizing series columns."""
    if output_file is None:
        output_file = input_file.replace('.csv', '_fixed.csv')
    
    # Read the raw file content
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to parse as CSV with different strategies
    lines = content.strip().split('\n')
    if len(lines) < 2:
        print(f"❌ Error: CSV file needs at least 2 lines (header + data)")
        return
    
    # Parse header
    header_reader = csv.reader([lines[0]])
    header = next(header_reader)
    
    # Find all columns that might need summarization (series or long JSON columns)
    series_indices = []
    for i, col in enumerate(header):
        if 'series' in col.lower() or 'meta_report_sections' in col.lower():
            series_indices.append(i)
    
    if not series_indices:
        print("ℹ️  No series/meta columns found")
        return
    
    print(f"📊 Processing CSV with {len(header)} columns")
    print(f"📋 Found {len(series_indices)} column(s) to process: {[header[i] for i in series_indices]}")
    
    # Parse data rows - need to handle potential malformed CSV
    fixed_rows = [header]
    
    for line_num, line in enumerate(lines[1:], start=2):
        # Try to parse the row
        reader = csv.reader([line])
        try:
            row = next(reader)
        except Exception as e:
            print(f"⚠️  Warning: Could not parse line {line_num}: {e}")
            continue
        
        # If row has more columns than header, it's likely malformed
        # Try to reconstruct by finding where series data starts
        fixed_row = list(row[:len(header)])
        
        # Process all series/meta columns
        for col_idx in series_indices:
            if col_idx < len(fixed_row):
                col_value = fixed_row[col_idx]
                
                # Check if this value is actually part of a longer JSON that got split
                if len(row) > len(header) and col_idx < len(row):
                    # Reconstruct the full value from remaining columns
                    remaining = row[col_idx:]
                    reconstructed = col_value
                    for i, part in enumerate(remaining[1:], 1):
                        reconstructed += ',' + part
                        # Check if we have a complete JSON structure
                        try:
                            json.loads(reconstructed)
                            fixed_row[col_idx] = reconstructed
                            break
                        except:
                            continue
                    
                    if len(reconstructed) > len(col_value):
                        col_value = reconstructed
                        fixed_row[col_idx] = reconstructed
                
                # Summarize if too long
                if len(col_value) > 150:
                    fixed_row[col_idx] = summarize_series_json(col_value, max_length=150)
                    print(f"  Line {line_num}, Col {col_idx+1} ({header[col_idx]}): {len(col_value)} → {len(fixed_row[col_idx])} chars")
        
        # Ensure row has correct number of columns
        while len(fixed_row) < len(header):
            fixed_row.append('')
        fixed_row = fixed_row[:len(header)]
        
        fixed_rows.append(fixed_row)
    
    # Write fixed CSV with proper escaping
    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(fixed_rows)
    
    print(f"✅ Fixed CSV saved to: {output_file}")
    
    # Verify
    with open(output_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        fixed_rows_check = list(reader)
        if fixed_rows_check:
            max_cell = max(len(cell) for row in fixed_rows_check for cell in row)
            print(f"✅ Max cell length: {max_cell} chars")
            print(f"✅ Columns: {len(fixed_rows_check[0]) if fixed_rows_check else 0}")
            print(f"✅ Status: {'OK' if max_cell < 50000 else 'WARNING'}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_csv_properly.py <input_csv> [output_csv]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(input_file).exists():
        print(f"❌ Error: File not found: {input_file}")
        sys.exit(1)
    
    fix_csv_properly(input_file, output_file)

