#!/usr/bin/env python3
"""
Generate Visualization Report for High Score Sales Handling Analysis
===================================================================
Creates a comprehensive HTML report with visualizations from the CSV data.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import base64
from io import BytesIO
import os
import sys
import argparse

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10

# Argentina formatting
import locale
try:
    locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')
except:
    pass

def fig_to_base64(fig):
    """Convert matplotlib figure to base64 string for HTML embedding"""
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode()
    buf.close()
    plt.close(fig)
    return img_str

def create_owner_performance_chart(df_owners):
    """Create bar chart for owner performance metrics"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Desempeño por Owner', fontsize=16, fontweight='bold')
    
    # Sort by total contacts
    df_sorted = df_owners.sort_values('total_contacts', ascending=False)
    
    # 1. Total Contacts
    ax1 = axes[0, 0]
    colors1 = ['#2ecc71' if x > 0 else '#e74c3c' for x in df_sorted['contacted']]
    bars1 = ax1.barh(df_sorted['owner_name'], df_sorted['total_contacts'], color=colors1)
    ax1.set_xlabel('Total Contactos', fontweight='bold')
    ax1.set_title('Total Contactos Score 40+', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # 2. Contact Rate
    ax2 = axes[0, 1]
    colors2 = ['#3498db' if x >= 20 else '#e74c3c' if x == 0 else '#f39c12' for x in df_sorted['contact_rate']]
    bars2 = ax2.barh(df_sorted['owner_name'], df_sorted['contact_rate'], color=colors2)
    ax2.set_xlabel('Tasa de Contacto (%)', fontweight='bold')
    ax2.set_title('Tasa de Contacto por Owner', fontweight='bold')
    ax2.set_xlim(0, 105)
    ax2.grid(axis='x', alpha=0.3)
    
    # 3. SQL Conversion Rate
    ax3 = axes[1, 0]
    colors3 = ['#27ae60' if x > 0 else '#95a5a6' for x in df_sorted['sql_rate']]
    bars3 = ax3.barh(df_sorted['owner_name'], df_sorted['sql_rate'], color=colors3)
    ax3.set_xlabel('Tasa SQL (%)', fontweight='bold')
    ax3.set_title('Tasa de Conversión SQL', fontweight='bold')
    ax3.grid(axis='x', alpha=0.3)
    
    # 4. PQL Conversion Rate
    ax4 = axes[1, 1]
    colors4 = ['#9b59b6' if x > 0 else '#95a5a6' for x in df_sorted['pql_rate']]
    bars4 = ax4.barh(df_sorted['owner_name'], df_sorted['pql_rate'], color=colors4)
    ax4.set_xlabel('Tasa PQL (%)', fontweight='bold')
    ax4.set_title('Tasa de Conversión PQL', fontweight='bold')
    ax4.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_engagement_metrics_chart(df_contacts):
    """Create pie charts for engagement metrics"""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('Métricas de Engagement', fontsize=16, fontweight='bold')
    
    # 1. Contacted vs Not Contacted
    ax1 = axes[0]
    contacted = df_contacts['is_contacted'].sum()
    not_contacted = len(df_contacts) - contacted
    ax1.pie([contacted, not_contacted], 
            labels=[f'Contactados\n{contacted} ({contacted/len(df_contacts)*100:.1f}%)',
                   f'No Contactados\n{not_contacted} ({not_contacted/len(df_contacts)*100:.1f}%)'],
            colors=['#2ecc71', '#e74c3c'],
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontweight': 'bold'})
    ax1.set_title('Estado de Contacto', fontweight='bold', fontsize=12)
    
    # 2. SQL Conversions
    ax2 = axes[1]
    sql = df_contacts['is_sql'].sum()
    not_sql = len(df_contacts) - sql
    ax2.pie([sql, not_sql],
            labels=[f'SQL\n{sql} ({sql/len(df_contacts)*100:.1f}%)',
                   f'No SQL\n{not_sql} ({not_sql/len(df_contacts)*100:.1f}%)'],
            colors=['#3498db', '#ecf0f1'],
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontweight': 'bold'})
    ax2.set_title('Conversiones SQL', fontweight='bold', fontsize=12)
    
    # 3. PQL Conversions
    ax3 = axes[2]
    pql = df_contacts['is_pql'].sum()
    not_pql = len(df_contacts) - pql
    ax3.pie([pql, not_pql],
            labels=[f'PQL\n{pql} ({pql/len(df_contacts)*100:.1f}%)',
                   f'No PQL\n{not_pql} ({not_pql/len(df_contacts)*100:.1f}%)'],
            colors=['#9b59b6', '#ecf0f1'],
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontweight': 'bold'})
    ax3.set_title('Conversiones PQL', fontweight='bold', fontsize=12)
    
    plt.tight_layout()
    return fig

def create_time_distribution_chart(df_contacts):
    """Create time to contact distribution chart"""
    contacted_df = df_contacts[df_contacts['is_contacted'] == True].copy()
    
    if len(contacted_df) == 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'No hay datos de contacto disponibles', 
                ha='center', va='center', fontsize=14)
        ax.set_title('Distribución de Tiempo a Contacto', fontweight='bold')
        return fig
    
    # Create time buckets
    contacted_df['time_bucket'] = pd.cut(
        contacted_df['days_to_contact'],
        bins=[0, 1, 3, 7, float('inf')],
        labels=['0-1 día', '1-3 días', '3-7 días', '7+ días']
    )
    
    time_dist = contacted_df['time_bucket'].value_counts().sort_index()
    
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ['#2ecc71', '#3498db', '#f39c12', '#e74c3c']
    bars = ax.bar(time_dist.index, time_dist.values, color=colors[:len(time_dist)])
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{int(height)}\n({height/len(contacted_df)*100:.1f}%)',
               ha='center', va='bottom', fontweight='bold')
    
    ax.set_ylabel('Cantidad de Contactos', fontweight='bold')
    ax.set_xlabel('Rango de Tiempo', fontweight='bold')
    ax.set_title('Distribución de Tiempo a Primer Contacto', fontweight='bold', fontsize=14)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_score_distribution_chart(df_contacts):
    """Create score distribution histogram"""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create score buckets
    bins = [40, 45, 50, 55, 60, 70, 80, 90, 100]
    labels = ['40-44', '45-49', '50-54', '55-59', '60-69', '70-79', '80-89', '90-100']
    
    df_contacts['score_bucket'] = pd.cut(df_contacts['score'], bins=bins, labels=labels)
    score_dist = df_contacts['score_bucket'].value_counts().sort_index()
    
    colors = plt.cm.viridis(np.linspace(0, 1, len(score_dist)))
    bars = ax.bar(score_dist.index, score_dist.values, color=colors)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{int(height)}',
               ha='center', va='bottom', fontweight='bold')
    
    ax.set_ylabel('Cantidad de Contactos', fontweight='bold')
    ax.set_xlabel('Rango de Score', fontweight='bold')
    ax.set_title('Distribución de Scores (40+)', fontweight='bold', fontsize=14)
    ax.grid(axis='y', alpha=0.3)
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    return fig

def create_uncontacted_breakdown_chart(df_contacts):
    """Create chart showing uncontacted contacts by owner"""
    uncontacted = df_contacts[df_contacts['is_contacted'] == False]
    owner_counts = uncontacted['owner_name'].value_counts().head(10)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = ['#e74c3c' if x > 50 else '#f39c12' for x in owner_counts.values]
    bars = ax.barh(owner_counts.index, owner_counts.values, color=colors)
    
    # Add value labels
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2.,
               f'{int(width)}',
               ha='left', va='center', fontweight='bold', fontsize=10)
    
    ax.set_xlabel('Cantidad de Contactos No Contactados', fontweight='bold')
    ax.set_title('Top 10 Owners - Contactos No Contactados (Score 40+)', fontweight='bold', fontsize=14)
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_conversion_funnel_chart(df_contacts):
    """Create conversion funnel visualization with strict temporal order: Created → PQL → SQL"""
    total = len(df_contacts)
    
    # Convert dates to datetime for comparison
    df_contacts['createdate_dt'] = pd.to_datetime(df_contacts['createdate'], errors='coerce')
    df_contacts['pql_date_dt'] = pd.to_datetime(df_contacts['pql_date'], errors='coerce')
    df_contacts['sql_date_dt'] = pd.to_datetime(df_contacts['sql_date'], errors='coerce')
    
    # Strict sequential funnel: createdate < pql_date < sql_date
    # Stage 1: Total contacts (all contacts created in period)
    total_contacts = total
    
    # Stage 2: PQL (must have pql_date after createdate)
    pql_strict = df_contacts[
        (df_contacts['is_pql'] == True) &
        (df_contacts['createdate_dt'].notna()) &
        (df_contacts['pql_date_dt'].notna()) &
        (df_contacts['pql_date_dt'] >= df_contacts['createdate_dt'])
    ]
    pql_count = len(pql_strict)
    
    # Stage 3: SQL (must have sql_date after pql_date, pql_date after createdate)
    sql_strict = pql_strict[
        (pql_strict['is_sql'] == True) &
        (pql_strict['sql_date_dt'].notna()) &
        (pql_strict['sql_date_dt'] >= pql_strict['pql_date_dt'])
    ]
    sql_count = len(sql_strict)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    stages = ['Total\nContacts', 'PQL', 'SQL']
    values = [total_contacts, pql_count, sql_count]
    percentages = [
        100,
        (pql_count / total_contacts * 100) if total_contacts > 0 else 0,
        (sql_count / total_contacts * 100) if total_contacts > 0 else 0
    ]
    
    # Create funnel bars
    colors = ['#3498db', '#f39c12', '#9b59b6']
    bars = ax.barh(stages, values, color=colors)
    
    # Add percentage labels
    for i, (bar, pct, val) in enumerate(zip(bars, percentages, values)):
        width = bar.get_width()
        ax.text(width/2, bar.get_y() + bar.get_height()/2.,
               f'{int(val)}\n({pct:.1f}%)',
               ha='center', va='center', fontweight='bold', fontsize=11, color='white')
    
    ax.set_xlabel('Count', fontweight='bold')
    ax.set_title('Conversion Funnel - Score 40+ (Created → PQL → SQL)', fontweight='bold', fontsize=14)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    return fig

