#!/usr/bin/env python3
"""
Intercom Response Delay Analysis

This script analyzes Intercom conversation data for any specified period to understand
conversations with delayed responses (>5 days) and provide insights for
improving ticket prioritization and response times.

Usage:
    python analyze_response_delays.py --month 2025-05
    python analyze_response_delays.py --start-date 2025-05-01 --end-date 2025-06-01
    python analyze_response_delays.py --year 2025 --month-num 5
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
import os
from pathlib import Path
import argparse

warnings.filterwarnings('ignore')

# Set up the environment
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

def parse_arguments():
    """Parse command line arguments for date range"""
    parser = argparse.ArgumentParser(description='Intercom Response Delay Analysis')
    
    # Date range options
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    date_group.add_argument('--month', help='Month in YYYY-MM format')
    date_group.add_argument('--year', type=int, help='Year (use with --month-num)')
    
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD, required with --start-date)')
    parser.add_argument('--month-num', type=int, help='Month number 1-12 (use with --year)', choices=range(1, 13))
    parser.add_argument('--delay-threshold', type=int, default=5, help='Delay threshold in days (default: 5)')
    
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
    
    return start_date, end_date, args.delay_threshold

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

def find_conversation_file(start_date, end_date):
    """Find the appropriate conversation CSV file for the date range"""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Check if it's a full month
    if start_dt.day == 1 and end_dt.day == 1 and end_dt.month != start_dt.month:
        month_name = start_dt.strftime('%B').lower()
        year = start_dt.year
    
        # Try different file patterns for monthly data
        patterns = [
            f'../../outputs/csv_data/intercom/conversations/intercom-conversations-{month_name}-{year}.csv',
            f'outputs/csv_data/intercom/conversations/intercom-conversations-{month_name}-{year}.csv',
            f'../../outputs/csv_data/intercom/conversations/intercom-conversations-{start_dt.strftime("%Y_%m")}.csv',
            f'outputs/csv_data/intercom/conversations/intercom-conversations-{start_dt.strftime("%Y_%m")}.csv',
            f'intercom-conversations-{month_name}-{year}.csv'
        ]
    else:
        # For date ranges, use the numeric format
        file_suffix = get_file_suffix(start_date, end_date)
    patterns = [
            f'../../outputs/csv_data/intercom/conversations/intercom-conversations-{file_suffix}.csv',
        f'outputs/csv_data/intercom/conversations/intercom-conversations-{file_suffix}.csv',
            f'intercom-conversations-{file_suffix}.csv'
    ]
    
    for pattern in patterns:
        if os.path.exists(pattern):
            return pattern
    
    # If no specific file found, return the first pattern for user guidance
    return patterns[0]

# Parse command line arguments
START_DATE, END_DATE, DELAY_THRESHOLD = parse_arguments()
PERIOD_LABEL = get_period_label(START_DATE, END_DATE)
FILE_SUFFIX = get_file_suffix(START_DATE, END_DATE)
CSV_FILE_PATH = find_conversation_file(START_DATE, END_DATE)

class ResponseDelayAnalyzer:
    def __init__(self, csv_file_path, output_dir=f'outputs/intercom_analysis_{FILE_SUFFIX}'):
        self.csv_file_path = csv_file_path
        self.output_dir = output_dir
        self.start_date = START_DATE
        self.end_date = END_DATE
        self.period_label = PERIOD_LABEL
        self.file_suffix = FILE_SUFFIX
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"🔍 Loading {PERIOD_LABEL} conversation data from: {csv_file_path}")
        
    def load_and_process_data(self):
        """Load and process the conversation data"""
        try:
            # Load the CSV file
            df = pd.read_csv(self.csv_file_path)
            print(f"📊 Loaded {len(df):,} conversations from {self.period_label}")
            print(f"📖 Processing {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB of data")
            
            # Show basic info about the dataset
            print(f"\n📋 Dataset columns: {list(df.columns)}")
            
            # Process datetime columns
            datetime_cols = ['created_at', 'updated_at', 'waiting_since', 'snoozed_until']
            for col in datetime_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
            
            # Calculate response times if first_response_time exists
            if 'first_response_time' in df.columns:
                df['first_response_time_hours'] = df['first_response_time'] / 3600
                df['first_response_time_days'] = df['first_response_time'] / (3600 * 24)
            
            # Add hour, day of week, and week analysis
            if 'created_at' in df.columns:
                df['hour_created'] = df['created_at'].dt.hour
                df['day_of_week'] = df['created_at'].dt.day_name()
                df['week_of_month'] = df['created_at'].dt.day.apply(lambda x: (x-1)//7 + 1)
            
            self.df = df
            return df
            
        except Exception as e:
            print(f"❌ Error loading data: {str(e)}")
            raise
    
    def analyze_delayed_responses(self, delay_threshold_days=DELAY_THRESHOLD):
        """Analyze conversations with response delays > threshold"""
        print(f"\n🔍 Analyzing conversations with delays > {delay_threshold_days} days...")
        
        if 'first_response_time_days' not in self.df.columns:
            print("❌ No response time data available")
            return pd.DataFrame()
        
        # Filter conversations with response time data
        responded_df = self.df[self.df['first_response_time_days'].notna()].copy()
        
        # Identify delayed responses
        delayed_df = responded_df[responded_df['first_response_time_days'] > delay_threshold_days].copy()
        
        print(f"📊 Total conversations with response time data: {len(responded_df):,}")
        print(f"🚨 Conversations with delays > {delay_threshold_days} days: {len(delayed_df):,} ({len(delayed_df)/len(responded_df)*100:.1f}%)")
        
        if len(delayed_df) == 0:
            print(f"✅ No conversations found with delays > {delay_threshold_days} days")
            return pd.DataFrame()
        
        # Detailed analysis of delayed conversations
        print(f"\n📈 Delayed Response Statistics:")
        print(f"  • Average delay: {delayed_df['first_response_time_days'].mean():.1f} days")
        print(f"  • Median delay: {delayed_df['first_response_time_days'].median():.1f} days")
        print(f"  • Maximum delay: {delayed_df['first_response_time_days'].max():.1f} days")
        print(f"  • Minimum delay: {delayed_df['first_response_time_days'].min():.1f} days")
        
        # Save delayed conversations to CSV
        delayed_output_path = os.path.join(self.output_dir, f'delayed_conversations_{delay_threshold_days}d.csv')
        delayed_df.to_csv(delayed_output_path, index=False)
        print(f"💾 Saved delayed conversations to: {delayed_output_path}")
        
        return delayed_df
    
    def analyze_team_performance(self):
        """Analyze performance by teams and admins"""
        print(f"\n👥 Analyzing team and admin performance...")
        
        # Team analysis
        if 'team_assignee_id' in self.df.columns and 'first_response_time_days' in self.df.columns:
            team_stats = self.df.groupby('team_assignee_id').agg({
                'first_response_time_days': ['count', 'mean', 'median', 'max'],
                'conversation_rating_value': ['mean', 'count']
            }).round(2)
            
            team_stats.columns = ['total_conversations', 'avg_response_days', 'median_response_days', 
                                 'max_response_days', 'avg_rating', 'rated_conversations']
            
            # Calculate delayed response rate by team
            delayed_by_team = self.df[self.df['first_response_time_days'] > DELAY_THRESHOLD].groupby('team_assignee_id').size()
            total_by_team = self.df[self.df['first_response_time_days'].notna()].groupby('team_assignee_id').size()
            delay_rate = (delayed_by_team / total_by_team * 100).fillna(0)
            team_stats['delay_rate_percent'] = delay_rate
            
            team_stats = team_stats.sort_values('delay_rate_percent', ascending=False)
            print(f"📊 Team performance analysis saved")
            
            # Save team stats
            team_output_path = os.path.join(self.output_dir, 'team_performance.csv')
            team_stats.to_csv(team_output_path)
            
        # Admin analysis
        if 'admin_assignee_id' in self.df.columns and 'first_response_time_days' in self.df.columns:
            admin_stats = self.df.groupby('admin_assignee_id').agg({
                'first_response_time_days': ['count', 'mean', 'median', 'max'],
                'conversation_rating_value': ['mean', 'count']
            }).round(2)
            
            admin_stats.columns = ['total_conversations', 'avg_response_days', 'median_response_days', 
                                  'max_response_days', 'avg_rating', 'rated_conversations']
            
            # Calculate delayed response rate by admin
            delayed_by_admin = self.df[self.df['first_response_time_days'] > DELAY_THRESHOLD].groupby('admin_assignee_id').size()
            total_by_admin = self.df[self.df['first_response_time_days'].notna()].groupby('admin_assignee_id').size()
            delay_rate = (delayed_by_admin / total_by_admin * 100).fillna(0)
            admin_stats['delay_rate_percent'] = delay_rate
            
            admin_stats = admin_stats.sort_values('delay_rate_percent', ascending=False)
            
            # Save admin stats
            admin_output_path = os.path.join(self.output_dir, 'admin_performance.csv')
            admin_stats.to_csv(admin_output_path)
            print(f"📊 Admin performance analysis saved")
    
    def analyze_temporal_patterns(self):
        """Analyze when delayed responses occur most frequently"""
        print(f"\n📅 Analyzing temporal patterns in delayed responses...")
        
        # Day of week analysis
        if 'day_of_week' in self.df.columns and 'first_response_time_days' in self.df.columns:
            delayed_df = self.df[self.df['first_response_time_days'] > DELAY_THRESHOLD]
            
            if len(delayed_df) > 0:
                # Days with most delayed responses
                dow_delays = delayed_df['day_of_week'].value_counts()
                dow_total = self.df[self.df['first_response_time_days'].notna()]['day_of_week'].value_counts()
                dow_delay_rate = (dow_delays / dow_total * 100).fillna(0)
                
                print(f"📈 Day of Week Delay Rates:")
                for day, rate in dow_delay_rate.sort_values(ascending=False).items():
                    count = dow_delays.get(day, 0)
                    print(f"  • {day}: {rate:.1f}% ({count} delayed conversations)")
        
        # Hour of day analysis
        if 'hour_created' in self.df.columns:
            delayed_df = self.df[self.df['first_response_time_days'] > DELAY_THRESHOLD]
            
            if len(delayed_df) > 0:
                hour_delays = delayed_df['hour_created'].value_counts().sort_index()
                hour_total = self.df[self.df['first_response_time_days'].notna()]['hour_created'].value_counts().sort_index()
                hour_delay_rate = (hour_delays / hour_total * 100).fillna(0)
                
                print(f"\n⏰ Time of Day Analysis (hours with highest delay rates):")
                top_delay_hours = hour_delay_rate.nlargest(5)
                for hour, rate in top_delay_hours.items():
                    count = hour_delays.get(hour, 0)
                    try:
                        hour_int = int(str(hour))
                    except (ValueError, TypeError):
                        hour_int = 0
                    print(f"  • {hour_int:02d}:00 - {hour_int+1:02d}:00: {rate:.1f}% ({count} delayed)")
    
    def analyze_conversation_characteristics(self):
        """Analyze characteristics of delayed conversations"""
        print(f"\n🔍 Analyzing characteristics of delayed conversations...")
        
        delayed_df = self.df[self.df['first_response_time_days'] > DELAY_THRESHOLD].copy()
        normal_df = self.df[(self.df['first_response_time_days'] <= DELAY_THRESHOLD) & (self.df['first_response_time_days'].notna())].copy()
        
        if len(delayed_df) == 0:
            print("No delayed conversations to analyze")
            return
        
        # Priority analysis
        if 'priority' in self.df.columns:
            print(f"\n📊 Priority Distribution:")
            delayed_priority = delayed_df['priority'].value_counts(normalize=True) * 100
            normal_priority = normal_df['priority'].value_counts(normalize=True) * 100
            
            for priority in delayed_priority.index:
                delayed_pct = delayed_priority.get(priority, 0)
                normal_pct = normal_priority.get(priority, 0)
                print(f"  • {priority}: Delayed {delayed_pct:.1f}% vs Normal {normal_pct:.1f}%")
        
        # State analysis
        if 'state' in self.df.columns:
            print(f"\n📊 Conversation State Distribution:")
            delayed_state = delayed_df['state'].value_counts(normalize=True) * 100
            
            for state, pct in delayed_state.head(5).items():
                count = (delayed_df['state'] == state).sum()
                print(f"  • {state}: {pct:.1f}% ({count} conversations)")
        
        # Source analysis
        if 'source_type' in self.df.columns:
            print(f"\n📊 Source Type Distribution (Delayed Conversations):")
            delayed_source = delayed_df['source_type'].value_counts(normalize=True) * 100
            
            for source, pct in delayed_source.head(5).items():
                count = (delayed_df['source_type'] == source).sum()
                print(f"  • {source}: {pct:.1f}% ({count} conversations)")
    
    def create_visualizations(self):
        """Create visualizations for the analysis"""
        print(f"\n📊 Creating visualizations...")
        
        # Response time distribution
        if 'first_response_time_days' in self.df.columns:
            plt.figure(figsize=(15, 10))
            
            # Overall response time distribution
            plt.subplot(2, 2, 1)
            response_data = self.df[self.df['first_response_time_days'].notna()]['first_response_time_days']
            plt.hist(response_data, bins=50, edgecolor='black', alpha=0.7)
            plt.axvline(x=5, color='red', linestyle='--', label='5-day threshold')
            plt.xlabel('Response Time (days)')
            plt.ylabel('Number of Conversations')
            plt.title('Response Time Distribution - ' + self.period_label)
            plt.legend()
            plt.yscale('log')
            
            # Delayed responses by day of week
            if 'day_of_week' in self.df.columns:
                plt.subplot(2, 2, 2)
                delayed_df = self.df[self.df['first_response_time_days'] > 5]
                if len(delayed_df) > 0:
                    dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    dow_counts = delayed_df['day_of_week'].value_counts().reindex(dow_order, fill_value=0)
                    plt.bar(range(len(dow_counts)), list(dow_counts.values))
                    plt.xticks(range(len(dow_counts)), [day[:3] for day in dow_counts.index], rotation=45)
                    plt.xlabel('Day of Week')
                    plt.ylabel('Delayed Conversations')
                    plt.title('Delayed Responses by Day of Week')
            
            # Response time by hour of day
            if 'hour_created' in self.df.columns:
                plt.subplot(2, 2, 3)
                hourly_response = self.df.groupby('hour_created')['first_response_time_days'].mean()
                plt.plot(hourly_response.index, hourly_response.values, marker='o')
                plt.axhline(y=5, color='red', linestyle='--', label='5-day threshold')
                plt.xlabel('Hour of Day')
                plt.ylabel('Average Response Time (days)')
                plt.title('Average Response Time by Hour')
                plt.legend()
                plt.grid(True, alpha=0.3)
            
            # Response time trend over period
            if 'created_at' in self.df.columns:
                plt.subplot(2, 2, 4)
                daily_response = self.df.groupby(self.df['created_at'].dt.date)['first_response_time_days'].mean()
                plt.plot(daily_response.index, daily_response.values, marker='o')
                plt.axhline(y=5, color='red', linestyle='--', label='5-day threshold')
                plt.xlabel('Date')
                plt.ylabel('Average Response Time (days)')
                plt.title('Daily Average Response Time - ' + self.period_label)
                plt.xticks(rotation=45)
                plt.legend()
                plt.grid(True, alpha=0.3)
            
            plt.tight_layout()
            viz_path = os.path.join(self.output_dir, 'response_analysis.png')
            plt.savefig(viz_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"📊 Visualization saved to: {viz_path}")
    
    def generate_recommendations(self):
        """Generate actionable recommendations based on the analysis"""
        print(f"\n💡 Generating recommendations for improving response times...")
        
        delayed_df = self.df[self.df['first_response_time_days'] > 5].copy()
        
        recommendations = []
        
        if len(delayed_df) > 0:
            # Calculate key metrics
            total_conversations = len(self.df[self.df['first_response_time_days'].notna()])
            delayed_count = len(delayed_df)
            delay_rate = delayed_count / total_conversations * 100
            avg_delay = delayed_df['first_response_time_days'].mean()
            
            recommendations.append(f"📊 Current Situation:")
            recommendations.append(f"  • {delayed_count:,} conversations ({delay_rate:.1f}%) had response delays > 5 days")
            recommendations.append(f"  • Average delay time: {avg_delay:.1f} days")
            recommendations.append(f"  • Maximum delay: {delayed_df['first_response_time_days'].max():.1f} days")
            recommendations.append("")
            
            # Priority-based recommendations
            if 'priority' in self.df.columns:
                high_priority_delayed = delayed_df[delayed_df['priority'] == 'high']
                if len(high_priority_delayed) > 0:
                    recommendations.append(f"🚨 URGENT - High Priority Issues:")
                    recommendations.append(f"  • {len(high_priority_delayed)} high-priority conversations were delayed")
                    recommendations.append(f"  • Implement immediate escalation for high-priority tickets")
                    recommendations.append("")
            
            # Team-based recommendations
            if 'team_assignee_id' in self.df.columns:
                team_counts = delayed_df.groupby('team_assignee_id').size()
                if len(team_counts) > 0:
                    recommendations.append(f"👥 Team Performance Recommendations:")
                    for team_id, count in team_counts.items():
                        pct = count / len(delayed_df) * 100
                        recommendations.append(f"  • Team {team_id}: {count} delayed conversations ({pct:.1f}%)")
                    recommendations.append(f"  • Consider workload redistribution and additional training")
                    recommendations.append("")
            
            # Temporal recommendations
            if 'day_of_week' in self.df.columns:
                dow_delays = delayed_df['day_of_week'].value_counts()
                worst_day = dow_delays.index[0] if len(dow_delays) > 0 else None
                if worst_day:
                    recommendations.append(f"📅 Temporal Patterns:")
                    recommendations.append(f"  • {worst_day} has the most delayed responses ({dow_delays[worst_day]} conversations)")
                    recommendations.append(f"  • Consider adjusting staffing patterns for {worst_day}")
                    recommendations.append("")
        
        # General recommendations
        recommendations.extend([
            "🎯 Strategic Recommendations:",
            "  1. Implement SLA monitoring with automated alerts at 1, 3, and 4.5 days",
            "  2. Create escalation rules for conversations approaching 5-day threshold",
            "  3. Set up daily review meetings to discuss pending conversations",
            "  4. Implement priority scoring based on customer value and issue type",
            "  5. Create specialized teams for different conversation types",
            "  6. Develop auto-responder for immediate acknowledgment",
            "  7. Implement customer self-service options to reduce ticket volume",
            "",
            "📈 Measurement & Monitoring:",
            "  • Track daily response time metrics by team and individual",
            "  • Monitor conversation aging reports twice daily",
            "  • Set up weekly performance reviews with individual feedback",
            "  • Implement customer satisfaction tracking post-resolution",
            "",
            "🔧 Process Improvements:",
            "  • Standardize conversation triage and categorization",
            "  • Create response templates for common issues",
            "  • Implement conversation routing based on expertise",
            "  • Set up automated reminders for aging conversations"
        ])
        
        # Save recommendations
        rec_path = os.path.join(self.output_dir, 'recommendations.txt')
        with open(rec_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(recommendations))
        
        print(f"💾 Recommendations saved to: {rec_path}")
        
        # Print key recommendations to console
        print("\n" + "="*60)
        print("🎯 KEY RECOMMENDATIONS FOR IMMEDIATE ACTION:")
        print("="*60)
        for line in recommendations[:15]:  # Show first 15 lines
            print(line)
        print("...")
        print(f"📄 Full recommendations available in: {rec_path}")
    
    def run_complete_analysis(self):
        """Run the complete analysis workflow"""
        print("🚀 Starting " + self.period_label + " Response Delay Analysis")
        print("="*60)
        
        try:
            # Load and process data
            self.load_and_process_data()
            
            # Core analyses
            delayed_conversations = self.analyze_delayed_responses()
            self.analyze_team_performance()
            self.analyze_temporal_patterns()
            self.analyze_conversation_characteristics()
            
            # Create visualizations
            self.create_visualizations()
            
            # Generate actionable recommendations
            self.generate_recommendations()
            
            print(f"\n✅ Analysis completed successfully!")
            print(f"📁 All outputs saved to: {self.output_dir}")
            
            return {
                'delayed_conversations': delayed_conversations,
                'output_directory': self.output_dir
            }
            
        except Exception as e:
            print(f"❌ Error during analysis: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

def main():
    """Main function to run the analysis"""
    if not os.path.exists(CSV_FILE_PATH):
        print(f"❌ CSV file not found: {CSV_FILE_PATH}")
        print("Please ensure the conversation data is available.")
        return
    
    analyzer = ResponseDelayAnalyzer(CSV_FILE_PATH)
    results = analyzer.run_complete_analysis()
    
    return results

if __name__ == "__main__":
    main() 