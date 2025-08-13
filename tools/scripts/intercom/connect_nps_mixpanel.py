#!/usr/bin/env python3
"""
🔗 COLPPY NPS-MIXPANEL DATA CONNECTOR
Connect NPS survey responses with Mixpanel user behavior data

This script:
1. Loads NPS data from Intercom
2. Loads Mixpanel key events data
3. Connects users by email and user_id
4. Analyzes behavioral patterns vs satisfaction scores
5. Generates insights about user experience

Usage:
    python connect_nps_mixpanel.py --nps-file nps_file.csv --mixpanel-file mixpanel_file.csv
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
from scipy import stats
from scipy.stats import chi2_contingency, pearsonr, spearmanr
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
warnings.filterwarnings('ignore')

# Configure matplotlib for better plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

class NPSMixpanelConnector:
    def __init__(self, nps_file, mixpanel_file, output_dir=None):
        self.nps_file = nps_file
        self.mixpanel_file = mixpanel_file
        self.output_dir = output_dir or f"../../outputs/nps_mixpanel_analysis"
        
        # Create output directory
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"🔗 Connecting NPS and Mixpanel data...")
        print(f"📁 Output directory: {self.output_dir}")
        
    def load_and_prepare_data(self):
        """Load and prepare both datasets for connection."""
        print("📥 Loading NPS data...")
        
        # Load NPS data
        self.nps_data = pd.read_csv(self.nps_file)
        print(f"📊 NPS Data: {len(self.nps_data):,} rows loaded")
        
        # Clean NPS data
        self.nps_data['received_at'] = pd.to_datetime(self.nps_data['received_at'])
        self.nps_data['email'] = self.nps_data['email'].str.lower().str.strip()
        
        # Remove duplicates (keep latest response per user)
        self.nps_data_clean = self.nps_data.sort_values('received_at').drop_duplicates(
            subset=['email'], keep='last'
        ).copy()
        
        print(f"📊 NPS Data (deduplicated): {len(self.nps_data_clean):,} rows")
        
        # Load Mixpanel data
        print("📥 Loading Mixpanel data...")
        try:
            # Read in chunks to handle large file
            chunk_size = 10000
            chunks = []
            
            for chunk in pd.read_csv(self.mixpanel_file, chunksize=chunk_size):
                chunks.append(chunk)
            
            self.mixpanel_data = pd.concat(chunks, ignore_index=True)
            print(f"📊 Mixpanel Data: {len(self.mixpanel_data):,} rows loaded")
            
        except Exception as e:
            print(f"❌ Error loading Mixpanel data: {e}")
            return False
            
        # Clean Mixpanel data
        # Handle date parsing more robustly
        try:
            self.mixpanel_data['Time'] = pd.to_datetime(self.mixpanel_data['Time'], errors='coerce')
        except:
            # Try different date formats
            self.mixpanel_data['Time'] = pd.to_datetime(self.mixpanel_data['Time'], 
                                                       format='%Y-%m-%d %H:%M:%S', 
                                                       errors='coerce')
        
        # Remove rows with invalid dates
        invalid_dates = self.mixpanel_data['Time'].isna().sum()
        if invalid_dates > 0:
            print(f"⚠️  Found {invalid_dates} rows with invalid dates, removing them")
            self.mixpanel_data = self.mixpanel_data.dropna(subset=['Time'])
        
        self.mixpanel_data['email'] = self.mixpanel_data['Email'].str.lower().str.strip()
        
        # Remove rows with missing email
        self.mixpanel_data = self.mixpanel_data.dropna(subset=['email'])
        print(f"📊 Mixpanel Data (with email): {len(self.mixpanel_data):,} rows")
        
        return True
        
    def connect_datasets(self):
        """Connect NPS and Mixpanel data by email."""
        print("🔗 Connecting datasets by email...")
        
        # Get unique users from each dataset
        nps_emails = set(self.nps_data_clean['email'].dropna())
        mixpanel_emails = set(self.mixpanel_data['email'].dropna())
        
        print(f"📧 Unique emails in NPS: {len(nps_emails):,}")
        print(f"📧 Unique emails in Mixpanel: {len(mixpanel_emails):,}")
        
        # Find common emails
        common_emails = nps_emails.intersection(mixpanel_emails)
        print(f"🤝 Common emails: {len(common_emails):,}")
        
        if len(common_emails) == 0:
            print("❌ No common emails found between datasets!")
            return False
            
        # Create connected dataset
        # For each NPS response, get all Mixpanel events for that user
        connected_rows = []
        
        for email in common_emails:
            # Get NPS data for this user
            nps_row = self.nps_data_clean[self.nps_data_clean['email'] == email].iloc[0]
            
            # Get Mixpanel events for this user
            user_events = self.mixpanel_data[self.mixpanel_data['email'] == email].copy()
            
            # Add NPS information to each event
            for _, event_row in user_events.iterrows():
                combined_row = {
                    # NPS data
                    'nps_user_id': nps_row['user_id'],
                    'email': email,
                    'company_name': nps_row['name'],
                    'nps_score': nps_row['¿Qué probabilidades hay de que nos recomiende a familiares y amigos?'],
                    'nps_rating': nps_row.get('rating', ''),
                    'nps_good_feedback': nps_row.get('¡Qué bueno saberlo! ¿Qué es lo que más te gusta de nuestro producto o servicio?', ''),
                    'nps_improvement_feedback': nps_row.get('Lamentamos oír eso. ¿Qué podríamos haber hecho de manera diferente para mejorar tu experiencia?', ''),
                    'nps_future_feedback': nps_row.get('¿Qué es lo más importante que podríamos hacer para mejorar tu experiencia en el futuro?', ''),
                    'nps_received_at': nps_row['received_at'],
                    
                    # Mixpanel data
                    'mixpanel_user_id': email,  # Using email as user identifier
                    'event_time': event_row['Time'],
                    'event_name': event_row.get('Event Name', ''),
                    'key_events_total': event_row.get('D. Eventos clave de todos los usuarios [Total Events]', ''),
                    
                    # User properties from Mixpanel
                    'plan_type': event_row.get('Tipo Plan Empresa', ''),
                    'first_payment_date': event_row.get('Fecha primer pago', ''),
                    'signup_date': event_row.get('Fecha Alta', ''),
                    'session_start_total': event_row.get('A. Session Start [Total Sessions]', ''),
                    'session_end_avg_duration': event_row.get('B. Session End [Average Page duration]', ''),
                    'login_median_frequency': event_row.get('C. Login [Median Frequency per User]', ''),
                    'login_unique_users': event_row.get('E. Login [Unique Users]', ''),
                }
                
                connected_rows.append(combined_row)
        
        self.connected_data = pd.DataFrame(connected_rows)
        print(f"🔗 Connected dataset: {len(self.connected_data):,} rows")
        
        # Convert datetime columns properly
        self.connected_data['event_time'] = pd.to_datetime(self.connected_data['event_time'])
        self.connected_data['nps_received_at'] = pd.to_datetime(self.connected_data['nps_received_at'])
        
        # Add NPS categorization
        def categorize_nps(score):
            if pd.isna(score):
                return 'Unknown'
            if score >= 9:
                return 'Promoter'
            elif score >= 7:
                return 'Passive'
            else:
                return 'Detractor'
                
        self.connected_data['nps_category'] = self.connected_data['nps_score'].apply(categorize_nps)
        
        return True
        
    def analyze_behavioral_patterns(self):
        """Analyze behavioral patterns by NPS category."""
        print("📊 Analyzing behavioral patterns...")
        
        insights = {}
        
        # 1. Event frequency by NPS category
        event_analysis = self.connected_data.groupby(['nps_category', 'event_name']).size().reset_index(name='event_count')
        top_events_by_category = event_analysis.groupby('nps_category').apply(
            lambda x: x.nlargest(10, 'event_count')
        ).reset_index(drop=True)
        
        insights['top_events_by_nps'] = top_events_by_category.to_dict('records')
        
        # 2. User characteristics by NPS
        user_characteristics = self.connected_data.groupby('email').agg({
            'nps_score': 'first',
            'nps_category': 'first',
            'company_name': 'first',
            'plan_type': 'first',
            'first_payment_date': 'first',
            'signup_date': 'first',
            'event_name': 'count'  # Total events per user
        }).rename(columns={'event_name': 'total_events'}).reset_index()
        
        # 3. Plan distribution by NPS
        plan_nps = user_characteristics.groupby(['plan_type', 'nps_category']).size().reset_index(name='user_count')
        insights['plan_nps_distribution'] = plan_nps.to_dict('records')
        
        # 4. Activity level vs NPS
        activity_nps = user_characteristics.groupby('nps_category')['total_events'].agg([
            'count', 'mean', 'median', 'std'
        ]).round(2)
        insights['activity_by_nps'] = activity_nps.to_dict()
        
        # 5. Timeline analysis - FIXED IMPLEMENTATION
        # Events before vs after NPS survey to understand satisfaction progression
        print("📅 Analyzing timeline patterns...")
        timeline_analysis = []
        
        for email in user_characteristics['email']:
            try:
                user_data = self.connected_data[self.connected_data['email'] == email].copy()
                
                # Ensure datetime columns are properly formatted with timezone handling
                user_data['event_time'] = pd.to_datetime(user_data['event_time'], utc=True).dt.tz_localize(None)
                user_data['nps_received_at'] = pd.to_datetime(user_data['nps_received_at'], utc=True).dt.tz_localize(None)
                
                nps_date = user_data['nps_received_at'].iloc[0]
                
                # Compare events before and after NPS survey using timestamps
                nps_timestamp = nps_date
                
                events_before = user_data[user_data['event_time'] < nps_timestamp]
                events_after = user_data[user_data['event_time'] >= nps_timestamp]
                
                # Calculate activity metrics
                total_activity_days = 0
                if len(user_data) > 1:
                    total_activity_days = (user_data['event_time'].max() - user_data['event_time'].min()).days
                
                # Calculate days between first activity and NPS survey
                days_to_nps = 0
                if len(events_before) > 0:
                    days_to_nps = (nps_date - user_data['event_time'].min()).days
                
                # Calculate activity frequency before NPS
                avg_events_per_week_before = 0
                if len(events_before) > 0 and days_to_nps > 0:
                    avg_events_per_week_before = (len(events_before) * 7) / max(days_to_nps, 1)
                
                timeline_analysis.append({
                    'email': email,
                    'nps_score': user_data['nps_score'].iloc[0],
                    'nps_category': user_data['nps_category'].iloc[0],
                    'plan_type': user_data['plan_type'].iloc[0],
                    'company_name': user_data['company_name'].iloc[0],
                    'events_before_nps': len(events_before),
                    'events_after_nps': len(events_after),
                    'total_events': len(user_data),
                    'days_of_activity': total_activity_days,
                    'days_to_nps_survey': days_to_nps,
                    'avg_events_per_week_before_nps': round(avg_events_per_week_before, 2),
                    'activity_ratio_after_before': round(len(events_after) / max(len(events_before), 1), 2),
                    'first_activity_date': user_data['event_time'].min(),
                    'last_activity_date': user_data['event_time'].max(),
                    'nps_survey_date': nps_date
                })
                
            except Exception as e:
                print(f"⚠️  Error processing timeline for {email}: {e}")
                continue
        
        timeline_df = pd.DataFrame(timeline_analysis)
        
        if len(timeline_df) > 0:
            # Aggregate timeline insights by NPS category
            timeline_insights = timeline_df.groupby('nps_category').agg({
                'events_before_nps': ['mean', 'median', 'std'],
                'events_after_nps': ['mean', 'median', 'std'],
                'total_events': ['mean', 'median'],
                'days_of_activity': ['mean', 'median'],
                'days_to_nps_survey': ['mean', 'median'],
                'avg_events_per_week_before_nps': ['mean', 'median'],
                'activity_ratio_after_before': ['mean', 'median']
            }).round(2)
            
            # Add plan-based timeline analysis
            plan_timeline = timeline_df.groupby(['plan_type', 'nps_category']).agg({
                'events_before_nps': 'mean',
                'avg_events_per_week_before_nps': 'mean',
                'activity_ratio_after_before': 'mean'
            }).round(2)
            
            # Identify engagement patterns
            engagement_patterns = {
                'high_engagement_promoters': len(timeline_df[
                    (timeline_df['nps_category'] == 'Promoter') & 
                    (timeline_df['avg_events_per_week_before_nps'] > timeline_df['avg_events_per_week_before_nps'].median())
                ]),
                'low_engagement_detractors': len(timeline_df[
                    (timeline_df['nps_category'] == 'Detractor') & 
                    (timeline_df['avg_events_per_week_before_nps'] < timeline_df['avg_events_per_week_before_nps'].median())
                ]),
                'quick_to_survey_promoters': len(timeline_df[
                    (timeline_df['nps_category'] == 'Promoter') & 
                    (timeline_df['days_to_nps_survey'] < timeline_df['days_to_nps_survey'].median())
                ]),
                'late_survey_detractors': len(timeline_df[
                    (timeline_df['nps_category'] == 'Detractor') & 
                    (timeline_df['days_to_nps_survey'] > timeline_df['days_to_nps_survey'].median())
                ])
            }
            
            insights['timeline_analysis'] = {
                'summary_stats': timeline_insights.to_dict(),
                'plan_timeline_analysis': plan_timeline.to_dict(),
                'engagement_patterns': engagement_patterns,
                'total_users_analyzed': len(timeline_df),
                'key_insights': self.generate_timeline_insights(timeline_df)
            }
            
            # Save detailed timeline data
            timeline_file = f"{self.output_dir}/timeline_analysis_detail.csv"
            timeline_df.to_csv(timeline_file, index=False)
            print(f"📅 Timeline analysis saved: {timeline_file}")
            
        else:
            insights['timeline_analysis'] = {
                'error': 'No timeline data could be processed due to datetime issues'
            }
        
        # Add advanced correlations to insights
        advanced_correlations = self.analyze_advanced_correlations()
        insights['advanced_correlations'] = advanced_correlations
        
        self.insights = insights
        return insights
        
    def analyze_advanced_correlations(self):
        """Advanced correlation analysis with statistical significance."""
        print("🔬 Performing advanced correlation analysis...")
        
        correlations = {}
        
        # Prepare user-level dataset for correlation analysis
        user_analysis = self.connected_data.groupby('email').agg({
            'nps_score': 'first',
            'nps_category': 'first',
            'plan_type': 'first',
            'event_name': 'count',  # Total events
            'event_time': ['min', 'max'],  # First and last activity
            'session_start_total': 'first',
            'session_end_avg_duration': 'first',
            'login_median_frequency': 'first',
            'login_unique_users': 'first',
            'key_events_total': 'first'
        }).reset_index()
        
        # Flatten column names
        user_analysis.columns = [
            'email', 'nps_score', 'nps_category', 'plan_type', 'total_events',
            'first_activity', 'last_activity', 'session_start_total',
            'session_end_avg_duration', 'login_median_frequency', 
            'login_unique_users', 'key_events_total'
        ]
        
        # Calculate additional metrics
        user_analysis['days_active'] = (user_analysis['last_activity'] - user_analysis['first_activity']).dt.days
        user_analysis['events_per_day'] = user_analysis['total_events'] / np.maximum(user_analysis['days_active'], 1)
        
        # Convert categorical variables to numerical for correlation
        le_plan = LabelEncoder()
        user_analysis['plan_type_encoded'] = le_plan.fit_transform(user_analysis['plan_type'].fillna('unknown'))
        
        le_category = LabelEncoder()
        user_analysis['nps_category_encoded'] = le_category.fit_transform(user_analysis['nps_category'])
        
        # Clean numeric columns
        numeric_columns = ['nps_score', 'total_events', 'days_active', 'events_per_day', 
                          'session_start_total', 'session_end_avg_duration', 
                          'login_median_frequency', 'key_events_total', 'plan_type_encoded']
        
        for col in numeric_columns:
            if col in user_analysis.columns:
                user_analysis[col] = pd.to_numeric(user_analysis[col], errors='coerce')
        
        # Remove rows with missing NPS scores
        clean_data = user_analysis.dropna(subset=['nps_score']).copy()
        
        print(f"📊 Analyzing {len(clean_data)} users for correlations")
        
        # 1. CORRELATION MATRIX WITH SIGNIFICANCE TESTING
        correlation_results = {}
        
        # Define correlation pairs to analyze
        correlation_pairs = [
            ('nps_score', 'total_events', 'Activity Level vs Satisfaction'),
            ('nps_score', 'events_per_day', 'Daily Activity Intensity vs Satisfaction'),
            ('nps_score', 'days_active', 'Engagement Duration vs Satisfaction'),
            ('nps_score', 'session_start_total', 'Session Frequency vs Satisfaction'),
            ('nps_score', 'session_end_avg_duration', 'Session Duration vs Satisfaction'),
            ('nps_score', 'login_median_frequency', 'Login Frequency vs Satisfaction'),
            ('nps_score', 'plan_type_encoded', 'Plan Type vs Satisfaction'),
            ('total_events', 'days_active', 'Activity Level vs Engagement Duration'),
            ('events_per_day', 'session_end_avg_duration', 'Activity Intensity vs Session Quality')
        ]
        
        for var1, var2, description in correlation_pairs:
            if var1 in clean_data.columns and var2 in clean_data.columns:
                # Remove missing values for this pair
                pair_data = clean_data[[var1, var2]].dropna()
                
                if len(pair_data) > 10:  # Need sufficient data points
                    # Pearson correlation
                    pearson_corr, pearson_p = pearsonr(pair_data[var1], pair_data[var2])
                    
                    # Spearman correlation (rank-based, more robust)
                    spearman_corr, spearman_p = spearmanr(pair_data[var1], pair_data[var2])
                    
                    # Effect size interpretation
                    def interpret_correlation(r):
                        abs_r = abs(r)
                        if abs_r < 0.1:
                            return "negligible"
                        elif abs_r < 0.3:
                            return "weak"
                        elif abs_r < 0.5:
                            return "moderate"
                        elif abs_r < 0.7:
                            return "strong"
                        else:
                            return "very strong"
                    
                    # Statistical significance levels
                    def significance_level(p):
                        if p < 0.001:
                            return "highly significant (p<0.001)"
                        elif p < 0.01:
                            return "very significant (p<0.01)"
                        elif p < 0.05:
                            return "significant (p<0.05)"
                        elif p < 0.1:
                            return "marginally significant (p<0.1)"
                        else:
                            return "not significant (p≥0.1)"
                    
                    correlation_results[description] = {
                        'pearson_correlation': round(pearson_corr, 4),
                        'pearson_p_value': round(pearson_p, 6),
                        'spearman_correlation': round(spearman_corr, 4),
                        'spearman_p_value': round(spearman_p, 6),
                        'sample_size': len(pair_data),
                        'pearson_interpretation': interpret_correlation(pearson_corr),
                        'spearman_interpretation': interpret_correlation(spearman_corr),
                        'pearson_significance': significance_level(pearson_p),
                        'spearman_significance': significance_level(spearman_p),
                        'confidence_level': f"{(1-min(pearson_p, spearman_p))*100:.1f}%"
                    }
        
        correlations['statistical_correlations'] = correlation_results
        
        # 2. CATEGORICAL ASSOCIATIONS (CHI-SQUARE TESTS)
        categorical_results = {}
        
        # Plan Type vs NPS Category
        if 'plan_type' in clean_data.columns and 'nps_category' in clean_data.columns:
            contingency_table = pd.crosstab(clean_data['plan_type'], clean_data['nps_category'])
            
            if contingency_table.size > 0 and contingency_table.min().min() >= 5:
                chi2, p_value, dof, expected = chi2_contingency(contingency_table)
                
                # Cramér's V for effect size
                n = contingency_table.sum().sum()
                cramers_v = np.sqrt(chi2 / (n * (min(contingency_table.shape) - 1)))
                
                def interpret_cramers_v(v):
                    if v < 0.1:
                        return "negligible association"
                    elif v < 0.3:
                        return "weak association"
                    elif v < 0.5:
                        return "moderate association"
                    else:
                        return "strong association"
                
                categorical_results['plan_type_vs_nps'] = {
                    'chi2_statistic': round(chi2, 4),
                    'p_value': round(p_value, 6),
                    'degrees_of_freedom': dof,
                    'cramers_v': round(cramers_v, 4),
                    'effect_size': interpret_cramers_v(cramers_v),
                    'significance': significance_level(p_value),
                    'contingency_table': contingency_table.to_dict()
                }
        
        correlations['categorical_associations'] = categorical_results
        
        # 3. BEHAVIORAL PATTERN ANALYSIS
        behavior_patterns = {}
        
        # High-value user identification
        high_activity_threshold = clean_data['total_events'].quantile(0.75)
        high_engagement_threshold = clean_data['events_per_day'].quantile(0.75)
        
        # Create behavioral segments
        clean_data['activity_segment'] = pd.cut(clean_data['total_events'], 
                                              bins=3, labels=['Low', 'Medium', 'High'])
        clean_data['engagement_segment'] = pd.cut(clean_data['events_per_day'], 
                                                bins=3, labels=['Low', 'Medium', 'High'])
        
        # Analyze NPS by behavioral segments
        activity_nps = clean_data.groupby('activity_segment')['nps_score'].agg([
            'count', 'mean', 'std'
        ]).round(2)
        
        engagement_nps = clean_data.groupby('engagement_segment')['nps_score'].agg([
            'count', 'mean', 'std'
        ]).round(2)
        
        behavior_patterns['activity_segments'] = activity_nps.to_dict()
        behavior_patterns['engagement_segments'] = engagement_nps.to_dict()
        
        # Calculate probability of being a promoter by segment
        promoter_probabilities = {}
        for segment_type, column in [('activity', 'activity_segment'), ('engagement', 'engagement_segment')]:
            probs = clean_data.groupby(column)['nps_category'].apply(
                lambda x: (x == 'Promoter').sum() / len(x) * 100
            ).round(1)
            promoter_probabilities[f'{segment_type}_promoter_probability'] = probs.to_dict()
        
        behavior_patterns['promoter_probabilities'] = promoter_probabilities
        
        correlations['behavioral_patterns'] = behavior_patterns
        
        # 4. PREDICTIVE FEATURE IMPORTANCE
        try:
            # Prepare features for Random Forest
            feature_columns = ['total_events', 'events_per_day', 'days_active', 'plan_type_encoded']
            available_features = [col for col in feature_columns if col in clean_data.columns]
            
            if len(available_features) >= 2:
                X = clean_data[available_features].fillna(0)
                y = clean_data['nps_category_encoded']
                
                # Train Random Forest
                rf = RandomForestClassifier(n_estimators=100, random_state=42)
                rf.fit(X, y)
                
                # Feature importance
                feature_importance = dict(zip(available_features, rf.feature_importances_))
                sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
                
                correlations['predictive_analysis'] = {
                    'feature_importance': {k: round(v, 4) for k, v in sorted_features},
                    'accuracy_score': round(rf.score(X, y), 4),
                    'most_predictive_feature': sorted_features[0][0],
                    'least_predictive_feature': sorted_features[-1][0]
                }
                
        except Exception as e:
            print(f"⚠️  Predictive analysis failed: {e}")
            correlations['predictive_analysis'] = {'error': str(e)}
        
        # 5. BUSINESS IMPACT CORRELATIONS
        business_impact = {}
        
        # Calculate correlation strength summary
        strong_correlations = []
        for desc, result in correlation_results.items():
            pearson_strength = abs(result['pearson_correlation'])
            spearman_strength = abs(result['spearman_correlation'])
            
            if (pearson_strength > 0.3 and result['pearson_p_value'] < 0.05) or \
               (spearman_strength > 0.3 and result['spearman_p_value'] < 0.05):
                strong_correlations.append({
                    'relationship': desc,
                    'strongest_correlation': max(pearson_strength, spearman_strength),
                    'significance': min(result['pearson_p_value'], result['spearman_p_value']),
                    'sample_size': result['sample_size']
                })
        
        business_impact['significant_correlations_found'] = len(strong_correlations)
        business_impact['strong_relationships'] = strong_correlations
        
        correlations['business_impact'] = business_impact
        
        # Generate correlation insights
        correlations['insights'] = self.generate_correlation_insights(correlation_results, 
                                                                    categorical_results,
                                                                    behavior_patterns)
        
        return correlations
        
    def generate_correlation_insights(self, correlation_results, categorical_results, behavior_patterns):
        """Generate actionable insights from correlation analysis."""
        insights = []
        
        # Statistical correlation insights
        for desc, result in correlation_results.items():
            if result['pearson_p_value'] < 0.05 or result['spearman_p_value'] < 0.05:
                # Find the stronger correlation
                if abs(result['pearson_correlation']) > abs(result['spearman_correlation']):
                    corr_value = result['pearson_correlation']
                    corr_type = "linear"
                    p_value = result['pearson_p_value']
                else:
                    corr_value = result['spearman_correlation']
                    corr_type = "rank-based"
                    p_value = result['spearman_p_value']
                
                # Format insight based on correlation strength and significance
                strength = "strong" if abs(corr_value) > 0.5 else "moderate" if abs(corr_value) > 0.3 else "weak"
                direction = "positive" if corr_value > 0 else "negative"
                confidence = (1 - p_value) * 100
                
                insight = f"{desc}: {strength} {direction} {corr_type} correlation (r={corr_value:.3f}, confidence: {confidence:.1f}%)"
                insights.append(insight)
        
        # Categorical association insights
        if 'plan_type_vs_nps' in categorical_results:
            cat_result = categorical_results['plan_type_vs_nps']
            if cat_result['p_value'] < 0.05:
                insights.append(f"Plan type significantly influences NPS category (χ²={cat_result['chi2_statistic']:.2f}, p={cat_result['p_value']:.4f})")
                insights.append(f"Association strength: {cat_result['effect_size']} (Cramér's V={cat_result['cramers_v']:.3f})")
        
        # Behavioral segment insights
        if 'promoter_probabilities' in behavior_patterns:
            probs = behavior_patterns['promoter_probabilities']
            
            if 'activity_promoter_probability' in probs:
                activity_probs = probs['activity_promoter_probability']
                high_prob = max(activity_probs.values()) if activity_probs else 0
                low_prob = min(activity_probs.values()) if activity_probs else 0
                
                if high_prob - low_prob > 20:  # Significant difference
                    insights.append(f"Activity level strongly predicts promoter status: {high_prob:.1f}% vs {low_prob:.1f}% promoter probability")
            
            if 'engagement_promoter_probability' in probs:
                engagement_probs = probs['engagement_promoter_probability']
                high_prob = max(engagement_probs.values()) if engagement_probs else 0
                low_prob = min(engagement_probs.values()) if engagement_probs else 0
                
                if high_prob - low_prob > 20:  # Significant difference
                    insights.append(f"Daily engagement predicts satisfaction: {high_prob:.1f}% vs {low_prob:.1f}% promoter probability")
        
        return insights
        
    def create_visualizations(self):
        """Create visualizations for the connected data."""
        print("📈 Creating visualizations...")
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('NPS vs Mixpanel Behavioral Analysis - Colppy', fontsize=16, fontweight='bold')
        
        # 1. Activity level by NPS category
        user_summary = self.connected_data.groupby('email').agg({
            'nps_category': 'first',
            'event_name': 'count'
        }).rename(columns={'event_name': 'total_events'}).reset_index()
        
        sns.boxplot(data=user_summary, x='nps_category', y='total_events', ax=axes[0,0])
        axes[0,0].set_title('User Activity Level by NPS Category')
        axes[0,0].set_ylabel('Total Events')
        
        # 2. Plan distribution by NPS
        plan_nps = self.connected_data.groupby('email').agg({
            'nps_category': 'first',
            'plan_type': 'first'
        }).reset_index()
        
        plan_counts = plan_nps.groupby(['plan_type', 'nps_category']).size().unstack(fill_value=0)
        plan_counts.plot(kind='bar', ax=axes[0,1], stacked=True)
        axes[0,1].set_title('Plan Distribution by NPS Category')
        axes[0,1].set_ylabel('Number of Users')
        axes[0,1].tick_params(axis='x', rotation=45)
        
        # 3. Top events by NPS category
        top_events = self.connected_data.groupby(['nps_category', 'event_name']).size().reset_index(name='count')
        top_events_promoters = top_events[top_events['nps_category'] == 'Promoter'].nlargest(5, 'count')
        top_events_detractors = top_events[top_events['nps_category'] == 'Detractor'].nlargest(5, 'count')
        
        # Combine for comparison
        comparison_events = pd.concat([
            top_events_promoters[['event_name', 'count']].assign(category='Promoter'),
            top_events_detractors[['event_name', 'count']].assign(category='Detractor')
        ])
        
        if not comparison_events.empty:
            sns.barplot(data=comparison_events, x='count', y='event_name', hue='category', ax=axes[1,0])
            axes[1,0].set_title('Top Events: Promoters vs Detractors')
        
        # 4. NPS score distribution
        nps_dist = self.connected_data.groupby('email')['nps_score'].first()
        axes[1,1].hist(nps_dist, bins=11, alpha=0.7, edgecolor='black')
        axes[1,1].set_title('NPS Score Distribution')
        axes[1,1].set_xlabel('NPS Score')
        axes[1,1].set_ylabel('Number of Users')
        
        plt.tight_layout()
        
        # Save visualization
        viz_file = f"{self.output_dir}/nps_mixpanel_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(viz_file, dpi=300, bbox_inches='tight')
        print(f"📊 Visualization saved: {viz_file}")
        
        return viz_file
        
    def save_results(self):
        """Save all analysis results."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save connected dataset
        connected_file = f"{self.output_dir}/connected_nps_mixpanel_{timestamp}.csv"
        self.connected_data.to_csv(connected_file, index=False)
        print(f"💾 Connected data saved: {connected_file}")
        
        # Save insights
        self.save_insights(self.insights, self.output_dir, timestamp)
        
        # Create summary report
        summary = {
            'analysis_date': datetime.now().isoformat(),
            'data_connection': {
                'nps_records': len(self.nps_data_clean),
                'mixpanel_records': len(self.mixpanel_data),
                'connected_records': len(self.connected_data),
                'unique_users_connected': self.connected_data['email'].nunique()
            },
            'key_findings': self.generate_key_findings()
        }
        
        summary_file = f"{self.output_dir}/executive_summary_{timestamp}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"📋 Executive summary saved: {summary_file}")
        
        return {
            'connected_data': connected_file,
            'insights': f"{self.output_dir}/nps_mixpanel_insights_{timestamp}.json",
            'summary': summary_file
        }
        
    def generate_key_findings(self):
        """Generate key business findings."""
        user_summary = self.connected_data.groupby('email').agg({
            'nps_category': 'first',
            'event_name': 'count',
            'plan_type': 'first'
        }).rename(columns={'event_name': 'total_events'}).reset_index()
        
        findings = []
        
        # Activity patterns
        avg_activity = user_summary.groupby('nps_category')['total_events'].mean()
        if 'Promoter' in avg_activity and 'Detractor' in avg_activity:
            promoter_activity = avg_activity['Promoter']
            detractor_activity = avg_activity['Detractor']
            
            if promoter_activity > detractor_activity:
                findings.append(f"Promoters are {promoter_activity/detractor_activity:.1f}x more active than Detractors")
            
        # Plan insights
        plan_nps = user_summary.groupby('plan_type')['nps_category'].value_counts(normalize=True)
        for plan in plan_nps.index.get_level_values(0).unique():
            if (plan, 'Promoter') in plan_nps:
                promoter_pct = plan_nps[(plan, 'Promoter')] * 100
                findings.append(f"{plan} plan has {promoter_pct:.1f}% promoters")
        
        return findings
        
    def generate_timeline_insights(self, timeline_df):
        """Generate timeline insights based on the timeline analysis."""
        insights = []
        
        # 1. Activity before NPS patterns
        promoter_avg_before = timeline_df[timeline_df['nps_category'] == 'Promoter']['events_before_nps'].mean()
        detractor_avg_before = timeline_df[timeline_df['nps_category'] == 'Detractor']['events_before_nps'].mean()
        
        if promoter_avg_before > detractor_avg_before:
            ratio = promoter_avg_before / detractor_avg_before
            insights.append(f"Promoters had {ratio:.1f}x more activity before NPS survey than Detractors")
        
        # 2. Engagement frequency patterns
        promoter_weekly_freq = timeline_df[timeline_df['nps_category'] == 'Promoter']['avg_events_per_week_before_nps'].median()
        detractor_weekly_freq = timeline_df[timeline_df['nps_category'] == 'Detractor']['avg_events_per_week_before_nps'].median()
        
        insights.append(f"Promoters: {promoter_weekly_freq:.1f} events/week before NPS")
        insights.append(f"Detractors: {detractor_weekly_freq:.1f} events/week before NPS")
        
        # 3. Time to survey patterns
        promoter_days_to_survey = timeline_df[timeline_df['nps_category'] == 'Promoter']['days_to_nps_survey'].median()
        detractor_days_to_survey = timeline_df[timeline_df['nps_category'] == 'Detractor']['days_to_nps_survey'].median()
        
        insights.append(f"Promoters reached NPS survey after {promoter_days_to_survey:.0f} days median")
        insights.append(f"Detractors reached NPS survey after {detractor_days_to_survey:.0f} days median")
        
        # 4. Post-survey behavior
        promoter_activity_ratio = timeline_df[timeline_df['nps_category'] == 'Promoter']['activity_ratio_after_before'].median()
        detractor_activity_ratio = timeline_df[timeline_df['nps_category'] == 'Detractor']['activity_ratio_after_before'].median()
        
        insights.append(f"Promoters maintained {promoter_activity_ratio:.1f}x activity level after survey")
        insights.append(f"Detractors maintained {detractor_activity_ratio:.1f}x activity level after survey")
        
        # 5. Plan-specific insights
        plan_performance = timeline_df.groupby('plan_type')['avg_events_per_week_before_nps'].mean().sort_values(ascending=False)
        if len(plan_performance) > 0:
            top_plan = plan_performance.index[0]
            top_engagement = plan_performance.iloc[0]
            insights.append(f"Most engaged plan before NPS: {top_plan} ({top_engagement:.1f} events/week)")
        
        return insights
        
    def save_insights(self, insights, output_dir, timestamp):
        """Save insights to JSON file with proper serialization."""
        def make_serializable(obj):
            """Convert non-serializable objects to serializable format."""
            if isinstance(obj, dict):
                return {str(k): make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(item) for item in obj]
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            elif hasattr(obj, '__str__'):  # other objects with string representation
                return str(obj)
            else:
                return obj
        
        serializable_insights = make_serializable(insights)
        
        insights_file = f"{output_dir}/nps_mixpanel_insights_{timestamp}.json"
        with open(insights_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_insights, f, indent=2, ensure_ascii=False)
        print(f"💾 Insights saved: {insights_file}")
        
    def run_analysis(self):
        """Run the complete analysis pipeline."""
        try:
            # Load data
            if not self.load_and_prepare_data():
                return False
                
            # Connect datasets
            if not self.connect_datasets():
                return False
                
            # Analyze patterns
            self.analyze_behavioral_patterns()
            
            # Create visualizations
            self.create_visualizations()
            
            # Save results
            files = self.save_results()
            
            print("\n✅ Analysis completed successfully!")
            print(f"📊 Connected {self.connected_data['email'].nunique()} users")
            print(f"🔗 Generated {len(self.connected_data)} connected records")
            
            return True
            
        except Exception as e:
            print(f"❌ Error during analysis: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Connect NPS and Mixpanel data for analysis')
    parser.add_argument('--nps-file', required=True, help='Path to NPS CSV file')
    parser.add_argument('--mixpanel-file', required=True, help='Path to Mixpanel CSV file')
    parser.add_argument('--output-dir', help='Output directory for results')
    
    args = parser.parse_args()
    
    # Run analysis
    connector = NPSMixpanelConnector(
        nps_file=args.nps_file,
        mixpanel_file=args.mixpanel_file,
        output_dir=args.output_dir
    )
    
    success = connector.run_analysis()
    
    if success:
        print("\n🎯 Ready for strategic insights!")
    else:
        print("\n❌ Analysis failed. Check the error messages above.")

if __name__ == "__main__":
    main() 