#!/usr/bin/env python3
"""
🎯 COLPPY NPS ANALYSIS BY USER TYPE
Analyzes NPS data segmented by User Type (Accountant vs Non-Accountant) at the contact level

IMPORTANT DISTINCTION:
- This analysis is at the USER/CONTACT level (user type classification)
- ICP analysis (at company/account level) will be a separate future analysis
- This script classifies individual contacts/users, not companies/accounts

This script:
1. Loads NPS survey responses from Intercom
2. Enriches data with HubSpot contact information (user type classification)
3. Analyzes NPS metrics by User Type (Accountant vs Non-Accountant/SMB)
4. Provides comparative insights and visualizations

Future ICP Analysis (Company Level):
- Will analyze NPS at the company/account level
- Will check which company each contact belongs to in HubSpot
- Will use company-level ICP classification (not contact-level)

Usage:
    python analyze_nps_by_user_type.py --files nps_file1.csv nps_file2.csv [--output-dir outputs/]
    python analyze_nps_by_user_type.py --file nps_file.csv [--output-dir outputs/]
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import argparse
import os
import json
from pathlib import Path
import warnings
import time
import sys
import requests
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

warnings.filterwarnings('ignore')

# Load environment variables
load_dotenv()

# Configure matplotlib for better visualizations
plt.style.use('default')
sns.set_palette("husl")

def is_accountant_role(rol_wizard: Optional[str]) -> bool:
    """Check if rol_wizard indicates accountant role"""
    if not rol_wizard or str(rol_wizard).strip() == '':
        return False
    rol_lower = str(rol_wizard).lower().strip()
    return 'conta' in rol_lower

def classify_user_type(es_contador: Optional[str], rol_wizard: Optional[str]) -> str:
    """
    Classify contact/user as Accountant or Non-Accountant (SMB) based on HubSpot contact properties.
    
    NOTE: This is USER TYPE classification at the contact level, not ICP (which is at company level).
    
    Args:
        es_contador: Boolean field indicating if contact is an accountant
        rol_wizard: Role field that may contain accountant indicators
    
    Returns:
        'Accountant' or 'Non-Accountant'
    """
    # Primary check: es_contador field (Boolean)
    if es_contador:
        es_contador_str = str(es_contador).lower().strip()
        if es_contador_str in ['true', '1', 'yes']:
            return 'Accountant'
    
    # Secondary check: rol_wizard field
    if is_accountant_role(rol_wizard):
        return 'Accountant'
    
    # Default: Non-Accountant (SMB)
    return 'Non-Accountant'

def fetch_hubspot_user_type_info(emails: List[str], batch_size: int = 10) -> Dict[str, Dict[str, Any]]:
    """
    Fetch user type information from HubSpot for a list of emails.
    
    NOTE: This fetches USER TYPE at the contact level, not ICP (which is at company level).
    
    Args:
        emails: List of email addresses to query
        batch_size: Number of emails to process before showing progress
    
    Returns:
        Dictionary mapping email -> {es_contador, rol_wizard, user_type_classification, contact_id, found}
    """
    import requests
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment
    api_key = (
        os.getenv("HUBSPOT_API_KEY") or 
        os.getenv("HUBSPOT_ACCESS_TOKEN") or 
        os.getenv("HUBSPOT_TOKEN") or
        os.getenv("COLPPY_CRM_AUTOMATIONS") or
        os.getenv("ColppyCRMAutomations")
    )
    
    if not api_key:
        print("⚠️  Warning: HubSpot API key not found in environment variables.")
        print("   Please set one of: HUBSPOT_API_KEY, HUBSPOT_ACCESS_TOKEN, HUBSPOT_TOKEN")
        print("   Or use: COLPPY_CRM_AUTOMATIONS, ColppyCRMAutomations")
        print("   Continuing with 'Not Found in HubSpot' for all contacts...")
        
        # Return all as not found
        return {
            email: {
                'es_contador': None,
                'rol_wizard': None,
                'user_type_classification': 'Not Found in HubSpot',
                'contact_id': None,
                'found': False
            }
            for email in emails
        }
    
    base_url = "https://api.hubapi.com"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    icp_data = {}
    total_emails = len(emails)
    
    print(f"🔍 Querying HubSpot for {total_emails:,} unique emails...")
    print(f"   Properties to fetch: es_contador, rol_wizard (user type at contact level)")
    print(f"   NOTE: This is user type analysis, not ICP (ICP is at company level)")
    
    found_count = 0
    not_found_count = 0
    
    for idx, email in enumerate(emails, 1):
        if pd.isna(email) or not email or str(email).strip() == '':
            icp_data[email] = {
                'es_contador': None,
                'rol_wizard': None,
                'user_type_classification': 'Unknown',
                'contact_id': None,
                'found': False
            }
            continue
        
        try:
            # Search for contact by email using HubSpot Search API
            search_url = f"{base_url}/crm/v3/objects/contacts/search"
            
            payload = {
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": str(email).strip().lower()
                    }]
                }],
                "properties": ["es_contador", "rol_wizard", "email", "firstname", "lastname"],
                "limit": 1
            }
            
            response = requests.post(search_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                if results and len(results) > 0:
                    contact = results[0]
                    props = contact.get('properties', {})
                    es_contador = props.get('es_contador')
                    rol_wizard = props.get('rol_wizard')
                    
                    user_type_classification = classify_user_type(es_contador, rol_wizard)
                    
                    icp_data[email] = {
                        'es_contador': es_contador,
                        'rol_wizard': rol_wizard,
                        'user_type_classification': user_type_classification,
                        'contact_id': contact.get('id'),
                        'found': True
                    }
                    found_count += 1
                else:
                    icp_data[email] = {
                        'es_contador': None,
                        'rol_wizard': None,
                        'user_type_classification': 'Not Found in HubSpot',
                        'contact_id': None,
                        'found': False
                    }
                    not_found_count += 1
            elif response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = int(response.headers.get('Retry-After', 1))
                print(f"   ⚠️  Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                # Retry this email
                idx -= 1
                continue
            else:
                # Error response
                icp_data[email] = {
                    'es_contador': None,
                    'rol_wizard': None,
                    'user_type_classification': 'Error',
                    'contact_id': None,
                    'found': False
                }
                not_found_count += 1
                if response.status_code != 404:  # 404 is expected for not found
                    print(f"   ⚠️  Error querying {email}: HTTP {response.status_code}")
            
            # Progress update
            if idx % batch_size == 0 or idx == total_emails:
                print(f"   Progress: {idx:,}/{total_emails:,} ({idx/total_emails*100:.1f}%) - "
                      f"Found: {found_count:,}, Not Found: {not_found_count:,}")
            
            # Rate limiting - small delay between requests
            time.sleep(0.1)
            
        except Exception as e:
            print(f"   ⚠️  Error querying {email}: {str(e)}")
            icp_data[email] = {
                'es_contador': None,
                'rol_wizard': None,
                'user_type_classification': 'Error',
                'contact_id': None,
                'found': False
            }
            not_found_count += 1
    
    print(f"\n✅ HubSpot query complete:")
    print(f"   • Found in HubSpot: {found_count:,} ({found_count/total_emails*100:.1f}%)")
    print(f"   • Not found: {not_found_count:,} ({not_found_count/total_emails*100:.1f}%)")
    
    return icp_data

class NPSByUserTypeAnalyzer:
    def __init__(self, file_paths, output_dir="outputs/nps_analysis_by_user_type"):
        """Initialize NPS by User Type Analyzer (contact level, not ICP/company level)."""
        # Handle both single file (backward compatibility) and multiple files
        if isinstance(file_paths, str):
            self.file_paths = [file_paths]
        else:
            self.file_paths = file_paths
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # NPS column mapping (Spanish to English for easier processing)
        self.column_mapping = {
            '¿Qué probabilidades hay de que nos recomiende a familiares y amigos?': 'nps_score',
            '¡Qué bueno saberlo! ¿Qué es lo que más te gusta de nuestro producto o servicio?': 'promoter_feedback',
            'Lamentamos oír eso. ¿Qué podríamos haber hecho de manera diferente para mejorar tu experiencia?': 'detractor_feedback',
            '¿Qué es lo más importante que podríamos hacer para mejorar tu experiencia en el futuro?': 'improvement_feedback'
        }
        
        self.df = None
        self.df_enriched = None
        self.analysis_results = {}
    
    def load_and_clean_data(self):
        """Load and clean the NPS data from one or multiple files."""
        print(f"🔄 Loading NPS data from {len(self.file_paths)} file(s)...")
        
        try:
            dataframes = []
            total_rows_before = 0
            
            # Load each file
            for idx, file_path in enumerate(self.file_paths):
                if not os.path.exists(file_path):
                    print(f"⚠️  Warning: File not found: {file_path}, skipping...")
                    continue
                
                print(f"   📂 Loading file {idx + 1}/{len(self.file_paths)}: {os.path.basename(file_path)}")
                df = pd.read_csv(file_path, encoding='utf-8')
                total_rows_before += len(df)
                
                # Add source file column to track origin
                df['source_file'] = os.path.basename(file_path)
                
                dataframes.append(df)
            
            if not dataframes:
                print("❌ Error: No valid files found to load")
                return False
            
            # Combine all dataframes
            print(f"🔗 Combining {len(dataframes)} file(s)...")
            self.df = pd.concat(dataframes, ignore_index=True)
            
            print(f"   📊 Total rows before processing: {len(self.df):,}")
            
            # Rename columns for easier processing
            self.df = self.df.rename(columns=self.column_mapping)
            
            # Convert dates
            date_columns = ['received_at', 'completed_at']
            for col in date_columns:
                if col in self.df.columns:
                    self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
            
            # Clean NPS scores (convert to numeric, handle non-numeric values)
            if 'nps_score' in self.df.columns:
                self.df['nps_score'] = pd.to_numeric(self.df['nps_score'], errors='coerce')
            
            # Remove rows with no NPS score (incomplete responses)
            initial_count = len(self.df)
            self.df = self.df.dropna(subset=['nps_score'])
            final_count = len(self.df)
            
            print(f"✅ Loaded {final_count:,} complete NPS responses from {len(dataframes)} file(s)")
            print(f"   📉 Removed {initial_count - final_count:,} incomplete responses")
            
            # Remove true duplicates (same email, same date, same score)
            self.df['received_date'] = self.df['received_at'].dt.date
            duplicate_mask = self.df.duplicated(
                subset=['email', 'received_date', 'nps_score'],
                keep='first'
            )
            
            duplicate_count = duplicate_mask.sum()
            if duplicate_count > 0:
                print(f"⚠️  Removing {duplicate_count} true duplicates (same email, same date, same score)...")
                self.df = self.df[~duplicate_mask].copy()
                print(f"📊 After removing duplicates: {len(self.df):,} responses")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading data: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def enrich_with_hubspot_user_type(self):
        """Enrich NPS data with HubSpot user type information (contact level)."""
        print(f"\n🔗 Enriching NPS data with HubSpot user type information...")
        print(f"   NOTE: This is user type at contact level, not ICP (which is at company level)")
        
        # Get unique emails
        unique_emails = self.df['email'].dropna().unique().tolist()
        print(f"   📧 Found {len(unique_emails):,} unique email addresses")
        
        # Fetch user type information from HubSpot
        user_type_data = fetch_hubspot_user_type_info(unique_emails)
        
        # Create enrichment dataframe
        enrichment_df = pd.DataFrame([
            {
                'email': email,
                'es_contador': data['es_contador'],
                'rol_wizard': data['rol_wizard'],
                'user_type_classification': data['user_type_classification'],
                'contact_id': data['contact_id'],
                'found_in_hubspot': data['found']
            }
            for email, data in user_type_data.items()
        ])
        
        # Merge with NPS data
        self.df_enriched = self.df.merge(
            enrichment_df,
            on='email',
            how='left'
        )
        
        # Fill missing classifications
        self.df_enriched['user_type_classification'] = self.df_enriched['user_type_classification'].fillna('Not Found in HubSpot')
        
        # Summary
        user_type_breakdown = self.df_enriched['user_type_classification'].value_counts()
        print(f"\n📊 User Type Classification Summary (Contact Level):")
        for user_type, count in user_type_breakdown.items():
            pct = (count / len(self.df_enriched)) * 100
            print(f"   • {user_type}: {count:,} ({pct:.1f}%)")
        
        return True
    
    def calculate_nps_by_user_type(self):
        """Calculate NPS metrics segmented by User Type (contact level)."""
        if self.df_enriched is None:
            print("❌ Error: Data not enriched with HubSpot user type information")
            return False
        
        print(f"\n📊 Calculating NPS metrics by User Type (Contact Level)...")
        
        def categorize_nps_score(score):
            """Categorize NPS score into Promoter, Passive, or Detractor."""
            if pd.isna(score):
                return 'Unknown'
            elif score >= 9:
                return 'Promoter'
            elif score >= 7:
                return 'Passive'
            else:
                return 'Detractor'
        
        # Add category
        self.df_enriched['nps_category'] = self.df_enriched['nps_score'].apply(categorize_nps_score)
        
        # Calculate NPS by User Type
        user_type_results = {}
        
        for user_type in self.df_enriched['user_type_classification'].unique():
            df_user_type = self.df_enriched[self.df_enriched['user_type_classification'] == user_type]
            
            if len(df_user_type) == 0:
                continue
            
            total_responses = len(df_user_type)
            promoters = len(df_user_type[df_user_type['nps_category'] == 'Promoter'])
            passives = len(df_user_type[df_user_type['nps_category'] == 'Passive'])
            detractors = len(df_user_type[df_user_type['nps_category'] == 'Detractor'])
            
            promoter_pct = (promoters / total_responses) * 100 if total_responses > 0 else 0
            detractor_pct = (detractors / total_responses) * 100 if total_responses > 0 else 0
            nps_score = promoter_pct - detractor_pct
            avg_score = df_user_type['nps_score'].mean()
            
            user_type_results[user_type] = {
                'nps_score': round(nps_score, 1),
                'total_responses': total_responses,
                'promoters': promoters,
                'passives': passives,
                'detractors': detractors,
                'promoter_percentage': round(promoter_pct, 1),
                'passive_percentage': round((passives / total_responses) * 100, 1) if total_responses > 0 else 0,
                'detractor_percentage': round(detractor_pct, 1),
                'average_score': round(avg_score, 2)
            }
            
            print(f"\n   📈 {user_type}:")
            print(f"      NPS Score: {nps_score:.1f}")
            print(f"      Total Responses: {total_responses:,}")
            print(f"      Promoters: {promoters} ({promoter_pct:.1f}%)")
            print(f"      Passives: {passives} ({passives/total_responses*100:.1f}%)")
            print(f"      Detractors: {detractors} ({detractor_pct:.1f}%)")
            print(f"      Average Score: {avg_score:.2f}")
        
        self.analysis_results['nps_by_user_type'] = user_type_results
        
        return True
    
    def create_user_type_comparison_visualizations(self):
        """Create visualizations comparing NPS by User Type (contact level)."""
        if self.df_enriched is None:
            return None
        
        print(f"\n📊 Creating User Type comparison visualizations (Contact Level)...")
        
        # Filter to main user types (Accountant vs Non-Accountant)
        main_user_types = ['Accountant', 'Non-Accountant']
        df_main = self.df_enriched[
            self.df_enriched['user_type_classification'].isin(main_user_types)
        ].copy()
        
        if len(df_main) == 0:
            print("⚠️  No data for main user types (Accountant/Non-Accountant), skipping visualizations")
            return None
        
        # Create figure with subplots
        fig = plt.figure(figsize=(20, 16))
        
        # 1. NPS Score Comparison by User Type
        ax1 = plt.subplot(3, 3, 1)
        user_type_nps = df_main.groupby('user_type_classification').apply(
            lambda x: ((len(x[x['nps_score'] >= 9]) / len(x)) * 100) - 
                     ((len(x[x['nps_score'] <= 6]) / len(x)) * 100)
        )
        colors = ['#388e3c' if x > 0 else '#d32f2f' for x in user_type_nps.values]
        bars = ax1.bar(user_type_nps.index, user_type_nps.values, color=colors, alpha=0.7)
        ax1.axhline(0, color='black', linestyle='-', linewidth=1)
        ax1.set_title('NPS Score por User Type (Contact Level)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('NPS Score')
        ax1.grid(axis='y', alpha=0.3)
        for bar, val in zip(bars, user_type_nps.values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:.1f}', ha='center', va='bottom' if val > 0 else 'top', fontweight='bold')
        
        # 2. Response Distribution by User Type
        ax2 = plt.subplot(3, 3, 2)
        user_type_counts = df_main['user_type_classification'].value_counts()
        colors_pie = ['#4caf50', '#ff9800']
        wedges, texts, autotexts = ax2.pie(user_type_counts.values, labels=user_type_counts.index, 
                                          autopct='%1.1f%%', colors=colors_pie, startangle=90)
        ax2.set_title('Distribución de Respuestas por User Type', fontsize=14, fontweight='bold')
        
        # 3. NPS Category Distribution by User Type
        ax3 = plt.subplot(3, 3, 3)
        category_user_type = pd.crosstab(df_main['user_type_classification'], df_main['nps_category'], normalize='index') * 100
        category_user_type.plot(kind='bar', ax=ax3, color=['#388e3c', '#ff9800', '#d32f2f'], alpha=0.7)
        ax3.set_title('Distribución de Categorías NPS por User Type', fontsize=14, fontweight='bold')
        ax3.set_xlabel('User Type')
        ax3.set_ylabel('Porcentaje (%)')
        ax3.legend(title='Categoría', bbox_to_anchor=(1.05, 1), loc='upper left')
        ax3.tick_params(axis='x', rotation=45)
        ax3.grid(axis='y', alpha=0.3)
        
        # 4. Average Score by User Type
        ax4 = plt.subplot(3, 3, 4)
        avg_scores = df_main.groupby('user_type_classification')['nps_score'].mean()
        bars = ax4.bar(avg_scores.index, avg_scores.values, color=['#4caf50', '#ff9800'], alpha=0.7)
        ax4.set_title('Puntuación Promedio por User Type', fontsize=14, fontweight='bold')
        ax4.set_ylabel('Puntuación Promedio')
        ax4.set_ylim([0, 10])
        ax4.grid(axis='y', alpha=0.3)
        for bar, val in zip(bars, avg_scores.values):
            height = bar.get_height()
            ax4.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:.2f}', ha='center', va='bottom', fontweight='bold')
        
        # 5. Score Distribution Histogram by User Type
        ax5 = plt.subplot(3, 3, 5)
        for user_type in main_user_types:
            df_user_type = df_main[df_main['user_type_classification'] == user_type]
            if len(df_user_type) > 0:
                ax5.hist(df_user_type['nps_score'], bins=11, alpha=0.5, label=user_type, edgecolor='black')
        ax5.set_title('Distribución de Puntuaciones por User Type', fontsize=14, fontweight='bold')
        ax5.set_xlabel('Puntuación NPS')
        ax5.set_ylabel('Frecuencia')
        ax5.legend()
        ax5.grid(axis='y', alpha=0.3)
        
        # 6. Temporal Trend by User Type
        ax6 = plt.subplot(3, 3, 6)
        df_main['month_year'] = df_main['received_at'].dt.to_period('M')
        monthly_user_type = df_main.groupby(['month_year', 'user_type_classification']).apply(
            lambda x: ((len(x[x['nps_score'] >= 9]) / len(x)) * 100) - 
                     ((len(x[x['nps_score'] <= 6]) / len(x)) * 100)
        ).unstack()
        
        if len(monthly_user_type) > 0:
            monthly_user_type.plot(kind='line', ax=ax6, marker='o', linewidth=2, markersize=6)
            ax6.set_title('Evolución NPS Mensual por User Type', fontsize=14, fontweight='bold')
            ax6.set_xlabel('Mes')
            ax6.set_ylabel('NPS Score')
            ax6.legend(title='User Type')
            ax6.grid(True, alpha=0.3)
            ax6.tick_params(axis='x', rotation=45)
        
        # 7. Promoter vs Detractor Comparison
        ax7 = plt.subplot(3, 3, 7)
        promoter_detractor = pd.DataFrame({
            'Promoters': df_main.groupby('user_type_classification').apply(
                lambda x: len(x[x['nps_score'] >= 9]) / len(x) * 100
            ),
            'Detractors': df_main.groupby('user_type_classification').apply(
                lambda x: len(x[x['nps_score'] <= 6]) / len(x) * 100
            )
        })
        promoter_detractor.plot(kind='bar', ax=ax7, color=['#388e3c', '#d32f2f'], alpha=0.7)
        ax7.set_title('Promotores vs Detractores por User Type', fontsize=14, fontweight='bold')
        ax7.set_ylabel('Porcentaje (%)')
        ax7.legend()
        ax7.tick_params(axis='x', rotation=45)
        ax7.grid(axis='y', alpha=0.3)
        
        # 8. Response Volume Over Time by User Type
        ax8 = plt.subplot(3, 3, 8)
        df_main['date'] = df_main['received_at'].dt.date
        daily_user_type = df_main.groupby(['date', 'user_type_classification']).size().unstack(fill_value=0)
        if len(daily_user_type) > 0:
            daily_user_type.plot(kind='line', ax=ax8, alpha=0.7, linewidth=2)
            ax8.set_title('Volumen de Respuestas Diarias por User Type', fontsize=14, fontweight='bold')
            ax8.set_xlabel('Fecha')
            ax8.set_ylabel('Respuestas')
            ax8.legend(title='User Type')
            ax8.grid(True, alpha=0.3)
            plt.setp(ax8.xaxis.get_majorticklabels(), rotation=45)
        
        # 9. Summary Statistics
        ax9 = plt.subplot(3, 3, 9)
        ax9.axis('off')
        
        summary_text = "RESUMEN NPS POR USER TYPE\n(Contact Level)\n\n"
        if 'nps_by_user_type' in self.analysis_results:
            for user_type, metrics in self.analysis_results['nps_by_user_type'].items():
                if user_type in main_user_types:
                    summary_text += f"{user_type}:\n"
                    summary_text += f"  NPS: {metrics['nps_score']}\n"
                    summary_text += f"  Respuestas: {metrics['total_responses']:,}\n"
                    summary_text += f"  Promedio: {metrics['average_score']}\n\n"
        
        ax9.text(0.1, 0.9, summary_text, transform=ax9.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
        
        plt.tight_layout()
        
        # Save the plot
        plot_path = self.output_dir / f"nps_by_user_type_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"📊 User Type comparison visualizations saved to: {plot_path}")
        
        return plot_path
    
    def export_results(self):
        """Export all analysis results to files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Export enriched data
        if self.df_enriched is not None:
            data_path = self.output_dir / f"nps_enriched_with_user_type_{timestamp}.csv"
            self.df_enriched.to_csv(data_path, index=False, encoding='utf-8')
            print(f"📄 Enriched data exported to: {data_path}")
        
        # Export analysis results
        analysis_path = self.output_dir / f"nps_by_user_type_analysis_{timestamp}.json"
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(self.analysis_results, f, indent=2, ensure_ascii=False, default=str)
        print(f"📄 Analysis results exported to: {analysis_path}")
        
        return data_path if self.df_enriched is not None else None, analysis_path
    
    def run_complete_analysis(self):
        """Run the complete NPS by User Type analysis pipeline (contact level)."""
        print("🚀 Starting NPS analysis by User Type (Contact Level)...")
        print("=" * 60)
        print("NOTE: This is user type analysis at contact level, not ICP (which is at company level)")
        print("=" * 60)
        
        # Load and clean data
        if not self.load_and_clean_data():
            return False
        
        # Enrich with HubSpot user type information
        if not self.enrich_with_hubspot_user_type():
            return False
        
        # Calculate NPS by User Type
        if not self.calculate_nps_by_user_type():
            return False
        
        # Create visualizations
        self.create_user_type_comparison_visualizations()
        
        # Export results
        print("\n💾 Exporting results...")
        self.export_results()
        
        # Print summary
        print("\n" + "=" * 60)
        print("🎯 NPS BY USER TYPE SUMMARY (Contact Level)")
        print("=" * 60)
        
        if 'nps_by_user_type' in self.analysis_results:
            for user_type, metrics in self.analysis_results['nps_by_user_type'].items():
                print(f"\n{user_type}:")
                print(f"  NPS Score: {metrics['nps_score']}")
                print(f"  Total Responses: {metrics['total_responses']:,}")
                print(f"  Promoters: {metrics['promoters']} ({metrics['promoter_percentage']}%)")
                print(f"  Detractors: {metrics['detractors']} ({metrics['detractor_percentage']}%)")
        
        print("\n✅ Analysis complete!")
        print("\n📝 NOTE: Future ICP analysis will be at company/account level")
        return True

