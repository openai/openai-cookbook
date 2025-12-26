#!/usr/bin/env python3
"""
HubSpot Conversion Rate Analysis
===============================

This script analyzes the conversion rates from contacts/leads to deals for any specified date range,
providing comprehensive insights for Product-Led Growth optimization.

Author: Data Analytics Team - Colppy
Date: January 2025

Usage:
    python hubspot_conversion_analysis.py --start-date 2025-05-01 --end-date 2025-06-01
    python hubspot_conversion_analysis.py --month 2025-05  # For a specific month
    python hubspot_conversion_analysis.py --year 2025 --month 5  # Alternative month format
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
import json
from dotenv import load_dotenv
import warnings
import argparse
warnings.filterwarnings('ignore')

# Load environment variables
load_dotenv()

def parse_arguments():
    """Parse command line arguments for date range"""
    parser = argparse.ArgumentParser(description='HubSpot Conversion Rate Analysis')
    
    # Date range options
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    date_group.add_argument('--month', help='Month in YYYY-MM format')
    date_group.add_argument('--year', type=int, help='Year (use with --month-num)')
    
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD, required with --start-date)')
    parser.add_argument('--month-num', type=int, help='Month number 1-12 (use with --year)', choices=range(1, 13))
    
    args = parser.parse_args()
    
    # Validate and convert arguments
    if args.start_date:
        if not args.end_date:
            parser.error("--end-date is required when using --start-date")
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').strftime('%Y-%m-%d')
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            parser.error("Invalid date format. Use YYYY-MM-DD")
    elif args.month:
        try:
            date_obj = datetime.strptime(args.month, '%Y-%m')
            start_date = date_obj.strftime('%Y-%m-%d')
            # Get last day of month
            if date_obj.month == 12:
                next_month = date_obj.replace(year=date_obj.year + 1, month=1)
            else:
                next_month = date_obj.replace(month=date_obj.month + 1)
            end_date = next_month.strftime('%Y-%m-%d')
        except ValueError:
            parser.error("Invalid month format. Use YYYY-MM")
    elif args.year and args.month_num:
        try:
            date_obj = datetime(args.year, args.month_num, 1)
            start_date = date_obj.strftime('%Y-%m-%d')
            # Get last day of month
            if date_obj.month == 12:
                next_month = date_obj.replace(year=date_obj.year + 1, month=1)
            else:
                next_month = date_obj.replace(month=date_obj.month + 1)
            end_date = next_month.strftime('%Y-%m-%d')
        except ValueError:
            parser.error("Invalid year/month combination")
    else:
        parser.error("Must specify either --start-date/--end-date, --month, or --year/--month-num")
    
    return start_date, end_date

def get_period_label(start_date, end_date):
    """Generate a human-readable period label"""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Check if it's a full month
    if start_dt.day == 1 and end_dt.day == 1 and end_dt.month != start_dt.month:
        return start_dt.strftime('%B %Y')
    else:
        return f"{start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"

def get_file_suffix(start_date, end_date):
    """Generate a file suffix for the date range"""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Check if it's a full month
    if start_dt.day == 1 and end_dt.day == 1 and end_dt.month != start_dt.month:
        return start_dt.strftime('%Y_%m')
    else:
        return f"{start_dt.strftime('%Y_%m_%d')}_{end_dt.strftime('%Y_%m_%d')}"

# Parse command line arguments
START_DATE, END_DATE = parse_arguments()
PERIOD_LABEL = get_period_label(START_DATE, END_DATE)
FILE_SUFFIX = get_file_suffix(START_DATE, END_DATE)

# Configuration
API_KEY = os.getenv("HUBSPOT_API_KEY")

# Output directories
OUTPUT_BASE = "tools/outputs/csv_data/hubspot"
LEADS_DIR = os.path.join(OUTPUT_BASE, "leads")
DEALS_DIR = os.path.join(OUTPUT_BASE, "deals")
CONTACTS_DIR = os.path.join(OUTPUT_BASE, "contacts")
VISUALIZATIONS_DIR = "tools/outputs/visualizations/hubspot"

# Create directories if they don't exist
for directory in [LEADS_DIR, DEALS_DIR, CONTACTS_DIR, VISUALIZATIONS_DIR]:
    os.makedirs(directory, exist_ok=True)

# HubSpot API Headers
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
} if API_KEY else {}

class HubSpotConversionAnalyzer:
    """Class to analyze HubSpot conversion rates from contacts/leads to deals"""
    
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        self.contacts_df = None
        self.leads_df = None
        self.deals_df = None
        self.conversion_metrics = {}
        
    def load_existing_data(self):
        """Load existing CSV data from previous exports"""
        print("Loading existing HubSpot data...")
        
        # Load leads data
        leads_file = os.path.join(LEADS_DIR, f"hubspot_leads_{FILE_SUFFIX}_complete.csv")
        if os.path.exists(leads_file):
            print(f"Loading leads data from {leads_file}")
            self.leads_df = pd.read_csv(leads_file)
            print(f"Loaded {len(self.leads_df)} leads")
        else:
            print("No leads data found, will fetch from API")
            
        # Load deals data
        deals_file = os.path.join(DEALS_DIR, f"hubspot_deals_{FILE_SUFFIX}_with_company.csv")
        if os.path.exists(deals_file):
            print(f"Loading deals data from {deals_file}")
            self.deals_df = pd.read_csv(deals_file)
            print(f"Loaded {len(self.deals_df)} deals")
        else:
            # Try alternative location
            alt_deals_file = f"scripts/hubspot/hubspot_deals_{FILE_SUFFIX}_with_company.csv"
            if os.path.exists(alt_deals_file):
                print(f"Loading deals data from {alt_deals_file}")
                self.deals_df = pd.read_csv(alt_deals_file)
                print(f"Loaded {len(self.deals_df)} deals")
            else:
                print("No deals data found, will fetch from API")
        
        # Check if we have contacts data
        contacts_files = [
            os.path.join(CONTACTS_DIR, f"hubspot_contacts_{FILE_SUFFIX}.csv"),
            f"hubspot_contacts_{FILE_SUFFIX}.csv",
            f"scripts/hubspot/hubspot_contacts_{FILE_SUFFIX}.csv"
        ]
        
        for contacts_file in contacts_files:
            if os.path.exists(contacts_file):
                print(f"Loading contacts data from {contacts_file}")
                self.contacts_df = pd.read_csv(contacts_file)
                print(f"Loaded {len(self.contacts_df)} contacts")
                break
        
        if self.contacts_df is None:
            print("No contacts data found, will use leads data as proxy")
            
    def fetch_contacts_from_api(self):
        """Fetch contacts data from HubSpot API"""
        if not API_KEY:
            print("No API key found, skipping contacts fetch")
            return
            
        print("Fetching contacts from HubSpot API...")
        url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
        all_contacts = []
        after = None
        
        while True:
            payload = {
                "filterGroups": [
                    {
                        "filters": [
                            {"propertyName": "createdate", "operator": "GTE", "value": f"{self.start_date}T00:00:00Z"},
                            {"propertyName": "createdate", "operator": "LT", "value": f"{self.end_date}T00:00:00Z"}
                        ]
                    }
                ],
                "properties": [
                    "email", "firstname", "lastname", "createdate", "hubspot_owner_id",
                    "lead_source", "lifecyclestage", "hs_lead_status", "company",
                    "hs_date_entered_lead", "hs_date_entered_customer", "total_revenue"
                ],
                "limit": 100
            }
            
            if after:
                payload["after"] = after
                
            try:
                response = requests.post(url, headers=HEADERS, json=payload)
                response.raise_for_status()
                data = response.json()
                
                contacts = data.get("results", [])
                all_contacts.extend(contacts)
                print(f"Fetched {len(contacts)} contacts (total: {len(all_contacts)})")
                
                after = data.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                    
            except Exception as e:
                print(f"Error fetching contacts: {e}")
                break
        
        # Process contacts data
        if all_contacts:
            contacts_data = []
            for contact in all_contacts:
                props = contact["properties"]
                contacts_data.append({
                    "id": contact["id"],
                    "email": props.get("email"),
                    "firstname": props.get("firstname"),
                    "lastname": props.get("lastname"),
                    "createdate": props.get("createdate"),
                    "hubspot_owner_id": props.get("hubspot_owner_id"),
                    "lead_source": props.get("lead_source"),
                    "lifecyclestage": props.get("lifecyclestage"),
                    "hs_lead_status": props.get("hs_lead_status"),
                    "company": props.get("company"),
                    "date_entered_lead": props.get("hs_date_entered_lead"),
                    "date_entered_customer": props.get("hs_date_entered_customer"),
                    "total_revenue": props.get("total_revenue")
                })
            
            self.contacts_df = pd.DataFrame(contacts_data)
            
            # Save to CSV
            output_file = os.path.join(CONTACTS_DIR, f"hubspot_contacts_{FILE_SUFFIX}.csv")
            self.contacts_df.to_csv(output_file, index=False)
            print(f"Saved {len(self.contacts_df)} contacts to {output_file}")

    def prepare_data(self):
        """Clean and prepare data for analysis"""
        print("Preparing data for analysis...")
        
        # Convert date columns
        if self.leads_df is not None:
            date_columns = ["created_date", "lead_date", "mql_date", "sql_date", "opportunity_date", "customer_date"]
            for col in date_columns:
                if col in self.leads_df.columns:
                    self.leads_df[col] = pd.to_datetime(self.leads_df[col], errors='coerce')
        
        if self.deals_df is not None:
            if "Close Date" in self.deals_df.columns:
                self.deals_df["Close Date"] = pd.to_datetime(self.deals_df["Close Date"], errors='coerce')
                
        if self.contacts_df is not None:
            date_columns = ["createdate", "date_entered_lead", "date_entered_customer"]
            for col in date_columns:
                if col in self.contacts_df.columns:
                    self.contacts_df[col] = pd.to_datetime(self.contacts_df[col], errors='coerce')
        
        print("Data preparation completed")

    def calculate_conversion_rates(self):
        """Calculate comprehensive conversion rates"""
        print("Calculating conversion rates...")
        
        # Initialize metrics
        metrics = {
            "total_contacts": 0,
            "total_leads": 0,
            "total_deals": 0,
            "total_closed_won_deals": 0,
            "total_closed_lost_deals": 0,
            "contact_to_lead_conversion": 0.0,
            "lead_to_deal_conversion": 0.0,
            "contact_to_deal_conversion": 0.0,
            "lead_to_closed_won_conversion": 0.0,
            "contact_to_closed_won_conversion": 0.0,
            "deal_win_rate": 0.0
        }
        
        # Count totals
        if self.contacts_df is not None:
            metrics["total_contacts"] = len(self.contacts_df)
            
        if self.leads_df is not None:
            metrics["total_leads"] = len(self.leads_df)
            
        if self.deals_df is not None:
            metrics["total_deals"] = len(self.deals_df)
            
            # Count closed won and lost deals
            if "Stage" in self.deals_df.columns:
                closed_won_deals = self.deals_df[self.deals_df["Stage"] == "closedwon"]
                closed_lost_deals = self.deals_df[self.deals_df["Stage"] == "closedlost"]
                
                metrics["total_closed_won_deals"] = len(closed_won_deals)
                metrics["total_closed_lost_deals"] = len(closed_lost_deals)
        
        # Calculate conversion rates
        # If we don't have contacts data, use leads as the starting point
        if metrics["total_contacts"] == 0 and metrics["total_leads"] > 0:
            print("Using leads as the starting point for conversion analysis")
            starting_point = metrics["total_leads"]
            conversion_base = "leads"
        else:
            starting_point = metrics["total_contacts"]
            conversion_base = "contacts"
            
        # Contact/Lead to Deal conversion
        if starting_point > 0:
            if conversion_base == "contacts":
                metrics["contact_to_deal_conversion"] = (metrics["total_deals"] / starting_point) * 100
                metrics["contact_to_closed_won_conversion"] = (metrics["total_closed_won_deals"] / starting_point) * 100
                
                # Contact to Lead conversion (if we have both)
                if metrics["total_leads"] > 0:
                    metrics["contact_to_lead_conversion"] = (metrics["total_leads"] / starting_point) * 100
            else:
                metrics["lead_to_deal_conversion"] = (metrics["total_deals"] / starting_point) * 100
                metrics["lead_to_closed_won_conversion"] = (metrics["total_closed_won_deals"] / starting_point) * 100
        
        # Lead to Deal conversion (if we have leads data)
        if metrics["total_leads"] > 0:
            metrics["lead_to_deal_conversion"] = (metrics["total_deals"] / metrics["total_leads"]) * 100
            metrics["lead_to_closed_won_conversion"] = (metrics["total_closed_won_deals"] / metrics["total_leads"]) * 100
        
        # Deal win rate
        total_closed_deals = metrics["total_closed_won_deals"] + metrics["total_closed_lost_deals"]
        if total_closed_deals > 0:
            metrics["deal_win_rate"] = (metrics["total_closed_won_deals"] / total_closed_deals) * 100
        
        self.conversion_metrics = metrics
        
        # Print summary
        print("\n" + "="*50)
        print(f"CONVERSION RATE ANALYSIS - {PERIOD_LABEL.upper()}")
        print("="*50)
        print(f"Total Contacts: {metrics['total_contacts']:,}")
        print(f"Total Leads: {metrics['total_leads']:,}")
        print(f"Total Deals: {metrics['total_deals']:,}")
        print(f"Closed Won Deals: {metrics['total_closed_won_deals']:,}")
        print(f"Closed Lost Deals: {metrics['total_closed_lost_deals']:,}")
        print("\nCONVERSION RATES:")
        print(f"Contact to Lead: {metrics['contact_to_lead_conversion']:.2f}%")
        print(f"Lead to Deal: {metrics['lead_to_deal_conversion']:.2f}%")
        print(f"Contact to Deal: {metrics['contact_to_deal_conversion']:.2f}%")
        print(f"Lead to Closed Won: {metrics['lead_to_closed_won_conversion']:.2f}%")
        print(f"Contact to Closed Won: {metrics['contact_to_closed_won_conversion']:.2f}%")
        print(f"Deal Win Rate: {metrics['deal_win_rate']:.2f}%")
        print("="*50)
        
        return metrics

    def analyze_conversion_by_source(self):
        """Analyze conversion rates by lead source"""
        if self.leads_df is None or "Lead Source" not in self.leads_df.columns:
            print("No lead source data available for analysis")
            return None
            
        print("Analyzing conversion rates by lead source...")
        
        # Group by lead source
        source_analysis = []
        
        for source in self.leads_df["Lead Source"].unique():
            if pd.isna(source):
                continue
                
            source_leads = self.leads_df[self.leads_df["Lead Source"] == source]
            lead_count = len(source_leads)
            
                        # Count deals for this source
            if self.deals_df is not None and "Deal Name" in self.deals_df.columns:
                # This is a simplified matching - in reality you'd need to match by contact ID or email
                # For now, we'll estimate based on proportional allocation
                deal_ratio = lead_count / len(self.leads_df) if len(self.leads_df) > 0 else 0
                estimated_deals = int(len(self.deals_df) * deal_ratio)
                estimated_closed_won = int(self.conversion_metrics["total_closed_won_deals"] * deal_ratio)
            else:
                estimated_deals = 0
                estimated_closed_won = 0
            
            conversion_rate = (estimated_deals / lead_count * 100) if lead_count > 0 else 0.0
            win_rate = (estimated_closed_won / lead_count * 100) if lead_count > 0 else 0.0
            
            source_analysis.append({
                "Lead Source": source,
                "Leads": lead_count,
                "Estimated Deals": estimated_deals,
                "Estimated Closed Won": estimated_closed_won,
                "Lead to Deal %": conversion_rate,
                "Lead to Closed Won %": win_rate
            })
        
        source_df = pd.DataFrame(source_analysis)
        source_df = source_df.sort_values("Lead to Closed Won %", ascending=False)
        
        return source_df

    def analyze_conversion_by_owner(self):
        """Analyze conversion rates by owner"""
        if self.leads_df is None or "Owner Name" not in self.leads_df.columns:
            print("No owner data available for analysis")
            return None
            
        print("Analyzing conversion rates by owner...")
        
        owner_analysis = []
        
        for owner in self.leads_df["Owner Name"].unique():
            if pd.isna(owner) or owner == "":
                continue
                
            owner_leads = self.leads_df[self.leads_df["Owner Name"] == owner]
            lead_count = len(owner_leads)
            
            # Count deals for this owner
            if self.deals_df is not None and "Owner Name" in self.deals_df.columns:
                owner_deals = self.deals_df[self.deals_df["Owner Name"] == owner]
                deal_count = len(owner_deals)
                closed_won_count = len(owner_deals[owner_deals["Stage"] == "closedwon"]) if "Stage" in owner_deals.columns else 0
            else:
                deal_count = 0
                closed_won_count = 0
            
            conversion_rate = (deal_count / lead_count * 100) if lead_count > 0 else 0
            win_rate = (closed_won_count / lead_count * 100) if lead_count > 0 else 0
            
            owner_analysis.append({
                "Owner": owner,
                "Leads": lead_count,
                "Deals": deal_count,
                "Closed Won": closed_won_count,
                "Lead to Deal %": conversion_rate,
                "Lead to Closed Won %": win_rate
            })
        
        owner_df = pd.DataFrame(owner_analysis)
        owner_df = owner_df.sort_values("Lead to Closed Won %", ascending=False)
        
        return owner_df

    def create_visualizations(self):
        """Create comprehensive visualizations"""
        print("Creating visualizations...")
        
        # Set up the plotting style
        plt.style.use('default')
        sns.set_palette("husl")
        
        # 1. Funnel Visualization
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Conversion Funnel
        stages = []
        counts = []
        
        if self.conversion_metrics["total_contacts"] > 0:
            stages.extend(["Contacts", "Leads", "Deals", "Closed Won"])
            counts.extend([
                self.conversion_metrics["total_contacts"],
                self.conversion_metrics["total_leads"],
                self.conversion_metrics["total_deals"],
                self.conversion_metrics["total_closed_won_deals"]
            ])
        else:
            stages.extend(["Leads", "Deals", "Closed Won"])
            counts.extend([
                self.conversion_metrics["total_leads"],
                self.conversion_metrics["total_deals"],
                self.conversion_metrics["total_closed_won_deals"]
            ])
        
        # Create funnel chart
        colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c'][:len(stages)]
        bars = ax1.barh(stages, counts, color=colors)
        ax1.set_xlabel('Count')
        ax1.set_title(f'Sales Funnel - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        
        # Add count labels on bars
        for i, (bar, count) in enumerate(zip(bars, counts)):
            ax1.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height()/2, 
                    f'{count:,}', va='center', fontweight='bold')
        
        # 2. Conversion Rates Bar Chart
        rates = [
            self.conversion_metrics.get("contact_to_lead_conversion", 0),
            self.conversion_metrics.get("lead_to_deal_conversion", 0),
            self.conversion_metrics.get("contact_to_deal_conversion", 0),
            self.conversion_metrics.get("deal_win_rate", 0)
        ]
        
        rate_labels = ["Contact→Lead", "Lead→Deal", "Contact→Deal", "Deal Win Rate"]
        
        bars2 = ax2.bar(rate_labels, rates, color=['#9b59b6', '#34495e', '#16a085', '#e67e22'])
        ax2.set_ylabel('Conversion Rate (%)')
        ax2.set_title(f'Conversion Rates - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        ax2.set_ylim(0, max(rates) * 1.1 if rates else 100)
        
        # Add percentage labels on bars
        for bar, rate in zip(bars2, rates):
            if rate > 0:
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(rates) * 0.01,
                        f'{rate:.1f}%', ha='center', va='bottom', fontweight='bold')
        
        plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
        
        # 3. Deal Stage Distribution
        if self.deals_df is not None and "Stage" in self.deals_df.columns:
            stage_counts = self.deals_df["Stage"].value_counts()
            
            # Create pie chart
            ax3.pie(stage_counts.values, labels=stage_counts.index, autopct='%1.1f%%', startangle=90)
            ax3.set_title(f'Deal Stage Distribution - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        else:
            ax3.text(0.5, 0.5, 'No deal stage data available', ha='center', va='center', transform=ax3.transAxes)
            ax3.set_title(f'Deal Stage Distribution - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        
        # 4. Timeline Analysis
        if self.deals_df is not None and "Close Date" in self.deals_df.columns:
            # Convert close date and filter to date range
            close_dates = pd.to_datetime(self.deals_df["Close Date"], errors='coerce')
            period_deals = close_dates[(close_dates >= START_DATE) & (close_dates < END_DATE)]
            
            if len(period_deals) > 0:
                # Group by day
                daily_deals = period_deals.groupby(period_deals.dt.date).size()
                
                ax4.plot(daily_deals.index, daily_deals.values, marker='o', linewidth=2, markersize=6)
                ax4.set_xlabel('Date')
                ax4.set_ylabel('Deals Closed')
                ax4.set_title(f'Daily Deal Closures - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
                ax4.tick_params(axis='x', rotation=45)
                ax4.grid(True, alpha=0.3)
            else:
                ax4.text(0.5, 0.5, 'No deal closure timeline data available', ha='center', va='center', transform=ax4.transAxes)
                ax4.set_title(f'Daily Deal Closures - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        else:
            ax4.text(0.5, 0.5, 'No deal timeline data available', ha='center', va='center', transform=ax4.transAxes)
            ax4.set_title(f'Daily Deal Closures - {PERIOD_LABEL}', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # Save the main dashboard
        dashboard_file = os.path.join(VISUALIZATIONS_DIR, f"hubspot_conversion_dashboard_{FILE_SUFFIX}.png")
        plt.savefig(dashboard_file, dpi=300, bbox_inches='tight')
        print(f"Saved conversion dashboard to {dashboard_file}")
        plt.close()
        
        # Create additional source analysis chart if data available
        source_df = self.analyze_conversion_by_source()
        if source_df is not None and len(source_df) > 0:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
            
            # Top sources by lead count
            top_sources = source_df.head(10)
            ax1.barh(top_sources["Lead Source"], top_sources["Leads"])
            ax1.set_xlabel('Number of Leads')
            ax1.set_title('Top Lead Sources by Volume', fontweight='bold')
            
            # Top sources by conversion rate
            top_conversion = source_df[source_df["Lead to Closed Won %"] > 0].head(10)
            if len(top_conversion) > 0:
                ax2.barh(top_conversion["Lead Source"], top_conversion["Lead to Closed Won %"])
                ax2.set_xlabel('Conversion Rate (%)')
                ax2.set_title('Top Lead Sources by Conversion Rate', fontweight='bold')
            
            plt.tight_layout()
            source_file = os.path.join(VISUALIZATIONS_DIR, f"hubspot_source_analysis_{FILE_SUFFIX}.png")
            plt.savefig(source_file, dpi=300, bbox_inches='tight')
            print(f"Saved source analysis to {source_file}")
            plt.close()

    def export_results(self):
        """Export analysis results to CSV files"""
        print("Exporting results...")
        
        # Export conversion metrics
        metrics_df = pd.DataFrame([self.conversion_metrics])
        metrics_file = os.path.join(OUTPUT_BASE, f"hubspot_conversion_metrics_{FILE_SUFFIX}.csv")
        metrics_df.to_csv(metrics_file, index=False)
        print(f"Exported conversion metrics to {metrics_file}")
        
        # Export source analysis
        source_df = self.analyze_conversion_by_source()
        if source_df is not None:
            source_file = os.path.join(OUTPUT_BASE, f"hubspot_conversion_by_source_{FILE_SUFFIX}.csv")
            source_df.to_csv(source_file, index=False)
            print(f"Exported source analysis to {source_file}")
        
        # Export owner analysis
        owner_df = self.analyze_conversion_by_owner()
        if owner_df is not None:
            owner_file = os.path.join(OUTPUT_BASE, f"hubspot_conversion_by_owner_{FILE_SUFFIX}.csv")
            owner_df.to_csv(owner_file, index=False)
            print(f"Exported owner analysis to {owner_file}")
        
        return {
            "metrics": metrics_file,
            "source_analysis": source_file if source_df is not None else None,
            "owner_analysis": owner_file if owner_df is not None else None
        }

    def generate_executive_summary(self):
        """Generate executive summary for CEO and leadership team"""
        summary = f"""