def create_conversion_by_score_chart(df_contacts):
    """Create chart showing conversion rates by score ranges"""
    # Create score buckets
    bins = [40, 45, 50, 55, 60, 70, 80, 90, 100]
    labels = ['40-44', '45-49', '50-54', '55-59', '60-69', '70-79', '80-89', '90-99']
    
    df_contacts['score_bucket'] = pd.cut(df_contacts['score'], bins=bins, labels=labels, include_lowest=True)
    
    # Calculate conversion rates by score bucket
    conversion_by_score = []
    for bucket in labels:
        bucket_df = df_contacts[df_contacts['score_bucket'] == bucket]
        if len(bucket_df) > 0:
            total = len(bucket_df)
            sql_count = bucket_df['is_sql'].sum()
            pql_count = bucket_df['is_pql'].sum()
            sql_rate = (sql_count / total * 100) if total > 0 else 0
            pql_rate = (pql_count / total * 100) if total > 0 else 0
            
            conversion_by_score.append({
                'score_range': bucket,
                'total': total,
                'sql_count': sql_count,
                'pql_count': pql_count,
                'sql_rate': sql_rate,
                'pql_rate': pql_rate
            })
    
    conversion_df = pd.DataFrame(conversion_by_score)
    
    if len(conversion_df) == 0:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, 'No hay datos disponibles', ha='center', va='center', fontsize=14)
        ax.set_title('Tasas de Conversión por Rango de Score', fontweight='bold')
        return fig
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('Tasas de Conversión por Rango de Score', fontsize=16, fontweight='bold')
    
    x_pos = np.arange(len(conversion_df))
    width = 0.35
    
    # SQL Conversion Rates
    bars1 = ax1.bar(x_pos, conversion_df['sql_rate'], width, label='SQL', color='#3498db', alpha=0.8)
    ax1.set_xlabel('Rango de Score', fontweight='bold')
    ax1.set_ylabel('Tasa de Conversión (%)', fontweight='bold')
    ax1.set_title('Tasa de Conversión SQL por Score', fontweight='bold')
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(conversion_df['score_range'], rotation=45, ha='right')
    ax1.set_ylim(0, max(conversion_df['sql_rate'].max() * 1.2, 10))
    ax1.grid(axis='y', alpha=0.3)
    ax1.legend()
    
    # Add value labels on bars
    for i, (bar, rate, count) in enumerate(zip(bars1, conversion_df['sql_rate'], conversion_df['sql_count'])):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{rate:.1f}%\n({int(count)})',
                ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    # PQL Conversion Rates
    bars2 = ax2.bar(x_pos, conversion_df['pql_rate'], width, label='PQL', color='#9b59b6', alpha=0.8)
    ax2.set_xlabel('Rango de Score', fontweight='bold')
    ax2.set_ylabel('Tasa de Conversión (%)', fontweight='bold')
    ax2.set_title('Tasa de Conversión PQL por Score', fontweight='bold')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(conversion_df['score_range'], rotation=45, ha='right')
    ax2.set_ylim(0, max(conversion_df['pql_rate'].max() * 1.2, 10))
    ax2.grid(axis='y', alpha=0.3)
    ax2.legend()
    
    # Add value labels on bars
    for i, (bar, rate, count) in enumerate(zip(bars2, conversion_df['pql_rate'], conversion_df['pql_count'])):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{rate:.1f}%\n({int(count)})',
                ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    plt.tight_layout()
    return fig

