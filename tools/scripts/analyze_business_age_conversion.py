#!/usr/bin/env python3
"""
Business Age vs Conversion Analysis
====================================
Joins local SQLite companies (with CUITs) against the RNS dataset to get
incorporation dates, then correlates business age with deal outcomes.

Goal: Validate whether business age is a useful lead quality signal.

Data sources:
- facturacion_hubspot.db: companies (CUIT, type) + deals (stage, amount, close_date)
- RNS dataset: fecha_hora_contrato_social (incorporation date), actividad_descripcion
"""

import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR.parent / "data" / "facturacion_hubspot.db"
RNS_DIR = SCRIPT_DIR / "rns_datasets"


def load_companies_with_deals() -> pd.DataFrame:
    """Load companies joined with their deals from local SQLite DB."""
    conn = sqlite3.connect(str(DB_PATH))

    query = """
    SELECT
        c.cuit,
        c.hubspot_id as company_hubspot_id,
        c.name as company_name,
        c.type as company_type,
        c.tipo_icp_contador,
        d.deal_stage,
        d.amount,
        d.close_date,
        d.deal_name,
        da.association_type_id
    FROM companies c
    JOIN deal_associations da ON c.hubspot_id = da.company_hubspot_id
    JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
    WHERE c.cuit IS NOT NULL
      AND c.cuit != ''
      AND c.cuit != '20000000001'
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"Loaded {len(df)} company-deal records ({df['cuit'].nunique()} unique CUITs)")
    return df


def load_rns_dataset() -> pd.DataFrame:
    """Load the most recent RNS dataset."""
    csv_files = sorted(RNS_DIR.glob("*.csv"), reverse=True)

    if not csv_files:
        raise FileNotFoundError(f"No RNS CSV files found in {RNS_DIR}")

    latest = csv_files[0]
    print(f"Loading RNS dataset: {latest.name}...")

    # Only load columns we need (saves memory)
    usecols = [
        'cuit', 'razon_social', 'fecha_hora_contrato_social',
        'tipo_societario', 'actividad_descripcion', 'actividad_codigo',
        'actividad_orden', 'dom_fiscal_provincia'
    ]

    df = pd.read_csv(
        latest,
        encoding='utf-8',
        on_bad_lines='skip',
        usecols=lambda c: c in usecols,
        low_memory=False
    )

    df.columns = df.columns.str.lower().str.strip()

    # Keep only primary activity (actividad_orden == 1 or first per CUIT)
    if 'actividad_orden' in df.columns:
        df_primary = df[df['actividad_orden'] == 1].drop_duplicates(subset=['cuit'], keep='first')
    else:
        df_primary = df.drop_duplicates(subset=['cuit'], keep='first')

    print(f"RNS loaded: {len(df)} total rows, {len(df_primary)} unique CUITs (primary activity)")
    return df_primary


def parse_rns_date(date_str):
    """Parse RNS date format (e.g. '1912-04-30-00:00' or '2020-01-15')."""
    if pd.isna(date_str):
        return pd.NaT

    date_str = str(date_str).strip()

    # Handle format 'YYYY-MM-DD-HH:MM'
    if len(date_str) > 10:
        date_str = date_str[:10]

    try:
        return pd.to_datetime(date_str, format='%Y-%m-%d')
    except (ValueError, TypeError):
        return pd.NaT


def classify_deal_outcome(stage: str) -> str:
    """Map deal stage to human-readable outcome."""
    mapping = {
        'closedwon': 'Won',
        'closedlost': 'Lost',
        '31849274': 'Churned',
        '34692158': 'Recovered',
    }
    return mapping.get(stage, 'Other')


def analyze_business_age_vs_conversion(merged: pd.DataFrame, reference_date: str | None = None):
    """Core analysis: does business age predict conversion?

    Args:
        merged: Joined company-deals + RNS data.
        reference_date: Date for business age calculation (YYYY-MM-DD). Default: today.
    """
    if reference_date is None:
        reference_date = datetime.now().strftime("%Y-%m-%d")
    ref_ts = pd.Timestamp(reference_date)

    print("\n" + "=" * 70)
    print("BUSINESS AGE vs CONVERSION ANALYSIS")
    print("=" * 70)

    # --- 1. Overall match rate ---
    total_companies = merged['cuit'].nunique()
    matched = merged[merged['incorporation_date'].notna()]['cuit'].nunique()
    print(f"\n--- Match Rate ---")
    print(f"Companies with CUITs: {total_companies}")
    print(f"Matched in RNS:       {matched} ({matched/total_companies*100:.1f}%)")
    print(f"Not in RNS:           {total_companies - matched} (likely monotributistas/individuals)")

    # Filter to matched only
    df = merged[merged['incorporation_date'].notna()].copy()

    if len(df) == 0:
        print("No matches found. Cannot proceed with analysis.")
        return

    # --- 2. Business age distribution ---
    df['business_age_years'] = (ref_ts - df['incorporation_date']).dt.days / 365.25

    # Filter out unreasonable ages (before 1900 or future dates)
    df = df[(df['business_age_years'] > 0) & (df['business_age_years'] < 130)]

    print(f"\n--- Business Age Distribution (years) ---")
    print(f"Mean:   {df['business_age_years'].mean():.1f}")
    print(f"Median: {df['business_age_years'].median():.1f}")
    print(f"Min:    {df['business_age_years'].min():.1f}")
    print(f"Max:    {df['business_age_years'].max():.1f}")

    # --- 3. Age buckets ---
    age_bins = [0, 2, 5, 10, 20, 50, 130]
    age_labels = ['0-2y', '2-5y', '5-10y', '10-20y', '20-50y', '50y+']
    df['age_bucket'] = pd.cut(df['business_age_years'], bins=age_bins, labels=age_labels)

    # --- 4. Conversion by age bucket ---
    print(f"\n--- Deal Outcomes by Business Age ---")

    # One row per CUIT + deal combination
    outcome_by_age = df.groupby(['age_bucket', 'outcome']).agg(
        deal_count=('cuit', 'count'),
        avg_amount=('amount_num', 'mean')
    ).reset_index()

    pivot = outcome_by_age.pivot_table(
        index='age_bucket',
        columns='outcome',
        values='deal_count',
        fill_value=0,
        observed=True
    )

    # Add totals and win rate
    pivot['Total'] = pivot.sum(axis=1)
    if 'Won' in pivot.columns:
        pivot['Win Rate'] = (pivot['Won'] / pivot['Total'] * 100).round(1)
    if 'Churned' in pivot.columns:
        pivot['Churn Rate'] = (pivot['Churned'] / pivot['Total'] * 100).round(1)

    print(pivot.to_string())

    # --- 5. By company type (ICP) ---
    print(f"\n--- Business Age by Company Type ---")
    type_age = df.groupby('company_type').agg(
        count=('cuit', 'nunique'),
        mean_age=('business_age_years', 'mean'),
        median_age=('business_age_years', 'median')
    ).sort_values('count', ascending=False)

    print(type_age.to_string())

    # --- 6. Win rate by age AND company type ---
    if df['company_type'].notna().any():
        print(f"\n--- Win Rate by Age Bucket + Company Type ---")
        for ctype in ['Cuenta Contador', 'Cuenta Pyme']:
            subset = df[df['company_type'] == ctype]
            if len(subset) == 0:
                continue

            print(f"\n  {ctype}:")
            type_pivot = subset.groupby(['age_bucket', 'outcome']).size().reset_index(name='count')
            type_table = type_pivot.pivot_table(
                index='age_bucket', columns='outcome', values='count', fill_value=0, observed=True
            )
            type_table['Total'] = type_table.sum(axis=1)
            if 'Won' in type_table.columns:
                type_table['Win Rate'] = (type_table['Won'] / type_table['Total'] * 100).round(1)
            print(f"  {type_table.to_string()}")

    # --- 7. Activity description analysis ---
    if 'actividad_descripcion' in df.columns:
        print(f"\n--- Top Activities by Outcome ---")

        for outcome in ['Won', 'Lost', 'Churned']:
            subset = df[df['outcome'] == outcome]
            if len(subset) == 0:
                continue

            top_activities = subset['actividad_descripcion'].value_counts().head(10)
            print(f"\n  {outcome} (top 10 activities):")
            for act, count in top_activities.items():
                if pd.notna(act):
                    print(f"    {count:4d}  {act[:80]}")

    # --- 8. Average deal amount by age bucket ---
    print(f"\n--- Avg Deal Amount (ARS) by Business Age ---")
    amount_by_age = df[df['amount_num'] > 0].groupby('age_bucket', observed=True).agg(
        avg_amount=('amount_num', 'mean'),
        median_amount=('amount_num', 'median'),
        deal_count=('cuit', 'count')
    )
    print(amount_by_age.to_string())

    # --- 9. Tipo societario analysis ---
    if 'tipo_societario' in df.columns:
        print(f"\n--- Win Rate by Tipo Societario ---")
        tipo_outcomes = df.groupby(['tipo_societario', 'outcome']).size().reset_index(name='count')
        tipo_pivot = tipo_outcomes.pivot_table(
            index='tipo_societario', columns='outcome', values='count', fill_value=0, observed=True
        )
        tipo_pivot['Total'] = tipo_pivot.sum(axis=1)
        if 'Won' in tipo_pivot.columns:
            tipo_pivot['Win Rate'] = (tipo_pivot['Won'] / tipo_pivot['Total'] * 100).round(1)
        tipo_pivot = tipo_pivot.sort_values('Total', ascending=False)
        print(tipo_pivot.to_string())

    # --- 10. Key takeaways ---
    print(f"\n{'=' * 70}")
    print("KEY FINDINGS SUMMARY")
    print("=" * 70)

    if 'Won' in pivot.columns and 'Win Rate' in pivot.columns:
        best_bucket = pivot['Win Rate'].idxmax()
        worst_bucket = pivot['Win Rate'].idxmin()
        overall_wr = pivot['Won'].sum() / pivot['Total'].sum() * 100

        print(f"Overall win rate:        {overall_wr:.1f}%")
        print(f"Best age bucket:         {best_bucket} ({pivot.loc[best_bucket, 'Win Rate']:.1f}% win rate)")
        print(f"Worst age bucket:        {worst_bucket} ({pivot.loc[worst_bucket, 'Win Rate']:.1f}% win rate)")
        print(f"Spread:                  {pivot['Win Rate'].max() - pivot['Win Rate'].min():.1f} pp")

        if pivot['Win Rate'].max() - pivot['Win Rate'].min() > 5:
            print(f"\n→ SIGNAL DETECTED: {pivot['Win Rate'].max() - pivot['Win Rate'].min():.1f}pp spread in win rate across age buckets.")
            print(f"  Business age appears to be a meaningful lead quality signal.")
        else:
            print(f"\n→ WEAK SIGNAL: Only {pivot['Win Rate'].max() - pivot['Win Rate'].min():.1f}pp spread.")
            print(f"  Business age alone may not be a strong enough signal.")


def main():
    """Run the full analysis pipeline."""
    import argparse
    parser = argparse.ArgumentParser(description="Business age vs conversion analysis")
    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        help="Reference date for business age (YYYY-MM-DD). Default: today. Use RNS dataset date when available.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("BUSINESS AGE vs CONVERSION - HYPOTHESIS VALIDATION")
    print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Step 1: Load companies + deals from SQLite
    print("\n[1/4] Loading companies and deals from local DB...")
    company_deals = load_companies_with_deals()

    # Step 2: Load RNS dataset
    print("\n[2/4] Loading RNS dataset...")
    rns = load_rns_dataset()

    # Step 3: Join on CUIT
    print("\n[3/4] Joining datasets on CUIT...")

    # Normalize CUITs for join
    company_deals['cuit_clean'] = company_deals['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)
    rns['cuit_clean'] = rns['cuit'].astype(str).str.replace(r'[-\s\.]', '', regex=True)

    merged = company_deals.merge(
        rns[['cuit_clean', 'razon_social', 'fecha_hora_contrato_social',
             'tipo_societario', 'actividad_descripcion', 'actividad_codigo',
             'dom_fiscal_provincia']],
        on='cuit_clean',
        how='left',
        suffixes=('', '_rns')
    )

    # Parse dates
    merged['incorporation_date'] = merged['fecha_hora_contrato_social'].apply(parse_rns_date)

    # Parse deal amounts
    merged['amount_num'] = pd.to_numeric(merged['amount'], errors='coerce').fillna(0)

    # Classify outcomes
    merged['outcome'] = merged['deal_stage'].apply(classify_deal_outcome)

    match_rate = merged['incorporation_date'].notna().mean()
    print(f"Join complete. Match rate: {match_rate*100:.1f}%")

    # Step 4: Analyze
    print("\n[4/4] Running analysis...")
    analyze_business_age_vs_conversion(merged, reference_date=args.reference_date)

    # Save merged dataset for further exploration
    output_dir = SCRIPT_DIR.parent / "data"
    output_file = output_dir / "business_age_analysis.csv"

    export_cols = [
        'cuit', 'company_name', 'company_type', 'tipo_icp_contador',
        'deal_stage', 'outcome', 'amount_num', 'close_date',
        'incorporation_date', 'tipo_societario', 'actividad_descripcion',
        'actividad_codigo', 'dom_fiscal_provincia'
    ]
    available_cols = [c for c in export_cols if c in merged.columns]
    merged[available_cols].to_csv(str(output_file), index=False)
    print(f"\nDetailed data exported to: {output_file}")


if __name__ == "__main__":
    main()