HubSpot Conversion Rate Analysis - {PERIOD_LABEL}
==========================================

EXECUTIVE SUMMARY for CEO Juan Ignacio Onetto

KEY METRICS:
- Total Pipeline Generated: {self.conversion_metrics['total_leads']:,} leads → {self.conversion_metrics['total_deals']:,} deals
- Overall Conversion Rate: {self.conversion_metrics['lead_to_deal_conversion']:.1f}% (Lead to Deal)
- Closed Won Conversion: {self.conversion_metrics['lead_to_closed_won_conversion']:.1f}% (Lead to Closed Won)
- Deal Win Rate: {self.conversion_metrics['deal_win_rate']:.1f}%
- Revenue Impact: {self.conversion_metrics['total_closed_won_deals']:,} closed won deals

PRODUCT-LED GROWTH INSIGHTS:
1. Current funnel efficiency is {'strong' if self.conversion_metrics['lead_to_deal_conversion'] > 20 else 'moderate' if self.conversion_metrics['lead_to_deal_conversion'] > 10 else 'needs improvement'}
2. Win rate of {self.conversion_metrics['deal_win_rate']:.1f}% {'exceeds' if self.conversion_metrics['deal_win_rate'] > 30 else 'meets' if self.conversion_metrics['deal_win_rate'] > 20 else 'lags'} SaaS benchmarks
3. {'High' if self.conversion_metrics['total_deals'] > 100 else 'Moderate' if self.conversion_metrics['total_deals'] > 50 else 'Low'} volume period with {self.conversion_metrics['total_deals']:,} total opportunities

