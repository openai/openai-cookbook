#!/usr/bin/env python3
"""
Campaign Role Funnel Depth Analysis
====================================

Analyzes the correlation between campaign roles and how deep users progress
through the funnel. Compares conversion rates by role across different campaigns.

Funnel Steps:
1. Validó email
2. Finalizar Wizard
3. Eventos clave de todos los usuarios en Trial

Usage:
    python campaign_role_funnel_analysis.py --input data.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, List, Tuple
import sys
import os

# Set Argentina locale formatting
plt.rcParams['axes.formatter.use_locale'] = True

def parse_funnel_data(data_string: str) -> pd.DataFrame:
    """
    Parse the provided CSV-like data string into a structured DataFrame.
    
    Args:
        data_string: Raw data string with campaign, role, and funnel metrics
        
    Returns:
        DataFrame with parsed and structured data
    """
    lines = [line.strip() for line in data_string.strip().split('\n') if line.strip()]
    
    # Parse header
    header = lines[0].split(',')
    
    # Parse data rows
    rows = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 8:
            rows.append({
                'utm_campaign': parts[0],
                'role': parts[1],
                'validated_email': int(parts[2]) if parts[2].isdigit() else 0,
                'finalized_wizard': int(parts[3]) if parts[3].isdigit() else 0,
                'trial_key_events': int(parts[4]) if parts[4].isdigit() else 0,
                'validated_email_date': int(parts[5]) if parts[5].isdigit() else 0,
                'finalized_wizard_date': int(parts[6]) if parts[6].isdigit() else 0,
                'trial_key_events_date': int(parts[7]) if parts[7].isdigit() else 0,
            })
    
    df = pd.DataFrame(rows)
    
    # Filter out special aggregation rows for main analysis
    df_clean = df[~df['role'].isin(['$overall', '$remaining_values', 'undefined'])]
    
    return df, df_clean

def calculate_funnel_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate funnel conversion rates and depth metrics.
    
    Args:
        df: DataFrame with funnel data
        
    Returns:
        DataFrame with calculated metrics
    """
    metrics = []
    
    for _, row in df.iterrows():
        validated = row['validated_email']
        finalized = row['finalized_wizard']
        trial_events = row['trial_key_events']
        
        # Calculate conversion rates
        rate_step1_to_step2 = (finalized / validated * 100) if validated > 0 else 0
        rate_step2_to_step3 = (trial_events / finalized * 100) if finalized > 0 else 0
        rate_step1_to_step3 = (trial_events / validated * 100) if validated > 0 else 0
        
        # Calculate funnel depth score (weighted average)
        # Step 1 = 1 point, Step 2 = 2 points, Step 3 = 3 points
        depth_score = (
            (validated - finalized) * 1 +  # Only step 1
            (finalized - trial_events) * 2 +  # Reached step 2
            trial_events * 3  # Reached step 3
        ) / validated if validated > 0 else 0
        
        metrics.append({
            'utm_campaign': row['utm_campaign'],
            'role': row['role'],
            'validated_email': validated,
            'finalized_wizard': finalized,
            'trial_key_events': trial_events,
            'conversion_rate_step1_to_step2': rate_step1_to_step2,
            'conversion_rate_step2_to_step3': rate_step2_to_step3,
            'conversion_rate_step1_to_step3': rate_step1_to_step3,
            'funnel_depth_score': depth_score,
            'dropout_step1': validated - finalized,
            'dropout_step2': finalized - trial_events,
        })
    
    return pd.DataFrame(metrics)

def analyze_by_role(df: pd.DataFrame) -> Dict:
    """
    Analyze funnel performance by role.
    
    Args:
        df: DataFrame with funnel metrics
        
    Returns:
        Dictionary with role-based analysis
    """
    role_analysis = {}
    
    for role in df['role'].unique():
        role_data = df[df['role'] == role]
        
        total_validated = role_data['validated_email'].sum()
        total_finalized = role_data['finalized_wizard'].sum()
        total_trial = role_data['trial_key_events'].sum()
        
        role_analysis[role] = {
            'total_validated': int(total_validated),
            'total_finalized': int(total_finalized),
            'total_trial': int(total_trial),
            'avg_conversion_step1_to_step2': role_data['conversion_rate_step1_to_step2'].mean(),
            'avg_conversion_step2_to_step3': role_data['conversion_rate_step2_to_step3'].mean(),
            'avg_conversion_step1_to_step3': role_data['conversion_rate_step1_to_step3'].mean(),
            'avg_funnel_depth_score': role_data['funnel_depth_score'].mean(),
            'campaigns_count': len(role_data),
        }
    
    return role_analysis