def create_conversion_rate_comparison_chart(df_contacts):
    """Create combined chart showing SQL and PQL rates by score"""
    # Create score buckets
    bins = [40, 45, 50, 55, 60, 70, 80, 90, 100]
    labels = ['40-44', '45-49', '50-54', '55-59', '60-69', '70-79', '80-89', '90-99']
    
    df_contacts['score_bucket'] = pd.cut(df_contacts['score'], bins=bins, labels=labels, include_lowest=True)
    
    # Calculate conversion rates by score bucket
    conversion_by_score = []
    for bucket in labels:
        bucket_df = df_contacts[df_contacts['score_bucket'] == bucket]
        if len(bucket_df) > 0:
            total = len(bucket_df)
            sql_count = bucket_df['is_sql'].sum()
            pql_count = bucket_df['is_pql'].sum()
            sql_rate = (sql_count / total * 100) if total > 0 else 0
            pql_rate = (pql_count / total * 100) if total > 0 else 0
            
            conversion_by_score.append({
                'score_range': bucket,
                'total': total,
                'sql_rate': sql_rate,
                'pql_rate': pql_rate
            })
    
    conversion_df = pd.DataFrame(conversion_by_score)
    
    if len(conversion_df) == 0:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, 'No hay datos disponibles', ha='center', va='center', fontsize=14)
        ax.set_title('Comparación de Tasas de Conversión por Score', fontweight='bold')
        return fig
    
    fig, ax = plt.subplots(figsize=(14, 7))
    
    x_pos = np.arange(len(conversion_df))
    width = 0.35
    
    bars1 = ax.bar(x_pos - width/2, conversion_df['sql_rate'], width, label='SQL', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x_pos + width/2, conversion_df['pql_rate'], width, label='PQL', color='#9b59b6', alpha=0.8)
    
    ax.set_xlabel('Rango de Score', fontweight='bold', fontsize=12)
    ax.set_ylabel('Tasa de Conversión (%)', fontweight='bold', fontsize=12)
    ax.set_title('Comparación de Tasas de Conversión SQL vs PQL por Rango de Score', fontweight='bold', fontsize=14)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(conversion_df['score_range'], rotation=45, ha='right')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.1f}%',
                       ha='center', va='bottom', fontweight='bold', fontsize=9)
    
    plt.tight_layout()
    return fig

