#!/usr/bin/env python3
"""
SQL Cycle Time Visualization
============================
Creates visualizations for SQL cycle time analysis from complete_sql_conversion_analysis.py output.
Reuses visualization patterns from generate_visualization_report.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import os
import sys
import argparse
import glob

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 10

# Argentina formatting
import locale
try:
    locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')
except:
    pass

def get_cycle_range(cycle_days):
    """Categorize cycle time into ranges"""
    if pd.isna(cycle_days):
        return 'N/A'
    cycle = float(cycle_days)
    if cycle < 0:
        return 'N/A'
    elif cycle == 0:
        return '0 days'
    elif cycle < 1:
        return '0-1 days'
    elif cycle < 2:
        return '1-2 days'
    elif cycle < 3:
        return '2-3 days'
    elif cycle < 4:
        return '3-4 days'
    elif cycle < 5:
        return '4-5 days'
    elif cycle < 6:
        return '5-6 days'
    elif cycle < 7:
        return '6-7 days'
    elif cycle < 8:
        return '7-8 days'
    elif cycle < 9:
        return '8-9 days'
    elif cycle < 10:
        return '9-10 days'
    else:
        return '10+ days'

def create_cycle_time_distribution_chart(df_contacts):
    """Create cycle time distribution histogram with ranges"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('SQL Cycle Time Distribution', fontsize=16, fontweight='bold')
    
    # Calculate cycle time if not present
    if 'sql_cycle_days' not in df_contacts.columns:
        df_contacts['createdate'] = pd.to_datetime(df_contacts['createdate'])
        df_contacts['sql_date'] = pd.to_datetime(df_contacts['sql_date'])
        df_contacts['sql_cycle_days'] = (df_contacts['sql_date'] - df_contacts['createdate']).dt.total_seconds() / 86400
    
    cycles = df_contacts['sql_cycle_days'].dropna()
    
    # 1. Histogram
    ax1.hist(cycles, bins=30, color='#3498db', edgecolor='black', alpha=0.7)
    ax1.axvline(cycles.mean(), color='#e74c3c', linestyle='--', linewidth=2, label=f'Mean: {cycles.mean():.2f} days')
    ax1.axvline(cycles.median(), color='#2ecc71', linestyle='--', linewidth=2, label=f'Median: {cycles.median():.2f} days')
    ax1.set_xlabel('Cycle Time (Days)', fontweight='bold')
    ax1.set_ylabel('Frequency', fontweight='bold')
    ax1.set_title('Cycle Time Distribution (Histogram)', fontweight='bold')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # 2. Box plot
    bp = ax2.boxplot([cycles], vert=True, patch_artist=True)
    bp['boxes'][0].set_facecolor('#3498db')
    bp['boxes'][0].set_alpha(0.7)
    ax2.set_xticklabels(['SQL Cycle Time'])
    ax2.set_ylabel('Cycle Time (Days)', fontweight='bold')
    ax2.set_title('Cycle Time Distribution (Box Plot)', fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    
    # Add statistics text
    stats_text = f'Mean: {cycles.mean():.2f} days\nMedian: {cycles.median():.2f} days\nMin: {cycles.min():.2f} days\nMax: {cycles.max():.2f} days'
    ax2.text(0.98, 0.98, stats_text, transform=ax2.transAxes, 
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
             fontsize=10)
    
    plt.tight_layout()
    return fig

def create_cycle_time_by_range_chart(df_contacts):
    """Create bar chart showing cycle time distribution by ranges"""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Calculate cycle time if not present
    if 'sql_cycle_days' not in df_contacts.columns:
        df_contacts['createdate'] = pd.to_datetime(df_contacts['createdate'])
        df_contacts['sql_date'] = pd.to_datetime(df_contacts['sql_date'])
        df_contacts['sql_cycle_days'] = (df_contacts['sql_date'] - df_contacts['createdate']).dt.total_seconds() / 86400
    
    df_contacts['cycle_range'] = df_contacts['sql_cycle_days'].apply(get_cycle_range)
    
    all_ranges = ['0 days', '0-1 days', '1-2 days', '2-3 days', '3-4 days', '4-5 days', 
                  '5-6 days', '6-7 days', '7-8 days', '8-9 days', '9-10 days', '10+ days']
    
    # Count by range
    range_counts = df_contacts['cycle_range'].value_counts()
    counts = [range_counts.get(r, 0) for r in all_ranges]
    percentages = [(c / len(df_contacts) * 100) if len(df_contacts) > 0 else 0 for c in counts]
    
    # Color gradient: fast (green) to slow (red)
    colors = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(all_ranges)))
    
    bars = ax.bar(range(len(all_ranges)), counts, color=colors, edgecolor='black', alpha=0.8)
    
    # Add value labels on bars
    for i, (bar, count, pct) in enumerate(zip(bars, counts, percentages)):
        if count > 0:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(count)}\n({pct:.1f}%)',
                   ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    ax.set_xlabel('Cycle Time Range', fontweight='bold', fontsize=12)
    ax.set_ylabel('Count', fontweight='bold', fontsize=12)
    ax.set_title('SQL Cycle Time Distribution by Range (July-December 2025)', fontweight='bold', fontsize=14)
    ax.set_xticks(range(len(all_ranges)))
    ax.set_xticklabels(all_ranges, rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_cycle_time_by_month_chart(df_contacts):
    """Create chart showing cycle time trends by month"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12))
    fig.suptitle('SQL Cycle Time by Month', fontsize=16, fontweight='bold')
    
    # Extract month from createdate
    df_contacts['createdate'] = pd.to_datetime(df_contacts['createdate'])
    df_contacts['sql_date'] = pd.to_datetime(df_contacts['sql_date'])
    
    if 'sql_cycle_days' not in df_contacts.columns:
        df_contacts['sql_cycle_days'] = (df_contacts['sql_date'] - df_contacts['createdate']).dt.total_seconds() / 86400
    
    df_contacts['month'] = df_contacts['createdate'].dt.to_period('M').astype(str)
    
    months = sorted(df_contacts['month'].unique())
    
    # 1. Average and Median cycle time by month
    monthly_stats = df_contacts.groupby('month')['sql_cycle_days'].agg(['mean', 'median', 'count']).reset_index()
    monthly_stats = monthly_stats.sort_values('month')
    
    x = np.arange(len(months))
    width = 0.35
    
    bars1 = ax1.bar(x - width/2, monthly_stats['mean'], width, label='Average', color='#3498db', alpha=0.8)
    bars2 = ax1.bar(x + width/2, monthly_stats['median'], width, label='Median', color='#2ecc71', alpha=0.8)
    
    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.2f}',
                        ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    ax1.set_xlabel('Month', fontweight='bold')
    ax1.set_ylabel('Cycle Time (Days)', fontweight='bold')
    ax1.set_title('Average and Median Cycle Time by Month', fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(months, rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # 2. Cycle time distribution by range, stacked by month
    all_ranges = ['0-1 days', '1-2 days', '2-3 days', '3-4 days', '4-5 days', 
                  '5-6 days', '6-7 days', '7-8 days', '8-9 days', '9-10 days', '10+ days']
    
    df_contacts['cycle_range'] = df_contacts['sql_cycle_days'].apply(get_cycle_range)
    
    # Prepare data for stacked bar chart
    range_data = []
    for month in months:
        month_df = df_contacts[df_contacts['month'] == month]
        month_counts = []
        for r in all_ranges:
            count = len(month_df[month_df['cycle_range'] == r])
            month_counts.append(count)
        range_data.append(month_counts)
    
    range_data = np.array(range_data)
    
    # Create stacked bar chart
    bottom = np.zeros(len(months))
    colors_range = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(all_ranges)))
    
    for i, (r, color) in enumerate(zip(all_ranges, colors_range)):
        ax2.bar(months, range_data[:, i], bottom=bottom, label=r, color=color, alpha=0.8, edgecolor='black')
        bottom += range_data[:, i]
    
    ax2.set_xlabel('Month', fontweight='bold')
    ax2.set_ylabel('Count', fontweight='bold')
    ax2.set_title('Cycle Time Distribution by Month (Stacked)', fontweight='bold')
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_same_day_conversion_trend(df_contacts):
    """Create chart showing same-day conversion rate trend"""
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Extract month and calculate cycle time
    df_contacts['createdate'] = pd.to_datetime(df_contacts['createdate'])
    df_contacts['sql_date'] = pd.to_datetime(df_contacts['sql_date'])
    
    if 'sql_cycle_days' not in df_contacts.columns:
        df_contacts['sql_cycle_days'] = (df_contacts['sql_date'] - df_contacts['createdate']).dt.total_seconds() / 86400
    
    df_contacts['month'] = df_contacts['createdate'].dt.to_period('M').astype(str)
    df_contacts['is_same_day'] = df_contacts['sql_cycle_days'] < 1.0
    
    months = sorted(df_contacts['month'].unique())
    
    monthly_stats = df_contacts.groupby('month').agg({
        'sql_cycle_days': 'count',
        'is_same_day': 'sum'
    }).reset_index()
    monthly_stats.columns = ['month', 'total_sqls', 'same_day_sqls']
    monthly_stats['same_day_pct'] = (monthly_stats['same_day_sqls'] / monthly_stats['total_sqls'] * 100)
    monthly_stats = monthly_stats.sort_values('month')
    
    # Create dual-axis chart
    ax1 = ax
    ax2 = ax1.twinx()
    
    # Bar chart for counts
    bars = ax1.bar(monthly_stats['month'], monthly_stats['same_day_sqls'], 
                   color='#2ecc71', alpha=0.7, label='Same-day SQLs', edgecolor='black')
    
    # Line chart for percentage
    line = ax2.plot(monthly_stats['month'], monthly_stats['same_day_pct'], 
                    color='#e74c3c', marker='o', linewidth=2, markersize=8, label='Same-day %')
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontweight='bold')
    
    for i, (month, pct) in enumerate(zip(monthly_stats['month'], monthly_stats['same_day_pct'])):
        ax2.text(i, pct + 1, f'{pct:.1f}%',
                ha='center', va='bottom', fontweight='bold', color='#e74c3c')
    
    ax1.set_xlabel('Month', fontweight='bold')
    ax1.set_ylabel('Same-day SQL Count', fontweight='bold', color='#2ecc71')
    ax2.set_ylabel('Same-day Conversion Rate (%)', fontweight='bold', color='#e74c3c')
    ax1.set_title('Same-day SQL Conversion Trend by Month', fontweight='bold', fontsize=14)
    ax1.tick_params(axis='y', labelcolor='#2ecc71')
    ax2.tick_params(axis='y', labelcolor='#e74c3c')
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(axis='y', alpha=0.3)
    
    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    return fig

def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description='Visualize SQL Cycle Time Analysis')
    parser.add_argument('--contacts-file', help='Path to SQL contacts CSV file (default: latest from outputs/)')
    parser.add_argument('--output-dir', default='tools/outputs/visualizations', 
                       help='Output directory for visualizations (default: tools/outputs/visualizations)')
    parser.add_argument('--format', choices=['png', 'html'], default='png',
                       help='Output format: png (individual files) or html (combined report)')
    args = parser.parse_args()
    
    # Find contacts file
    if args.contacts_file:
        contacts_file = args.contacts_file
    else:
        files = glob.glob('tools/outputs/complete_sql_contacts_*.csv')
        if not files:
            print("❌ No SQL contacts CSV file found. Run complete_sql_conversion_analysis.py first.")
            sys.exit(1)
        contacts_file = max(files)
        print(f"📁 Using file: {contacts_file}")
    
    # Read data
    print("📊 Loading data...")
    df_contacts = pd.read_csv(contacts_file)
    print(f"✅ Loaded {len(df_contacts)} SQL contacts")
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Generate visualizations
    print("📈 Generating visualizations...")
    
    fig1 = create_cycle_time_distribution_chart(df_contacts)
    fig2 = create_cycle_time_by_range_chart(df_contacts)
    fig3 = create_cycle_time_by_month_chart(df_contacts)
    fig4 = create_same_day_conversion_trend(df_contacts)
    
    # Save figures
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if args.format == 'png':
        fig1.savefig(os.path.join(args.output_dir, f'sql_cycle_time_distribution_{timestamp}.png'), 
                     dpi=300, bbox_inches='tight')
        fig2.savefig(os.path.join(args.output_dir, f'sql_cycle_time_by_range_{timestamp}.png'), 
                     dpi=300, bbox_inches='tight')
        fig3.savefig(os.path.join(args.output_dir, f'sql_cycle_time_by_month_{timestamp}.png'), 
                     dpi=300, bbox_inches='tight')
        fig4.savefig(os.path.join(args.output_dir, f'sql_same_day_trend_{timestamp}.png'), 
                     dpi=300, bbox_inches='tight')
        
        print(f"\n✅ Visualizations saved to {args.output_dir}/")
        print(f"   - sql_cycle_time_distribution_{timestamp}.png")
        print(f"   - sql_cycle_time_by_range_{timestamp}.png")
        print(f"   - sql_cycle_time_by_month_{timestamp}.png")
        print(f"   - sql_same_day_trend_{timestamp}.png")
    
    plt.close('all')
    
    print("\n✅ Visualization generation complete!")

if __name__ == "__main__":
    main()