def analyze_by_campaign(df: pd.DataFrame) -> Dict:
    """
    Analyze funnel performance by campaign.
    
    Args:
        df: DataFrame with funnel metrics
        
    Returns:
        Dictionary with campaign-based analysis
    """
    campaign_analysis = {}
    
    for campaign in df['utm_campaign'].unique():
        campaign_data = df[df['utm_campaign'] == campaign]
        
        total_validated = campaign_data['validated_email'].sum()
        total_finalized = campaign_data['finalized_wizard'].sum()
        total_trial = campaign_data['trial_key_events'].sum()
        
        campaign_analysis[campaign] = {
            'total_validated': int(total_validated),
            'total_finalized': int(total_finalized),
            'total_trial': int(total_trial),
            'avg_conversion_step1_to_step2': campaign_data['conversion_rate_step1_to_step2'].mean(),
            'avg_conversion_step2_to_step3': campaign_data['conversion_rate_step2_to_step3'].mean(),
            'avg_conversion_step1_to_step3': campaign_data['conversion_rate_step1_to_step3'].mean(),
            'avg_funnel_depth_score': campaign_data['funnel_depth_score'].mean(),
            'roles_count': len(campaign_data),
        }
    
    return campaign_analysis

def create_funnel_visualization(df: pd.DataFrame, output_dir: Path):
    """
    Create funnel depth visualization by role.
    
    Args:
        df: DataFrame with funnel metrics
        output_dir: Directory to save visualizations
    """
    # Aggregate by role
    role_agg = df.groupby('role').agg({
        'validated_email': 'sum',
        'finalized_wizard': 'sum',
        'trial_key_events': 'sum',
    }).reset_index()
    
    # Calculate percentages
    role_agg['pct_step1'] = 100
    role_agg['pct_step2'] = (role_agg['finalized_wizard'] / role_agg['validated_email'] * 100).fillna(0)
    role_agg['pct_step3'] = (role_agg['trial_key_events'] / role_agg['validated_email'] * 100).fillna(0)
    
    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Funnel Depth Analysis by Campaign Role', fontsize=16, fontweight='bold')
    
    # 1. Funnel Steps by Role (Bar Chart)
    ax1 = axes[0, 0]
    x = np.arange(len(role_agg))
    width = 0.25
    
    ax1.bar(x - width, role_agg['pct_step1'], width, label='Step 1: Validó Email', alpha=0.8)
    ax1.bar(x, role_agg['pct_step2'], width, label='Step 2: Finalizar Wizard', alpha=0.8)
    ax1.bar(x + width, role_agg['pct_step3'], width, label='Step 3: Trial Key Events', alpha=0.8)
    
    ax1.set_xlabel('Role', fontweight='bold')
    ax1.set_ylabel('Conversion Rate (%)', fontweight='bold')
    ax1.set_title('Funnel Conversion Rates by Role', fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(role_agg['role'], rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # 2. Funnel Depth Score by Role
    ax2 = axes[0, 1]
    depth_by_role = df.groupby('role')['funnel_depth_score'].mean().sort_values(ascending=False)
    ax2.barh(range(len(depth_by_role)), depth_by_role.values, color='steelblue', alpha=0.7)
    ax2.set_yticks(range(len(depth_by_role)))
    ax2.set_yticklabels(depth_by_role.index)
    ax2.set_xlabel('Average Funnel Depth Score', fontweight='bold')
    ax2.set_title('Funnel Depth Score by Role', fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)
    
    # 3. Campaign Performance Heatmap
    ax3 = axes[1, 0]
    campaign_role_pivot = df.pivot_table(
        values='funnel_depth_score',
        index='utm_campaign',
        columns='role',
        aggfunc='mean'
    )
    sns.heatmap(campaign_role_pivot, annot=True, fmt='.2f', cmap='YlOrRd', ax=ax3, cbar_kws={'label': 'Funnel Depth Score'})
    ax3.set_title('Funnel Depth Score: Campaign × Role', fontweight='bold')
    ax3.set_xlabel('Role', fontweight='bold')
    ax3.set_ylabel('Campaign', fontweight='bold')
    plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
    plt.setp(ax3.get_yticklabels(), rotation=0)
    
    # 4. Conversion Rate Comparison
    ax4 = axes[1, 1]
    conversion_metrics = df.groupby('role').agg({
        'conversion_rate_step1_to_step2': 'mean',
        'conversion_rate_step2_to_step3': 'mean',
        'conversion_rate_step1_to_step3': 'mean',
    })
    
    x = np.arange(len(conversion_metrics))
    width = 0.25
    ax4.bar(x - width, conversion_metrics['conversion_rate_step1_to_step2'], width, 
            label='Step 1→2', alpha=0.8)
    ax4.bar(x, conversion_metrics['conversion_rate_step2_to_step3'], width,
            label='Step 2→3', alpha=0.8)
    ax4.bar(x + width, conversion_metrics['conversion_rate_step1_to_step3'], width,
            label='Step 1→3', alpha=0.8)
    
    ax4.set_xlabel('Role', fontweight='bold')
    ax4.set_ylabel('Conversion Rate (%)', fontweight='bold')
    ax4.set_title('Step-by-Step Conversion Rates by Role', fontweight='bold')
    ax4.set_xticks(x)
    ax4.set_xticklabels(conversion_metrics.index, rotation=45, ha='right')
    ax4.legend()
    ax4.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    output_file = output_dir / 'funnel_depth_by_role.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"📊 Visualization saved: {output_file}")
    plt.close()

def create_campaign_analysis_visualization(df: pd.DataFrame, output_dir: Path):
    """
    Create campaign-level funnel analysis visualization.
    
    Args:
        df: DataFrame with funnel metrics
        output_dir: Directory to save visualizations
    """
    # Aggregate by campaign
    campaign_agg = df.groupby('utm_campaign').agg({
        'validated_email': 'sum',
        'finalized_wizard': 'sum',
        'trial_key_events': 'sum',
        'funnel_depth_score': 'mean',
    }).sort_values('funnel_depth_score', ascending=False)
    
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    fig.suptitle('Campaign Funnel Performance Analysis', fontsize=16, fontweight='bold')
    
    # 1. Funnel Depth Score by Campaign
    ax1 = axes[0]
    ax1.barh(range(len(campaign_agg)), campaign_agg['funnel_depth_score'].values, 
             color='coral', alpha=0.7)
    ax1.set_yticks(range(len(campaign_agg)))
    ax1.set_yticklabels(campaign_agg.index)
    ax1.set_xlabel('Average Funnel Depth Score', fontweight='bold')
    ax1.set_title('Campaign Funnel Depth Ranking', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # 2. Volume vs Depth Scatter
    ax2 = axes[1]
    scatter = ax2.scatter(campaign_agg['validated_email'], 
                         campaign_agg['funnel_depth_score'],
                         s=200, alpha=0.6, c=campaign_agg['funnel_depth_score'],
                         cmap='RdYlGn')
    
    for campaign in campaign_agg.index:
        ax2.annotate(campaign, 
                    (campaign_agg.loc[campaign, 'validated_email'],
                     campaign_agg.loc[campaign, 'funnel_depth_score']),
                    fontsize=8, alpha=0.7)
    
    ax2.set_xlabel('Total Validated Email (Volume)', fontweight='bold')
    ax2.set_ylabel('Funnel Depth Score', fontweight='bold')
    ax2.set_title('Campaign Volume vs Funnel Depth', fontweight='bold')
    ax2.grid(alpha=0.3)
    plt.colorbar(scatter, ax=ax2, label='Funnel Depth Score')
    
    plt.tight_layout()
    
    output_file = output_dir / 'campaign_funnel_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"📊 Visualization saved: {output_file}")
    plt.close()

def generate_insights(df: pd.DataFrame, role_analysis: Dict, campaign_analysis: Dict) -> List[str]:
    """
    Generate strategic insights from the analysis.
    
    Args:
        df: DataFrame with funnel metrics
        role_analysis: Role-based analysis dictionary
        campaign_analysis: Campaign-based analysis dictionary
        
    Returns:
        List of insight strings
    """
    insights = []
    
    # Role insights
    role_depth_scores = {role: data['avg_funnel_depth_score'] 
                        for role, data in role_analysis.items()}
    best_role = max(role_depth_scores, key=role_depth_scores.get)
    worst_role = min(role_depth_scores, key=role_depth_scores.get)
    
    insights.append(f"🎯 **Best Performing Role**: {best_role} with depth score {role_depth_scores[best_role]:.2f}")
    insights.append(f"⚠️ **Worst Performing Role**: {worst_role} with depth score {role_depth_scores[worst_role]:.2f}")
    
    # Campaign insights
    campaign_depth_scores = {camp: data['avg_funnel_depth_score'] 
                            for camp, data in campaign_analysis.items()}
    best_campaign = max(campaign_depth_scores, key=campaign_depth_scores.get)
    worst_campaign = min(campaign_depth_scores, key=campaign_depth_scores.get)
    
    insights.append(f"🚀 **Best Performing Campaign**: {best_campaign} with depth score {campaign_depth_scores[best_campaign]:.2f}")
    insights.append(f"📉 **Worst Performing Campaign**: {worst_campaign} with depth score {campaign_depth_scores[worst_campaign]:.2f}")
    
    # Conversion rate insights
    avg_conversion_step1_to_step2 = df['conversion_rate_step1_to_step2'].mean()
    avg_conversion_step2_to_step3 = df['conversion_rate_step2_to_step3'].mean()
    
    insights.append(f"📊 **Average Step 1→2 Conversion**: {avg_conversion_step1_to_step2:.2f}%")
    insights.append(f"📊 **Average Step 2→3 Conversion**: {avg_conversion_step2_to_step3:.2f}%")
    
    # Identify biggest drop-off
    if avg_conversion_step1_to_step2 < avg_conversion_step2_to_step3:
        insights.append("⚠️ **Biggest Drop-off**: Step 1→2 (Email validation to Wizard completion)")
    else:
        insights.append("⚠️ **Biggest Drop-off**: Step 2→3 (Wizard completion to Trial activation)")
    
    return insights

def main():
    """Main analysis function"""
    # Data provided by user
    data_string = """utm_campaign,¿Cuál es tu rol? wizard,(1) Validó email,(2) Finalizar Wizard,(3) Eventos clave de todos los usuarios en Trial,(1) Validó email(2025-10-01),(2) Finalizar Wizard(2025-10-01),(3) Eventos clave de todos los usuarios en Trial(2025-10-01)
$overall,$overall,783,245,40,280,155,28
App Mobile Colppy,$overall,30,13,0,38,19,1
App Mobile Colppy,ICP Contador / Asesor,2,1,0,1,1,0
App Mobile Colppy,ICP Pyme,21,9,0,11,9,1
App Mobile Colppy,Liquidador de sueldos,3,1,0,3,1,0
App Mobile Colppy,Otro,4,2,0,20,7,0
Contadores_lead_gen_meta - Copia,$overall,1,1,1,0,0,0
Contadores_lead_gen_meta - Copia,undefined,1,1,1,0,0,0
GRAL_lead_gen,$overall,52,37,3,13,8,3
GRAL_lead_gen,ICP Contador / Asesor,4,3,1,0,0,0
GRAL_lead_gen,ICP Pyme,22,18,1,8,3,2
GRAL_lead_gen,Liquidador de sueldos,1,1,0,0,0,0
GRAL_lead_gen,Otro,24,14,0,5,5,1
GRAL_lead_gen,undefined,1,1,1,0,0,0
Google My Business,$overall,2,2,0,1,1,0
Google My Business,ICP Pyme,2,2,0,1,1,0
Integraciones_lead_gen,$overall,18,10,1,5,2,0
Integraciones_lead_gen,ICP Contador / Asesor,4,2,0,3,2,0
Integraciones_lead_gen,ICP Pyme,6,3,1,0,0,0
Integraciones_lead_gen,Liquidador de sueldos,2,1,0,0,0,0
Integraciones_lead_gen,Otro,6,4,0,2,0,0
PMax_PyMEs_lead_gen,$overall,587,111,15,90,21,5
PMax_PyMEs_lead_gen,$remaining_values,14,2,0,1,0,0
PMax_PyMEs_lead_gen,ICP Contador / Asesor,38,7,1,14,2,0
PMax_PyMEs_lead_gen,ICP Pyme,107,29,11,24,13,2
PMax_PyMEs_lead_gen,Liquidador de sueldos,18,4,0,7,1,0
PMax_PyMEs_lead_gen,Otro,410,69,3,44,5,3
PyMEs_lead_gen,$overall,10,5,0,24,18,3
PyMEs_lead_gen,ICP Pyme,3,2,0,15,12,3
PyMEs_lead_gen,Liquidador de sueldos,2,1,0,1,1,0
PyMEs_lead_gen,Otro,5,2,0,8,5,0
Recordatorios,$overall,1,0,0,0,0,0
Recordatorios,ICP Pyme,1,0,0,0,0,0
Search_Branding_Leads_ARG,$overall,19,15,3,18,16,3
Search_Branding_Leads_ARG,ICP Pyme,14,10,1,12,11,2
Search_Branding_Leads_ARG,Otro,5,5,2,3,3,1
test,$overall,1,1,0,0,0,0
test,ICP Contador / Asesor,1,1,0,0,0,0
undefined,$overall,62,50,17,76,57,12
undefined,$remaining_values,1,0,0,1,1,1
undefined,ICP Contador / Asesor,15,13,3,4,3,1
undefined,ICP Pyme,34,30,11,54,45,9
undefined,Liquidador de sueldos,1,1,1,1,1,0
undefined,Otro,11,6,2,16,7,1"""
    
    print("🔍 Campaign Role Funnel Depth Analysis")
    print("=" * 70)
    print(f"Analysis Date: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}")
    print("=" * 70)
    
    # Parse data
    print("\n📊 Parsing data...")
    df_raw, df = parse_funnel_data(data_string)
    print(f"✅ Processed {len(df)} records (excluding aggregation rows)")
    print(f"📈 Total characters processed: {len(data_string)}")
    
    # Calculate metrics
    print("\n📊 Calculating funnel metrics...")
    df_metrics = calculate_funnel_metrics(df)
    
    # Analyze by role
    print("\n👥 Analyzing by role...")
    role_analysis = analyze_by_role(df_metrics)
    
    # Analyze by campaign
    print("\n📢 Analyzing by campaign...")
    campaign_analysis = analyze_by_campaign(df_metrics)
    
    # Create output directory
    output_dir = Path(__file__).parent.parent.parent / 'outputs' / 'funnel_analysis'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate visualizations
    print("\n📊 Creating visualizations...")
    create_funnel_visualization(df_metrics, output_dir)
    create_campaign_analysis_visualization(df_metrics, output_dir)
    
    # Generate insights
    print("\n💡 Generating insights...")
    insights = generate_insights(df_metrics, role_analysis, campaign_analysis)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results = {
        'analysis_metadata': {
            'analysis_date': datetime.now().isoformat(),
            'total_records': len(df),
            'total_characters': len(data_string),
            'campaigns_analyzed': len(campaign_analysis),
            'roles_analyzed': len(role_analysis),
        },
        'role_analysis': role_analysis,
        'campaign_analysis': campaign_analysis,
        'insights': insights,
        'raw_metrics': df_metrics.to_dict('records'),
    }
    
    output_file = output_dir / f'campaign_role_funnel_analysis_{timestamp}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    # Export to CSV
    csv_file = output_dir / f'campaign_role_funnel_metrics_{timestamp}.csv'
    df_metrics.to_csv(csv_file, index=False, encoding='utf-8')
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"\n📈 Total Records Analyzed: {len(df)}")
    print(f"📢 Campaigns: {len(campaign_analysis)}")
    print(f"👥 Roles: {len(role_analysis)}")
    
    print("\n💡 KEY INSIGHTS:")
    for insight in insights:
        print(f"  {insight}")
    
    print(f"\n💾 Results saved:")
    print(f"  📄 JSON: {output_file}")
    print(f"  📊 CSV: {csv_file}")
    print(f"  📈 Visualizations: {output_dir}/")
    
    return results

if __name__ == "__main__":
    main()

