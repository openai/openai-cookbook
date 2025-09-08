#!/usr/bin/env python3
"""
Comprehensive CSAT Analysis for Colppy CEO
==========================================

This script performs systematic analysis of CSAT data (1,209 records) from Intercom support conversations,
building on previous NPS-Mixpanel analysis that revealed the "activity-satisfaction paradox."

Datasets being processed:
- CSAT Dataset: 1,209 customer satisfaction records from Intercom
- Previous Analysis: 455 NPS-Mixpanel connected users with counter-intuitive satisfaction patterns

Analysis Framework:
1. Core CSAT Metrics
2. Satisfaction Segmentation 
3. Team & Agent Performance
4. Channel Effectiveness
5. Support Topic Analysis
6. AI vs Human Assistance Impact
7. Response Time Correlation
8. Subscription Plan Patterns
9. Industry-based Satisfaction
10. Email Matching for NPS-CSAT Connection
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
import os
warnings.filterwarnings('ignore')

# Configure matplotlib for Argentina standards
plt.rcParams['axes.formatter.use_locale'] = True
import locale
try:
    locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'C')
    except:
        pass

class CSATAnalyzer:
    def __init__(self, csat_file_path):
        """Initialize CSAT analyzer with data loading and preprocessing"""
        self.csat_file_path = csat_file_path
        self.df = None
        self.load_and_preprocess_data()
        
    def load_and_preprocess_data(self):
        """Load CSAT data and perform initial preprocessing"""
        print("🔄 Loading CSAT dataset...")
        
        # Load data
        self.df = pd.read_csv(self.csat_file_path)
        
        print(f"📊 Dataset loaded: {len(self.df):,} records")
        print(f"📋 Columns: {len(self.df.columns)} fields")
        print(f"📝 Characters processed: {self.df.memory_usage(deep=True).sum():,}")
        
        # Data preprocessing
        print("\n🔧 Preprocessing data...")
        
        # Convert date columns
        date_columns = ['Updated at (America/Argentina/Buenos_Aires)', 
                       'Conversation started at (America/Argentina/Buenos_Aires)']
        for col in date_columns:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(self.df[col], errors='coerce')
        
        # Clean rating column
        if 'Conversation rating' in self.df.columns:
            self.df['rating'] = pd.to_numeric(self.df['Conversation rating'], errors='coerce')
        
        # Create satisfaction segments
        self.df['satisfaction_segment'] = self.df['rating'].apply(self._categorize_satisfaction)
        
        # Extract month/week for temporal analysis
        if 'Updated at (America/Argentina/Buenos_Aires)' in self.df.columns:
            self.df['update_month'] = self.df['Updated at (America/Argentina/Buenos_Aires)'].dt.to_period('M')
            self.df['update_week'] = self.df['Updated at (America/Argentina/Buenos_Aires)'].dt.to_period('W')
        
        # Clean email column for matching
        if 'User email' in self.df.columns:
            self.df['clean_email'] = self.df['User email'].str.lower().str.strip()
        
        print("✅ Data preprocessing completed")
        
    def _categorize_satisfaction(self, rating):
        """Categorize satisfaction based on 1-5 rating scale"""
        if pd.isna(rating):
            return 'No Rating'
        elif rating >= 4:
            return 'Satisfied (4-5)'
        elif rating == 3:
            return 'Neutral (3)'
        else:
            return 'Dissatisfied (1-2)'
    
    def analyze_core_metrics(self):
        """Analyze core CSAT metrics and distribution"""
        print("\n" + "="*50)
        print("📈 CORE CSAT METRICS ANALYSIS")
        print("="*50)
        
        # Overall metrics
        total_responses = len(self.df)
        rated_responses = len(self.df[self.df['rating'].notna()])
        
        print(f"📊 Total Conversations: {total_responses:,}")
        print(f"📋 Rated Conversations: {rated_responses:,} ({rated_responses/total_responses*100:.1f}%)")
        
        if rated_responses > 0:
            # Rating distribution
            rating_dist = self.df['rating'].value_counts().sort_index()
            
            print(f"\n⭐ Rating Distribution:")
            for rating, count in rating_dist.items():
                if not pd.isna(rating):
                    pct = count/rated_responses*100
                    print(f"   {rating} stars: {count:,} ({pct:.1f}%)")
            
            # CSAT Score (4-5 star ratings)
            satisfied_count = len(self.df[self.df['rating'] >= 4])
            csat_score = satisfied_count / rated_responses * 100
            
            print(f"\n🎯 CSAT Score (4-5 stars): {csat_score:.1f}%")
            print(f"   Satisfied customers: {satisfied_count:,}")
            print(f"   Neutral (3 stars): {len(self.df[self.df['rating'] == 3]):,}")
            print(f"   Dissatisfied (1-2 stars): {len(self.df[self.df['rating'] <= 2]):,}")
            
            # Average rating
            avg_rating = self.df['rating'].mean()
            print(f"\n📊 Average Rating: {avg_rating:.2f}/5.0")
            
            # Satisfaction segments
            segment_dist = self.df['satisfaction_segment'].value_counts()
            print(f"\n🎭 Satisfaction Segments:")
            for segment, count in segment_dist.items():
                pct = count/total_responses*100
                print(f"   {segment}: {count:,} ({pct:.1f}%)")
        
        return {
            'total_responses': total_responses,
            'rated_responses': rated_responses,
            'csat_score': csat_score if rated_responses > 0 else 0,
            'avg_rating': self.df['rating'].mean(),
            'rating_distribution': rating_dist.to_dict() if rated_responses > 0 else {}
        }
    
    def analyze_team_performance(self):
        """Analyze satisfaction by support team and individual agents"""
        print("\n" + "="*50)
        print("👥 TEAM & AGENT PERFORMANCE ANALYSIS")
        print("="*50)
        
        # Team performance
        if 'Team currently assigned' in self.df.columns:
            team_stats = self.df.groupby('Team currently assigned').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100]
            }).round(2)
            
            team_stats.columns = ['Total_Conversations', 'Avg_Rating', 'CSAT_Score']
            team_stats = team_stats.sort_values('CSAT_Score', ascending=False)
            
            print("🏆 Team Performance Ranking:")
            for team, row in team_stats.head(10).iterrows():
                if pd.notna(team) and team != '':
                    print(f"   {team}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Total_Conversations']} convs)")
        
        # Individual agent performance
        if 'Teammate currently assigned' in self.df.columns:
            agent_stats = self.df.groupby('Teammate currently assigned').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            agent_stats.columns = ['Total_Conversations', 'Avg_Rating', 'CSAT_Score']
            # Filter agents with at least 5 conversations
            agent_stats = agent_stats[agent_stats['Total_Conversations'] >= 5]
            agent_stats = agent_stats.sort_values('CSAT_Score', ascending=False)
            
            print(f"\n🌟 Top Agent Performance (min 5 conversations):")
            for agent, row in agent_stats.head(10).iterrows():
                if pd.notna(agent) and agent != '':
                    print(f"   {agent}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Total_Conversations']} convs)")
        
        return {
            'team_performance': team_stats.to_dict() if 'Team currently assigned' in self.df.columns else {},
            'agent_performance': agent_stats.to_dict() if 'Teammate currently assigned' in self.df.columns else {}
        }
    
    def analyze_channel_effectiveness(self):
        """Analyze satisfaction by communication channel"""
        print("\n" + "="*50)
        print("📱 CHANNEL EFFECTIVENESS ANALYSIS")
        print("="*50)
        
        if 'Channel' in self.df.columns:
            channel_stats = self.df.groupby('Channel').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            channel_stats.columns = ['Total_Conversations', 'Avg_Rating', 'CSAT_Score']
            channel_stats = channel_stats.sort_values('CSAT_Score', ascending=False)
            
            print("📊 Channel Performance:")
            for channel, row in channel_stats.iterrows():
                if pd.notna(channel):
                    print(f"   {channel}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Total_Conversations']} convs)")
            
            return channel_stats.to_dict()
        
        return {}
    
    def analyze_ai_vs_human_impact(self):
        """Analyze satisfaction difference between AI-assisted and human-only support"""
        print("\n" + "="*50)
        print("🤖 AI vs HUMAN ASSISTANCE IMPACT")
        print("="*50)
        
        # Check for AI involvement indicators
        ai_columns = ['Fin AI Agent involved', 'Fin AI Agent replied before rating request', 
                     'Chatbot replied before rating request']
        
        ai_analysis = {}
        
        for col in ai_columns:
            if col in self.df.columns:
                # Convert to boolean
                self.df[f'{col}_bool'] = self.df[col].astype(str).str.lower().isin(['true', 'yes', '1'])
                
                ai_involved = self.df[self.df[f'{col}_bool'] == True]
                human_only = self.df[self.df[f'{col}_bool'] == False]
                
                if len(ai_involved) > 0 and len(human_only) > 0:
                    ai_csat = (ai_involved['rating'] >= 4).sum() / len(ai_involved[ai_involved['rating'].notna()]) * 100
                    human_csat = (human_only['rating'] >= 4).sum() / len(human_only[human_only['rating'].notna()]) * 100
                    
                    ai_avg = ai_involved['rating'].mean()
                    human_avg = human_only['rating'].mean()
                    
                    print(f"\n🔍 {col}:")
                    print(f"   AI Involved: {ai_csat:.1f}% CSAT, {ai_avg:.2f} avg ({len(ai_involved)} convs)")
                    print(f"   Human Only: {human_csat:.1f}% CSAT, {human_avg:.2f} avg ({len(human_only)} convs)")
                    print(f"   Difference: {ai_csat - human_csat:+.1f} percentage points")
                    
                    ai_analysis[col] = {
                        'ai_csat': ai_csat,
                        'human_csat': human_csat,
                        'difference': ai_csat - human_csat
                    }
        
        return ai_analysis
    
    def analyze_response_time_correlation(self):
        """Analyze correlation between response times and satisfaction"""
        print("\n" + "="*50)
        print("⏱️ RESPONSE TIME vs SATISFACTION CORRELATION")
        print("="*50)
        
        response_time_columns = [
            'First response time (seconds)',
            'First response time excluding time spent in bot inbox (seconds)',
            'First response time, only within office hours (seconds)'
        ]
        
        correlations = {}
        
        for col in response_time_columns:
            if col in self.df.columns:
                # Convert to numeric and calculate response time in minutes
                self.df[f'{col}_numeric'] = pd.to_numeric(self.df[col], errors='coerce')
                self.df[f'{col}_minutes'] = self.df[f'{col}_numeric'] / 60
                
                # Calculate correlation with rating
                correlation = self.df[[f'{col}_minutes', 'rating']].corr().iloc[0,1]
                
                if not pd.isna(correlation):
                    # Categorize response times
                    self.df[f'{col}_category'] = pd.cut(
                        self.df[f'{col}_minutes'], 
                        bins=[0, 5, 15, 60, np.inf], 
                        labels=['<5 min', '5-15 min', '15-60 min', '>60 min']
                    )
                    
                    # Calculate CSAT by response time category
                    response_time_stats = self.df.groupby(f'{col}_category').agg({
                        'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
                    }).round(2)
                    
                    response_time_stats.columns = ['Count', 'Avg_Rating', 'CSAT_Score']
                    
                    print(f"\n📊 {col.replace('(seconds)', '')}:")
                    print(f"   Correlation with rating: {correlation:.3f}")
                    for category, row in response_time_stats.iterrows():
                        if pd.notna(category):
                            print(f"   {category}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Count']} convs)")
                    
                    correlations[col] = {
                        'correlation': correlation,
                        'category_stats': response_time_stats.to_dict()
                    }
        
        return correlations
    
    def analyze_subscription_plan_patterns(self):
        """Analyze satisfaction patterns by subscription plan"""
        print("\n" + "="*50)
        print("💼 SUBSCRIPTION PLAN SATISFACTION PATTERNS")
        print("="*50)
        
        if 'Company plan' in self.df.columns:
            # Clean and standardize plan names
            self.df['clean_plan'] = self.df['Company plan'].str.strip()
            
            plan_stats = self.df.groupby('clean_plan').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            plan_stats.columns = ['Total_Conversations', 'Avg_Rating', 'CSAT_Score']
            # Filter plans with at least 10 conversations
            plan_stats = plan_stats[plan_stats['Total_Conversations'] >= 10]
            plan_stats = plan_stats.sort_values('CSAT_Score', ascending=False)
            
            print("📊 Plan Performance (min 10 conversations):")
            for plan, row in plan_stats.iterrows():
                if pd.notna(plan) and plan != '':
                    print(f"   {plan}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Total_Conversations']} convs)")
            
            return plan_stats.to_dict()
        
        return {}
    
    def analyze_industry_satisfaction(self):
        """Analyze satisfaction by industry sector"""
        print("\n" + "="*50)
        print("🏭 INDUSTRY-BASED SATISFACTION ANALYSIS")
        print("="*50)
        
        if 'Industria (colppy)' in self.df.columns:
            industry_stats = self.df.groupby('Industria (colppy)').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            industry_stats.columns = ['Total_Conversations', 'Avg_Rating', 'CSAT_Score']
            # Filter industries with at least 5 conversations
            industry_stats = industry_stats[industry_stats['Total_Conversations'] >= 5]
            industry_stats = industry_stats.sort_values('CSAT_Score', ascending=False)
            
            print("📊 Industry Performance (min 5 conversations):")
            for industry, row in industry_stats.head(15).iterrows():
                if pd.notna(industry) and industry != '':
                    print(f"   {industry}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Total_Conversations']} convs)")
            
            return industry_stats.to_dict()
        
        return {}
    
    def analyze_support_topics(self):
        """Analyze satisfaction by support topics and conversation tags"""
        print("\n" + "="*50)
        print("🏷️ SUPPORT TOPIC SATISFACTION ANALYSIS")
        print("="*50)
        
        topic_analysis = {}
        
        # Analyze conversation tags
        if 'Conversation tag' in self.df.columns:
            # Split multiple tags and analyze each
            tag_data = []
            for idx, row in self.df.iterrows():
                if pd.notna(row['Conversation tag']) and pd.notna(row['rating']):
                    tags = str(row['Conversation tag']).split(',')
                    for tag in tags:
                        tag = tag.strip()
                        if tag:
                            tag_data.append({
                                'tag': tag,
                                'rating': row['rating'],
                                'satisfied': row['rating'] >= 4
                            })
            
            if tag_data:
                tag_df = pd.DataFrame(tag_data)
                tag_stats = tag_df.groupby('tag').agg({
                    'rating': ['count', 'mean'],
                    'satisfied': lambda x: x.sum() / len(x) * 100
                }).round(2)
                
                tag_stats.columns = ['Count', 'Avg_Rating', 'CSAT_Score']
                # Filter tags with at least 5 occurrences
                tag_stats = tag_stats[tag_stats['Count'] >= 5]
                tag_stats = tag_stats.sort_values('CSAT_Score', ascending=False)
                
                print("📊 Top Support Topics by CSAT (min 5 occurrences):")
                for tag, row in tag_stats.head(15).iterrows():
                    print(f"   {tag}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Count']} cases)")
                
                topic_analysis['tags'] = tag_stats.to_dict()
        
        # Analyze topics column if available
        if 'Topics' in self.df.columns:
            topic_data = []
            for idx, row in self.df.iterrows():
                if pd.notna(row['Topics']) and pd.notna(row['rating']):
                    topics = str(row['Topics']).split(',')
                    for topic in topics:
                        topic = topic.strip()
                        if topic:
                            topic_data.append({
                                'topic': topic,
                                'rating': row['rating'],
                                'satisfied': row['rating'] >= 4
                            })
            
            if topic_data:
                topic_df = pd.DataFrame(topic_data)
                topic_stats = topic_df.groupby('topic').agg({
                    'rating': ['count', 'mean'],
                    'satisfied': lambda x: x.sum() / len(x) * 100
                }).round(2)
                
                topic_stats.columns = ['Count', 'Avg_Rating', 'CSAT_Score']
                topic_stats = topic_stats[topic_stats['Count'] >= 10]
                topic_stats = topic_stats.sort_values('CSAT_Score', ascending=False)
                
                print(f"\n📋 Product Topics by CSAT (min 10 cases):")
                for topic, row in topic_stats.head(10).iterrows():
                    print(f"   {topic}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Count']} cases)")
                
                topic_analysis['product_topics'] = topic_stats.to_dict()
        
        return topic_analysis
    
    def analyze_temporal_trends(self):
        """Analyze satisfaction trends over time"""
        print("\n" + "="*50)
        print("📅 TEMPORAL SATISFACTION TRENDS")
        print("="*50)
        
        temporal_analysis = {}
        
        # Monthly trends
        if 'update_month' in self.df.columns:
            monthly_stats = self.df.groupby('update_month').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            monthly_stats.columns = ['Count', 'Avg_Rating', 'CSAT_Score']
            
            print("📊 Monthly CSAT Trends:")
            for month, row in monthly_stats.tail(6).iterrows():  # Last 6 months
                print(f"   {month}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Count']} convs)")
            
            temporal_analysis['monthly'] = monthly_stats.to_dict()
        
        # Weekly trends for recent period
        if 'update_week' in self.df.columns:
            weekly_stats = self.df.groupby('update_week').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0]
            }).round(2)
            
            weekly_stats.columns = ['Count', 'Avg_Rating', 'CSAT_Score']
            
            print(f"\n📊 Recent Weekly CSAT Trends:")
            for week, row in weekly_stats.tail(8).iterrows():  # Last 8 weeks
                print(f"   {week}: {row['CSAT_Score']:.1f}% CSAT, {row['Avg_Rating']:.2f} avg ({row['Count']} convs)")
            
            temporal_analysis['weekly'] = weekly_stats.to_dict()
        
        return temporal_analysis
    
    def prepare_email_matching_analysis(self):
        """Prepare email list for matching with NPS-Mixpanel dataset"""
        print("\n" + "="*50)
        print("📧 EMAIL MATCHING PREPARATION")
        print("="*50)
        
        if 'clean_email' in self.df.columns:
            # Get unique emails with their satisfaction metrics
            email_metrics = self.df.groupby('clean_email').agg({
                'rating': ['count', 'mean', lambda x: (x >= 4).sum() / len(x) * 100 if len(x) > 0 else 0],
                'Conversation ID': 'nunique',
                'Updated at (America/Argentina/Buenos_Aires)': ['min', 'max']
            }).round(2)
            
            email_metrics.columns = [
                'total_ratings', 'avg_csat_rating', 'csat_score',
                'unique_conversations', 'first_csat_date', 'last_csat_date'
            ]
            
            # Filter emails with valid data
            valid_emails = email_metrics[
                (email_metrics['total_ratings'] > 0) & 
                (email_metrics['clean_email'].str.contains('@', na=False))
            ].copy()
            
            print(f"📊 Email Matching Statistics:")
            print(f"   Total unique emails: {len(email_metrics):,}")
            print(f"   Valid emails with ratings: {len(valid_emails):,}")
            print(f"   Average conversations per email: {valid_emails['unique_conversations'].mean():.1f}")
            
            # Save email list for matching
            output_file = '/Users/virulana/openai-cookbook/tools/outputs/csv_data/intercom/csat_emails_for_matching.csv'
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            valid_emails.reset_index().to_csv(output_file, index=False)
            print(f"💾 Email list saved to: {output_file}")
            
            return valid_emails.to_dict()
        
        return {}
    
    def generate_comprehensive_summary(self):
        """Generate comprehensive analysis summary with strategic insights"""
        print("\n" + "="*60)
        print("📋 COMPREHENSIVE CSAT ANALYSIS SUMMARY")
        print("="*60)
        
        # Run all analyses
        core_metrics = self.analyze_core_metrics()
        team_performance = self.analyze_team_performance()
        channel_effectiveness = self.analyze_channel_effectiveness()
        ai_impact = self.analyze_ai_vs_human_impact()
        response_time_analysis = self.analyze_response_time_correlation()
        plan_patterns = self.analyze_subscription_plan_patterns()
        industry_analysis = self.analyze_industry_satisfaction()
        topic_analysis = self.analyze_support_topics()
        temporal_trends = self.analyze_temporal_trends()
        email_matching = self.prepare_email_matching_analysis()
        
        print("\n" + "="*60)
        print("🎯 STRATEGIC INSIGHTS & RECOMMENDATIONS")
        print("="*60)
        
        # Key findings
        if core_metrics['rated_responses'] > 0:
            print(f"✅ CSAT Score: {core_metrics['csat_score']:.1f}% - ", end="")
            if core_metrics['csat_score'] >= 80:
                print("Excellent performance")
            elif core_metrics['csat_score'] >= 70:
                print("Good performance with room for improvement")
            else:
                print("Needs attention - below industry standards")
        
        # Response volume insights
        print(f"📊 Response Rate: {core_metrics['rated_responses']/core_metrics['total_responses']*100:.1f}% of conversations rated")
        
        # Connection opportunities
        valid_emails = len([k for k in email_matching.keys() if '@' in str(k)])
        print(f"🔗 Email Matching Opportunity: {valid_emails:,} unique emails available for NPS-CSAT correlation")
        
        print("\n🚀 NEXT STEPS:")
        print("1. Email match with NPS-Mixpanel dataset (455 connected users)")
        print("2. Validate 'activity-satisfaction paradox' in support context")
        print("3. Identify specific friction points in accounting workflows")
        print("4. Analyze AI assistance impact on high-activity users")
        print("5. Deep-dive into support topic satisfaction patterns")
        
        return {
            'core_metrics': core_metrics,
            'team_performance': team_performance,
            'channel_effectiveness': channel_effectiveness,
            'ai_impact': ai_impact,
            'response_time_analysis': response_time_analysis,
            'plan_patterns': plan_patterns,
            'industry_analysis': industry_analysis,
            'topic_analysis': topic_analysis,
            'temporal_trends': temporal_trends,
            'email_matching': email_matching
        }

def main():
    """Main execution function"""
    print("🎯 COLPPY CSAT COMPREHENSIVE ANALYSIS")
    print("=====================================")
    print("Analyzing 1,209 customer satisfaction records from Intercom")
    print("Building on previous NPS-Mixpanel analysis of 455 connected users")
    print("Investigating the 'activity-satisfaction paradox' in support context\n")
    
    # Initialize analyzer
    csat_file = '/Users/virulana/openai-cookbook/tools/outputs/csat.csv'
    analyzer = CSATAnalyzer(csat_file)
    
    # Run comprehensive analysis
    results = analyzer.generate_comprehensive_summary()
    
    print("\n✅ Analysis completed successfully!")
    print("📁 Output files saved to /Users/virulana/openai-cookbook/tools/outputs/csv_data/intercom/")
    
    return results

if __name__ == "__main__":
    results = main() 