def main():
    """Main function to run NPS by User Type analysis from command line."""
    parser = argparse.ArgumentParser(
        description='Analyze NPS data segmented by User Type at contact level (Accountant vs Non-Accountant). NOTE: This is user type analysis, not ICP (ICP is at company level).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Multiple files
  python analyze_nps_by_user_type.py --files file1.csv file2.csv
  
  # Single file (backward compatible)
  python analyze_nps_by_user_type.py --file file1.csv
  
  # With custom output directory
  python analyze_nps_by_user_type.py --files file1.csv file2.csv --output-dir outputs/custom/
  
NOTE: This analyzes user type at contact level. Future ICP analysis will be at company/account level.
        """
    )
    
    # Support both --file (single, backward compatible) and --files (multiple)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', '-f', help='Path to a single NPS CSV file (backward compatible)')
    group.add_argument('--files', nargs='+', help='Paths to one or more NPS CSV files')
    
    parser.add_argument('--output-dir', '-o', default='outputs/nps_analysis_by_user_type', 
                       help='Output directory for results (default: outputs/nps_analysis_by_user_type)')
    
    args = parser.parse_args()
    
    # Determine which files to process
    if args.file:
        file_paths = [args.file]
    else:
        file_paths = args.files
    
    # Validate files exist
    missing_files = [f for f in file_paths if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Error: The following file(s) not found:")
        for f in missing_files:
            print(f"   • {f}")
        return 1
    
    # Run analysis
    analyzer = NPSByUserTypeAnalyzer(file_paths, args.output_dir)
    success = analyzer.run_complete_analysis()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())