RECOMMENDATIONS:
- Focus on optimizing the {('lead qualification' if self.conversion_metrics['lead_to_deal_conversion'] < 15 else 'deal closing') if self.conversion_metrics['deal_win_rate'] < 25 else 'lead generation'} process
- Implement PLG tactics to improve self-service conversion
- Analyze top-performing sources for scaling opportunities

Period Analyzed: {START_DATE} to {END_DATE}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Contact: Data Analytics Team - Colppy
        """
        
        summary_file = os.path.join(OUTPUT_BASE, f"hubspot_executive_summary_{FILE_SUFFIX}.txt")
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Generated executive summary: {summary_file}")
        return summary

    def run_full_analysis(self):
        """Run the complete conversion rate analysis"""
        print(f"Starting HubSpot Conversion Rate Analysis for {PERIOD_LABEL}...")
        print("="*60)
        
        # Load data
        self.load_existing_data()
        
        # If no data loaded, try to fetch from API
        if self.contacts_df is None:
            self.fetch_contacts_from_api()
        
        # Prepare data
        self.prepare_data()
        
        # Calculate conversion rates
        metrics = self.calculate_conversion_rates()
        
        # Create visualizations
        self.create_visualizations()
        
        # Export results
        export_files = self.export_results()
        
        # Generate executive summary
        summary = self.generate_executive_summary()
        
        print("\n" + "="*60)
        print("ANALYSIS COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("Generated Files:")
        for key, file_path in export_files.items():
            if file_path:
                print(f"- {key}: {file_path}")
        print(f"- Dashboard: {os.path.join(VISUALIZATIONS_DIR, f'hubspot_conversion_dashboard_{FILE_SUFFIX}.png')}")
        print(f"- Executive Summary: {os.path.join(OUTPUT_BASE, f'hubspot_executive_summary_{FILE_SUFFIX}.txt')}")
        
        return {
            "metrics": metrics,
            "export_files": export_files,
            "summary": summary
        }

def main():
    """Main execution function"""
    analyzer = HubSpotConversionAnalyzer(START_DATE, END_DATE)
    results = analyzer.run_full_analysis()
    
    print("\nQuick Summary:")
    print(f"Lead to Deal Conversion: {results['metrics']['lead_to_deal_conversion']:.2f}%")
    print(f"Deal Win Rate: {results['metrics']['deal_win_rate']:.2f}%")
    print(f"Total Revenue Opportunities: {results['metrics']['total_closed_won_deals']:,} closed won deals")

if __name__ == "__main__":
    main() 