def generate_html_report(contacts_file, owners_file, output_file):
    """Generate comprehensive HTML report"""
    
    # Read data
    df_contacts = pd.read_csv(contacts_file)
    df_owners = pd.read_csv(owners_file)
    
    # Remove "No Owner" row if exists
    df_owners = df_owners[df_owners['owner_name'] != 'No Owner']
    
    # Extract period from filename
    import re
    period_match = re.search(r'(\d{4}_\d{2}_\d{2})_(\d{4}_\d{2}_\d{2})', contacts_file)
    if period_match:
        start_str = period_match.group(1)
        end_str = period_match.group(2)
        start_date = datetime.strptime(start_str, '%Y_%m_%d')
        end_date = datetime.strptime(end_str, '%Y_%m_%d')
        
        if start_date.month == end_date.month and start_date.day == 1:
            # Month-to-date
            month_name = start_date.strftime('%B').capitalize()
            period_title = f"{month_name} {start_date.day}-{end_date.day}, {start_date.year} (Month-to-Date)"
        else:
            # Custom range
            period_title = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
    else:
        period_title = "Análisis de Score 40+"
    
    # Generate all charts
    print("📊 Generando visualizaciones...")
    chart1 = create_owner_performance_chart(df_owners)
    chart2 = create_engagement_metrics_chart(df_contacts)
    chart3 = create_time_distribution_chart(df_contacts)
    chart4 = create_score_distribution_chart(df_contacts)
    chart5 = create_uncontacted_breakdown_chart(df_contacts)
    chart6 = create_conversion_funnel_chart(df_contacts)
    chart7 = create_conversion_by_score_chart(df_contacts)
    chart8 = create_conversion_rate_comparison_chart(df_contacts)
    
    # Convert to base64
    img1 = fig_to_base64(chart1)
    img2 = fig_to_base64(chart2)
    img3 = fig_to_base64(chart3)
    img4 = fig_to_base64(chart4)
    img5 = fig_to_base64(chart5)
    img6 = fig_to_base64(chart6)
    img7 = fig_to_base64(chart7)
    img8 = fig_to_base64(chart8)
    
    # Calculate summary metrics
    total_contacts = len(df_contacts)
    contacted = df_contacts['is_contacted'].sum()
    contact_rate = contacted / total_contacts * 100
    sql_count = df_contacts['is_sql'].sum()
    pql_count = df_contacts['is_pql'].sum()
    avg_score = df_contacts['score'].mean()
    
    contacted_df = df_contacts[df_contacts['is_contacted'] == True]
    avg_time = contacted_df['days_to_contact'].mean() if len(contacted_df) > 0 else 0
    
    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Análisis - Score 40+ | {period_title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 4px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            border-left: 5px solid #3498db;
            padding-left: 15px;
        }}
        .summary-box {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-card h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            opacity: 0.9;
        }}
        .metric-card .value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .metric-card.primary {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
        .metric-card.success {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .metric-card.warning {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }}
        .metric-card.info {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
        .chart-container {{
            margin: 30px 0;
            text-align: center;
            background: #fafafa;
            padding: 20px;
            border-radius: 8px;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        th {{
            background: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }}
        .badge {{
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-success {{ background: #2ecc71; color: white; }}
        .badge-warning {{ background: #f39c12; color: white; }}
        .badge-danger {{ background: #e74c3c; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Reporte de Análisis - Score 40+</h1>
        <p style="font-size: 18px; color: #7f8c8d; margin-bottom: 30px;">
            <strong>Período:</strong> {period_title} | <strong>Generado:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </p>
        
        <div class="summary-box">
            <div class="metric-card primary">
                <h3>Total Contactos</h3>
                <div class="value">{total_contacts:,}</div>
                <p>Score 40+</p>
            </div>
            <div class="metric-card success">
                <h3>Tasa de Contacto</h3>
                <div class="value">{contact_rate:.1f}%</div>
                <p>{contacted} de {total_contacts}</p>
            </div>
            <div class="metric-card info">
                <h3>Score Promedio</h3>
                <div class="value">{avg_score:.1f}</div>
                <p>Rango: 40-100</p>
            </div>
            <div class="metric-card warning">
                <h3>Conversiones SQL</h3>
                <div class="value">{sql_count}</div>
                <p>{sql_count/total_contacts*100:.1f}% del total</p>
            </div>
            <div class="metric-card warning">
                <h3>Conversiones PQL</h3>
                <div class="value">{pql_count}</div>
                <p>{pql_count/total_contacts*100:.1f}% del total</p>
            </div>
            <div class="metric-card info">
                <h3>Tiempo Promedio</h3>
                <div class="value">{avg_time:.1f}</div>
                <p>días a contacto</p>
            </div>
        </div>
        
        <h2>📈 Desempeño por Owner</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img1}" alt="Owner Performance">
        </div>
        
        <h2>🎯 Métricas de Engagement</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img2}" alt="Engagement Metrics">
        </div>
        
        <h2>⏱️ Distribución de Tiempo a Contacto</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img3}" alt="Time Distribution">
        </div>
        
        <h2>📊 Distribución de Scores</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img4}" alt="Score Distribution">
        </div>
        
        <h2>🚨 Contactos No Contactados por Owner</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img5}" alt="Uncontacted Breakdown">
        </div>
        
        <h2>🔄 Conversion Funnel (Strict Temporal Order)</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img6}" alt="Conversion Funnel">
            <p style="margin-top: 10px; color: #7f8c8d; font-size: 12px;">
                <strong>Note:</strong> Funnel shows only contacts following strict temporal order: 
                Created → PQL → SQL. Each stage requires the previous stage to have occurred first.
                Temporal validation: <code>createdate &lt; pql_date &lt; sql_date</code>
            </p>
        </div>
        
        <h2>📊 Tasas de Conversión por Rango de Score</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img7}" alt="Conversion by Score">
        </div>
        
        <h2>📈 Comparación SQL vs PQL por Score</h2>
        <div class="chart-container">
            <img src="data:image/png;base64,{img8}" alt="Conversion Rate Comparison">
        </div>
        
        <h2>📋 Tabla de Desempeño por Owner</h2>
        <table>
            <thead>
                <tr>
                    <th>Owner</th>
                    <th>Total</th>
                    <th>Contactados</th>
                    <th>% Contacto</th>
                    <th>Promedio Días</th>
                    <th>SQL</th>
                    <th>% SQL</th>
                    <th>PQL</th>
                    <th>% PQL</th>
                </tr>
            </thead>
            <tbody>
"""
    
    # Add owner performance table
    df_sorted = df_owners.sort_values('total_contacts', ascending=False)
    for _, row in df_sorted.iterrows():
        contact_badge = 'badge-success' if row['contact_rate'] >= 20 else 'badge-warning' if row['contact_rate'] > 0 else 'badge-danger'
        avg_time = f"{row['avg_time_to_contact']:.1f} días" if pd.notna(row['avg_time_to_contact']) else "N/A"
        html_content += f"""
                <tr>
                    <td><strong>{row['owner_name']}</strong></td>
                    <td>{int(row['total_contacts'])}</td>
                    <td>{int(row['contacted'])}</td>
                    <td><span class="badge {contact_badge}">{row['contact_rate']:.1f}%</span></td>
                    <td>{avg_time}</td>
                    <td>{int(row['sql_count'])}</td>
                    <td>{row['sql_rate']:.1f}%</td>
                    <td>{int(row['pql_count'])}</td>
                    <td>{row['pql_rate']:.1f}%</td>
                </tr>
"""
    
    html_content += """
            </tbody>
        </table>
        
        <div class="footer">
            <p>Reporte generado automáticamente desde HubSpot API</p>
            <p>Contactos con lead_source = "Usuario Invitado" han sido excluidos del análisis</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Reporte generado: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Generate visualization report from CSV data')
    parser.add_argument('--contacts-file', 
                       default='tools/outputs/high_score_contacts_2025_12_01_2025_12_20.csv',
                       help='Path to contacts CSV file')
    parser.add_argument('--owners-file',
                       default='tools/outputs/high_score_owner_performance_2025_12_01_2025_12_20.csv',
                       help='Path to owners performance CSV file')
    parser.add_argument('--output',
                       default='tools/outputs/high_score_visualization_report.html',
                       help='Output HTML file path')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.contacts_file):
        print(f"❌ Error: No se encontró el archivo {args.contacts_file}")
        sys.exit(1)
    
    if not os.path.exists(args.owners_file):
        print(f"❌ Error: No se encontró el archivo {args.owners_file}")
        sys.exit(1)
    
    generate_html_report(args.contacts_file, args.owners_file, args.output)

if __name__ == '__main__':
    main()

