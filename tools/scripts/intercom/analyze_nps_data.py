#!/usr/bin/env python3
"""
🎯 COLPPY NPS ANALYSIS TOOL
Comprehensive analysis of Net Promoter Score (NPS) data from Intercom surveys

This script analyzes NPS survey responses to provide:
1. Overall NPS calculation and categorization
2. Response trends over time
3. Detractor feedback analysis
4. Duplicate detection and handling
5. Response rate analysis
6. Sentiment analysis of feedback

Usage:
    python analyze_nps_data.py --files path/to/nps_file1.csv path/to/nps_file2.csv [--output-dir outputs/]
    python analyze_nps_data.py --file path/to/nps_file.csv [--output-dir outputs/]  # Single file (backward compatible)
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
warnings.filterwarnings('ignore')

# Configure matplotlib for better visualizations
plt.style.use('default')
sns.set_palette("husl")

class NPSAnalyzer:
    def __init__(self, file_paths, output_dir="outputs/nps_analysis"):
        """Initialize NPS Analyzer with file path(s) and output directory.
        
        Args:
            file_paths: Single file path (str) or list of file paths (list)
            output_dir: Output directory for results
        """
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
            
            # Show breakdown by source file
            if 'source_file' in self.df.columns:
                file_breakdown = self.df['source_file'].value_counts()
                print(f"\n📋 Responses by source file:")
                for file_name, count in file_breakdown.items():
                    print(f"   • {file_name}: {count:,} responses")
            
            # Identify duplicates
            self.identify_duplicates()
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading data: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def identify_duplicates(self):
        """Identify and handle duplicate responses.
        
        Only removes true duplicates (same email, same date, same score).
        Keeps multiple responses from the same user across different time periods
        to track how their answers evolved.
        """
        # Create date-only column for same-day duplicate detection
        self.df['received_date'] = self.df['received_at'].dt.date
        
        # Identify true duplicates: same email, same date, same score
        # These are likely duplicate submissions on the same day
        duplicate_mask = self.df.duplicated(
            subset=['email', 'received_date', 'nps_score'],
            keep='first'
        )
        
        true_duplicates = self.df[duplicate_mask]
        duplicate_count = len(true_duplicates)
        
        if duplicate_count > 0:
            print(f"⚠️  Found {duplicate_count} true duplicates (same email, same date, same score)")
            print(f"   Removing these duplicates while keeping legitimate multiple responses...")
            
            # Remove only true duplicates
            self.df_deduplicated = self.df[~duplicate_mask].copy()
            
            print(f"📊 After removing true duplicates: {len(self.df_deduplicated):,} responses")
        else:
            self.df_deduplicated = self.df.copy()
            print("✅ No true duplicates found (same email, same date, same score)")
        
        # Analyze users with multiple responses across different periods
        users_with_multiple = self.df_deduplicated.groupby('email').size()
        users_multiple_responses = users_with_multiple[users_with_multiple > 1]
        
        if len(users_multiple_responses) > 0:
            print(f"📈 Found {len(users_multiple_responses)} users with multiple responses across different periods")
            print(f"   These will be analyzed to track answer evolution over time")
            
            # Calculate time differences between responses for these users
            user_evolution_data = []
            for email in users_multiple_responses.index:
                user_responses = self.df_deduplicated[
                    self.df_deduplicated['email'] == email
                ].sort_values('received_at')
                
                if len(user_responses) > 1:
                    first_response = user_responses.iloc[0]
                    last_response = user_responses.iloc[-1]
                    
                    time_diff = (last_response['received_at'] - first_response['received_at']).days
                    
                    user_evolution_data.append({
                        'email': email,
                        'response_count': len(user_responses),
                        'first_response_date': first_response['received_at'],
                        'last_response_date': last_response['received_at'],
                        'days_between': time_diff,
                        'first_score': first_response['nps_score'],
                        'last_score': last_response['nps_score'],
                        'score_change': last_response['nps_score'] - first_response['nps_score']
                    })
            
            # Store evolution analysis
            self.analysis_results['user_evolution'] = {
                'users_with_multiple_responses': len(users_multiple_responses),
                'total_multiple_responses': users_multiple_responses.sum(),
                'evolution_data': user_evolution_data
            }
            
            # Store duplicate info for reporting
            self.analysis_results['duplicates'] = {
            'true_duplicates_removed': duplicate_count,
                'total_responses_before': len(self.df),
            'total_responses_after': len(self.df_deduplicated),
            'users_with_multiple_responses': len(users_multiple_responses) if len(users_multiple_responses) > 0 else 0
        }
        
        # Add source file breakdown if available
        if 'source_file' in self.df.columns:
            source_breakdown = self.df['source_file'].value_counts().to_dict()
            self.analysis_results['source_files'] = {
                'total_files': len(self.file_paths),
                'files_processed': list(source_breakdown.keys()),
                'responses_per_file': source_breakdown
            }
    
    def calculate_nps_metrics(self):
        """Calculate comprehensive NPS metrics."""
        df = self.df_deduplicated
        
        # Categorize responses
        df['nps_category'] = df['nps_score'].apply(self.categorize_nps_score)
        
        # Calculate NPS components
        total_responses = len(df)
        promoters = len(df[df['nps_category'] == 'Promoter'])
        passives = len(df[df['nps_category'] == 'Passive'])
        detractors = len(df[df['nps_category'] == 'Detractor'])
        
        # Calculate percentages
        promoter_pct = (promoters / total_responses) * 100
        passive_pct = (passives / total_responses) * 100
        detractor_pct = (detractors / total_responses) * 100
        
        # Calculate NPS (Promoters % - Detractors %)
        nps_score = promoter_pct - detractor_pct
        
        # Calculate average score
        avg_score = df['nps_score'].mean()
        
        # Store results
        self.analysis_results['nps_metrics'] = {
            'nps_score': round(nps_score, 1),
            'total_responses': total_responses,
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
            'promoter_percentage': round(promoter_pct, 1),
            'passive_percentage': round(passive_pct, 1),
            'detractor_percentage': round(detractor_pct, 1),
            'average_score': round(avg_score, 2)
        }
        
        print(f"📊 NPS Score: {nps_score:.1f}")
        print(f"   Promoters: {promoters} ({promoter_pct:.1f}%)")
        print(f"   Passives: {passives} ({passive_pct:.1f}%)")
        print(f"   Detractors: {detractors} ({detractor_pct:.1f}%)")
        
        return self.analysis_results['nps_metrics']
    
    def categorize_nps_score(self, score):
        """Categorize NPS score into Promoter, Passive, or Detractor."""
        if pd.isna(score):
            return 'Unknown'
        elif score >= 9:
            return 'Promoter'
        elif score >= 7:
            return 'Passive'
        else:
            return 'Detractor'
    
    def analyze_temporal_trends(self):
        """Analyze NPS trends over time."""
        df = self.df_deduplicated.copy()
        
        # Add time-based columns
        df['month_year'] = df['received_at'].dt.to_period('M')
        df['week'] = df['received_at'].dt.to_period('W')
        df['nps_category'] = df['nps_score'].apply(self.categorize_nps_score)
        
        # Monthly trends
        monthly_stats = df.groupby('month_year').agg({
            'nps_score': ['count', 'mean'],
            'nps_category': lambda x: (x == 'Promoter').sum() - (x == 'Detractor').sum()
        }).round(2)
        
        monthly_stats.columns = ['response_count', 'avg_score', 'nps_calculation']
        monthly_stats['nps_score'] = (monthly_stats['nps_calculation'] / monthly_stats['response_count']) * 100
        
        # Weekly trends (last 8 weeks)
        recent_weeks = df[df['received_at'] >= df['received_at'].max() - timedelta(weeks=8)]
        weekly_stats = recent_weeks.groupby('week').agg({
            'nps_score': ['count', 'mean'],
            'nps_category': lambda x: (x == 'Promoter').sum() - (x == 'Detractor').sum()
        }).round(2)
        
        weekly_stats.columns = ['response_count', 'avg_score', 'nps_calculation']
        weekly_stats['nps_score'] = (weekly_stats['nps_calculation'] / weekly_stats['response_count']) * 100
        
        # Convert Period indices to strings for JSON serialization
        monthly_dict = {}
        for period, row in monthly_stats.iterrows():
            monthly_dict[str(period)] = row.to_dict()
            
        weekly_dict = {}
        for period, row in weekly_stats.iterrows():
            weekly_dict[str(period)] = row.to_dict()
        
        self.analysis_results['temporal_trends'] = {
            'monthly_trends': monthly_dict,
            'weekly_trends': weekly_dict
        }
        
        return monthly_stats, weekly_stats
    
    def analyze_feedback(self):
        """Analyze qualitative feedback from responses."""
        df = self.df_deduplicated
        
        # Promoter feedback analysis
        promoter_feedback = df[df['nps_score'] >= 9]['promoter_feedback'].dropna()
        
        # Detractor feedback analysis
        detractor_feedback = df[df['nps_score'] <= 6]['detractor_feedback'].dropna()
        improvement_feedback = df[df['nps_score'] <= 6]['improvement_feedback'].dropna()
        
        # Common themes in detractor feedback (simple keyword analysis)
        detractor_keywords = self.extract_keywords(detractor_feedback)
        improvement_keywords = self.extract_keywords(improvement_feedback)
        promoter_keywords = self.extract_keywords(promoter_feedback)
        
        self.analysis_results['feedback_analysis'] = {
            'promoter_feedback_count': len(promoter_feedback),
            'detractor_feedback_count': len(detractor_feedback),
            'improvement_feedback_count': len(improvement_feedback),
            'detractor_keywords': detractor_keywords,
            'improvement_keywords': improvement_keywords,
            'promoter_keywords': promoter_keywords,
            'sample_detractor_feedback': detractor_feedback.head(10).tolist(),
            'sample_promoter_feedback': promoter_feedback.head(10).tolist()
        }
        
        return self.analysis_results['feedback_analysis']
    
    def analyze_user_evolution(self):
        """Analyze how individual users' NPS scores evolved over time."""
        if 'user_evolution' not in self.analysis_results:
            print("ℹ️  No users with multiple responses found for evolution analysis")
            return None
        
        evolution_data = self.analysis_results['user_evolution']['evolution_data']
        if not evolution_data:
            return None
        
        df_evolution = pd.DataFrame(evolution_data)
        
        # Calculate evolution statistics
        improved = len(df_evolution[df_evolution['score_change'] > 0])
        declined = len(df_evolution[df_evolution['score_change'] < 0])
        unchanged = len(df_evolution[df_evolution['score_change'] == 0])
        
        avg_score_change = df_evolution['score_change'].mean()
        avg_days_between = df_evolution['days_between'].mean()
        
        # Categorize evolution patterns
        significant_improvement = len(df_evolution[df_evolution['score_change'] >= 3])
        significant_decline = len(df_evolution[df_evolution['score_change'] <= -3])
        
        evolution_stats = {
            'total_users_tracked': len(df_evolution),
            'improved': improved,
            'declined': declined,
            'unchanged': unchanged,
            'significant_improvement': significant_improvement,
            'significant_decline': significant_decline,
            'avg_score_change': round(avg_score_change, 2),
            'avg_days_between_responses': round(avg_days_between, 1),
            'improvement_rate': round((improved / len(df_evolution)) * 100, 1) if len(df_evolution) > 0 else 0,
            'decline_rate': round((declined / len(df_evolution)) * 100, 1) if len(df_evolution) > 0 else 0
        }
        
        self.analysis_results['user_evolution_stats'] = evolution_stats
        
        print(f"\n📈 User Evolution Analysis:")
        print(f"   Users with multiple responses: {len(df_evolution)}")
        print(f"   Improved: {improved} ({evolution_stats['improvement_rate']}%)")
        print(f"   Declined: {declined} ({evolution_stats['decline_rate']}%)")
        print(f"   Unchanged: {unchanged}")
        print(f"   Significant improvement (≥3 points): {significant_improvement}")
        print(f"   Significant decline (≤-3 points): {significant_decline}")
        print(f"   Average score change: {avg_score_change:+.2f} points")
        print(f"   Average time between responses: {avg_days_between:.1f} days")
        
        return evolution_stats
    
    def extract_keywords(self, feedback_series):
        """Extract common keywords from feedback text."""
        if len(feedback_series) == 0:
            return {}
        
        # Simple keyword extraction (more sophisticated NLP could be added)
        all_text = ' '.join(feedback_series.astype(str).str.lower())
        
        # Common Spanish words to filter out
        stop_words = {'el', 'la', 'de', 'que', 'y', 'en', 'un', 'es', 'se', 'no', 'te', 'lo', 'le', 'da', 'su', 'por', 'son', 'con', 'para', 'al', 'del', 'los', 'las', 'muy', 'más', 'pero', 'una', 'me', 'si', 'ya', 'está', 'todo', 'hay', 'vez', 'puede', 'hace', 'tiene', 'ser', 'o', 'a', 'e'}
        
        words = all_text.split()
        word_freq = {}
        
        for word in words:
            # Clean word (remove punctuation)
            clean_word = ''.join(c for c in word if c.isalnum())
            if len(clean_word) > 2 and clean_word not in stop_words:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
        
        # Return top 10 keywords
        return dict(sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10])
    
    def create_visualizations(self):
        """Create comprehensive NPS visualizations in a single consolidated dashboard."""
        df = self.df_deduplicated
        
        # Set up the plotting style
        plt.style.use('default')
        
        # Determine grid size based on whether we have user evolution data
        has_evolution = 'user_evolution_stats' in self.analysis_results and \
                       self.analysis_results['user_evolution_stats']['total_users_tracked'] > 0
        
        if has_evolution:
            # Larger figure for consolidated view with user evolution
            fig = plt.figure(figsize=(24, 20))
            grid_rows, grid_cols = 4, 4  # 16 subplots total
        else:
            # Standard size if no evolution data
        fig = plt.figure(figsize=(20, 16))
            grid_rows, grid_cols = 3, 3  # 9 subplots
        
        # 1. NPS Distribution
        ax1 = plt.subplot(grid_rows, grid_cols, 1)
        nps_counts = df['nps_score'].value_counts().sort_index()
        colors = ['#d32f2f' if x <= 6 else '#ff9800' if x <= 8 else '#388e3c' for x in nps_counts.index]
        bars = ax1.bar(nps_counts.index, nps_counts.values, color=colors, alpha=0.8)
        ax1.set_title('Distribución de Puntuaciones NPS', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Puntuación NPS')
        ax1.set_ylabel('Cantidad de Respuestas')
        ax1.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom')
        
        # 2. NPS Categories Pie Chart
        ax2 = plt.subplot(grid_rows, grid_cols, 2)
        df['nps_category'] = df['nps_score'].apply(self.categorize_nps_score)
        category_counts = df['nps_category'].value_counts()
        colors_pie = ['#388e3c', '#ff9800', '#d32f2f']
        wedges, texts, autotexts = ax2.pie(category_counts.values, labels=category_counts.index, 
                                          autopct='%1.1f%%', colors=colors_pie, startangle=90)
        ax2.set_title('Categorías NPS', fontsize=14, fontweight='bold')
        
        # 3. Monthly Trend
        monthly_stats, weekly_stats = self.analyze_temporal_trends()
        if len(monthly_stats) > 1:
            ax3 = plt.subplot(grid_rows, grid_cols, 3)
            months = [str(m) for m in monthly_stats.index]
            ax3.plot(months, monthly_stats['nps_score'], marker='o', linewidth=2, markersize=8)
            ax3.set_title('Evolución NPS Mensual', fontsize=14, fontweight='bold')
            ax3.set_xlabel('Mes')
            ax3.set_ylabel('NPS Score')
            ax3.grid(True, alpha=0.3)
            ax3.tick_params(axis='x', rotation=45)
        
        # 4. Response Volume Over Time
        ax4 = plt.subplot(grid_rows, grid_cols, 4)
        df['date'] = df['received_at'].dt.date
        daily_responses = df.groupby('date').size()
        ax4.plot(daily_responses.index, daily_responses.values, alpha=0.7)
        ax4.set_title('Volumen de Respuestas Diarias', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Fecha')
        ax4.set_ylabel('Respuestas')
        ax4.grid(True, alpha=0.3)
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
        
        # 5. NPS by Month Heatmap
        if len(monthly_stats) > 1:
            ax5 = plt.subplot(grid_rows, grid_cols, 5)
            # Create a simple heatmap-style visualization
            months = list(range(len(monthly_stats)))
            scores = monthly_stats['nps_score'].values
            colors_heat = plt.cm.RdYlGn((scores + 100) / 200)  # Normalize to 0-1
            bars = ax5.bar(months, scores, color=colors_heat)
            ax5.set_title('NPS Score por Mes', fontsize=14, fontweight='bold')
            ax5.set_xlabel('Mes (índice)')
            ax5.set_ylabel('NPS Score')
            ax5.grid(axis='y', alpha=0.3)
        
        # 6. Average Score Distribution
        ax6 = plt.subplot(grid_rows, grid_cols, 6)
        ax6.hist(df['nps_score'], bins=11, alpha=0.7, color='skyblue', edgecolor='black')
        ax6.axvline(df['nps_score'].mean(), color='red', linestyle='--', linewidth=2, 
                   label=f'Promedio: {df["nps_score"].mean():.1f}')
        ax6.set_title('Histograma de Puntuaciones', fontsize=14, fontweight='bold')
        ax6.set_xlabel('Puntuación NPS')
        ax6.set_ylabel('Frecuencia')
        ax6.legend()
        ax6.grid(axis='y', alpha=0.3)
        
        # 7. Response Rate by Hour (if time data available)
        if 'received_at' in df.columns:
            ax7 = plt.subplot(grid_rows, grid_cols, 7)
            df['hour'] = df['received_at'].dt.hour
            hourly_responses = df.groupby('hour').size()
            ax7.bar(hourly_responses.index, hourly_responses.values, alpha=0.7, color='lightcoral')
            ax7.set_title('Respuestas por Hora del Día', fontsize=14, fontweight='bold')
            ax7.set_xlabel('Hora')
            ax7.set_ylabel('Cantidad de Respuestas')
            ax7.grid(axis='y', alpha=0.3)
        
        # 8. Weekly Trend (Recent 8 weeks)
        if len(weekly_stats) > 1:
            ax8 = plt.subplot(grid_rows, grid_cols, 8)
            weeks = [str(w) for w in weekly_stats.index]
            ax8.plot(weeks, weekly_stats['nps_score'], marker='s', linewidth=2, markersize=6, color='orange')
            ax8.set_title('Evolución NPS Semanal (Últimas 8 semanas)', fontsize=14, fontweight='bold')
            ax8.set_xlabel('Semana')
            ax8.set_ylabel('NPS Score')
            ax8.grid(True, alpha=0.3)
            ax8.tick_params(axis='x', rotation=45)
        
        # 9. Summary Stats Box
        ax9 = plt.subplot(grid_rows, grid_cols, 9)
        ax9.axis('off')
        
        # Create summary statistics text
        nps_metrics = self.analysis_results['nps_metrics']
        
        summary_text = f"""
        RESUMEN NPS
        
        🎯 NPS Score: {nps_metrics['nps_score']}
        
        📊 Distribución:
        • Promotores: {nps_metrics['promoters']} ({nps_metrics['promoter_percentage']}%)
        • Pasivos: {nps_metrics['passives']} ({nps_metrics['passive_percentage']}%)
        • Detractores: {nps_metrics['detractors']} ({nps_metrics['detractor_percentage']}%)
        
        📈 Promedio: {nps_metrics['average_score']}
        📝 Total Respuestas: {nps_metrics['total_responses']:,}
        
        📅 Período Analizado:
        {df['received_at'].min().strftime('%d/%m/%Y')} - {df['received_at'].max().strftime('%d/%m/%Y')}
        """
        
        ax9.text(0.1, 0.9, summary_text, transform=ax9.transAxes, fontsize=10,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
        
        # Add user evolution visualizations if data exists
        if has_evolution:
            self._add_user_evolution_charts(fig, grid_rows, grid_cols)
        
        plt.tight_layout()
        
        # Save the consolidated plot
        plot_path = self.output_dir / f"nps_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"📊 Consolidated visualization saved to: {plot_path}")
        
        return plot_path
    
    def _add_user_evolution_charts(self, fig, grid_rows, grid_cols):
        """Add user evolution charts to the main consolidated visualization."""
        if 'user_evolution' not in self.analysis_results:
            return
        
        evolution_data = self.analysis_results['user_evolution']['evolution_data']
        if not evolution_data:
            return
        
        df_evolution = pd.DataFrame(evolution_data)
        
        # 10. Score Change Distribution
        ax10 = plt.subplot(grid_rows, grid_cols, 10)
        score_changes = df_evolution['score_change']
        ax10.hist(score_changes, bins=20, color='skyblue', edgecolor='black', alpha=0.7)
        ax10.axvline(0, color='red', linestyle='--', linewidth=2, label='Sin cambio')
        ax10.axvline(score_changes.mean(), color='green', linestyle='--', linewidth=2, 
                   label=f'Promedio: {score_changes.mean():+.2f}')
        ax10.set_title('Distribución de Cambios en Puntuación', fontsize=11, fontweight='bold')
        ax10.set_xlabel('Cambio en Puntuación')
        ax10.set_ylabel('Cantidad de Usuarios')
        ax10.legend(fontsize=8)
        ax10.grid(axis='y', alpha=0.3)
        
        # 11. Evolution Categories Pie Chart
        ax11 = plt.subplot(grid_rows, grid_cols, 11)
        improved = len(df_evolution[df_evolution['score_change'] > 0])
        declined = len(df_evolution[df_evolution['score_change'] < 0])
        unchanged = len(df_evolution[df_evolution['score_change'] == 0])
        categories = ['Mejoraron', 'Empeoraron', 'Sin Cambio']
        sizes = [improved, declined, unchanged]
        colors_pie = ['#388e3c', '#d32f2f', '#ff9800']
        wedges, texts, autotexts = ax11.pie(sizes, labels=categories, autopct='%1.1f%%',
                                          colors=colors_pie, startangle=90, textprops={'fontsize': 9})
        ax11.set_title('Categorías de Evolución', fontsize=11, fontweight='bold')
        
        # 12. Time Between Responses
        ax12 = plt.subplot(grid_rows, grid_cols, 12)
        days_between = df_evolution['days_between']
        ax12.hist(days_between, bins=15, color='lightcoral', edgecolor='black', alpha=0.7)
        ax12.axvline(days_between.mean(), color='blue', linestyle='--', linewidth=2,
                   label=f'Promedio: {days_between.mean():.1f} días')
        ax12.set_title('Tiempo Entre Respuestas', fontsize=11, fontweight='bold')
        ax12.set_xlabel('Días entre Respuestas')
        ax12.set_ylabel('Cantidad de Usuarios')
        ax12.legend(fontsize=8)
        ax12.grid(axis='y', alpha=0.3)
        
        # 13. First vs Last Score Scatter
        ax13 = plt.subplot(grid_rows, grid_cols, 13)
        ax13.scatter(df_evolution['first_score'], df_evolution['last_score'], 
                   alpha=0.6, s=30, c=df_evolution['score_change'], 
                   cmap='RdYlGn', edgecolors='black', linewidth=0.3)
        # Add diagonal line (no change)
        max_score = max(df_evolution['first_score'].max(), df_evolution['last_score'].max())
        min_score = min(df_evolution['first_score'].min(), df_evolution['last_score'].min())
        ax13.plot([min_score, max_score], [min_score, max_score], 
                'r--', linewidth=1.5, label='Sin cambio')
        ax13.set_title('Primera vs Última Puntuación', fontsize=11, fontweight='bold')
        ax13.set_xlabel('Primera Puntuación')
        ax13.set_ylabel('Última Puntuación')
        ax13.legend(fontsize=8)
        ax13.grid(True, alpha=0.3)
        
        # 14. Score Change by Time Period
        ax14 = plt.subplot(grid_rows, grid_cols, 14)
        # Categorize time periods
        df_evolution['time_category'] = pd.cut(
            df_evolution['days_between'],
            bins=[0, 30, 90, 180, 365, float('inf')],
            labels=['<1 mes', '1-3 meses', '3-6 meses', '6-12 meses', '>12 meses']
        )
        time_avg_change = df_evolution.groupby('time_category')['score_change'].mean()
        colors_bar = ['#388e3c' if x > 0 else '#d32f2f' if x < 0 else '#ff9800' for x in time_avg_change.values]
        bars = ax14.bar(range(len(time_avg_change)), time_avg_change.values, color=colors_bar, alpha=0.7)
        ax14.set_xticks(range(len(time_avg_change)))
        ax14.set_xticklabels(time_avg_change.index, rotation=45, ha='right', fontsize=8)
        ax14.axhline(0, color='black', linestyle='-', linewidth=1)
        ax14.set_title('Cambio Promedio por Período', fontsize=11, fontweight='bold')
        ax14.set_ylabel('Cambio Promedio')
        ax14.grid(axis='y', alpha=0.3)
        # Add value labels
        for i, (bar, val) in enumerate(zip(bars, time_avg_change.values)):
            height = bar.get_height()
            ax14.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:+.2f}', ha='center', va='bottom' if val > 0 else 'top', fontsize=8)
        
        # 15. Evolution Summary Stats
        ax15 = plt.subplot(grid_rows, grid_cols, 15)
        ax15.axis('off')
        
        evo_stats = self.analysis_results['user_evolution_stats']
        summary_text = f"""
        EVOLUCIÓN DE USUARIOS
        
        👥 Usuarios múltiples: {evo_stats['total_users_tracked']}
        
        📊 Cambios:
        • Mejoraron: {evo_stats['improved']} ({evo_stats['improvement_rate']}%)
        • Empeoraron: {evo_stats['declined']} ({evo_stats['decline_rate']}%)
        • Sin cambio: {evo_stats['unchanged']}
        
        🎯 Significativos:
        • Mejora ≥3: {evo_stats['significant_improvement']}
        • Declive ≥3: {evo_stats['significant_decline']}
        
        📈 Promedio:
        • Cambio: {evo_stats['avg_score_change']:+.2f}
        • Días: {evo_stats['avg_days_between_responses']:.1f}
        """
        
        ax15.text(0.1, 0.9, summary_text, transform=ax15.transAxes, fontsize=9,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
        
        # 16. Source Files Info (if multiple files)
        ax16 = plt.subplot(grid_rows, grid_cols, 16)
        ax16.axis('off')
        
        if 'source_files' in self.analysis_results:
            source_info = self.analysis_results['source_files']
            source_text = f"""
        ARCHIVOS PROCESADOS
        
        📁 Total archivos: {source_info['total_files']}
        
        📊 Respuestas por archivo:"""
            for file_name, count in source_info['responses_per_file'].items():
                source_text += f"\n        • {file_name}: {count:,}"
            
            ax16.text(0.1, 0.9, source_text, transform=ax16.transAxes, fontsize=9,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
    
    def generate_executive_summary(self):
        """Generate an executive summary of NPS insights."""
        nps_metrics = self.analysis_results['nps_metrics']
        feedback_analysis = self.analysis_results.get('feedback_analysis', {})
        
        # Interpret NPS score
        nps_score = nps_metrics['nps_score']
        if nps_score >= 70:
            nps_interpretation = "Excelente - World Class"
        elif nps_score >= 50:
            nps_interpretation = "Muy Bueno"
        elif nps_score >= 30:
            nps_interpretation = "Bueno"
        elif nps_score >= 0:
            nps_interpretation = "Aceptable - Necesita Mejoras"
        else:
            nps_interpretation = "Crítico - Acción Inmediata Requerida"
        
        # Key insights
        insights = []
        
        if nps_metrics['detractor_percentage'] > 20:
            insights.append(f"🚨 Alto porcentaje de detractores ({nps_metrics['detractor_percentage']}%) - requiere atención inmediata")
        
        if nps_metrics['promoter_percentage'] < 40:
            insights.append(f"⚡ Oportunidad de crecimiento: solo {nps_metrics['promoter_percentage']}% son promotores")
        
        if nps_metrics['passive_percentage'] > 40:
            insights.append(f"💡 Gran oportunidad: {nps_metrics['passive_percentage']}% pasivos pueden convertirse en promotores")
        
        # Feedback insights
        if feedback_analysis.get('detractor_keywords'):
            top_issues = list(feedback_analysis['detractor_keywords'].keys())[:3]
            insights.append(f"🔍 Principales problemas reportados: {', '.join(top_issues)}")
        
        summary = {
            'nps_score': nps_score,
            'interpretation': nps_interpretation,
            'total_responses': nps_metrics['total_responses'],
            'key_insights': insights,
            'recommendations': self.generate_recommendations(nps_metrics, feedback_analysis),
            'analysis_date': datetime.now().isoformat(),
            'data_period': f"{self.df_deduplicated['received_at'].min()} to {self.df_deduplicated['received_at'].max()}",
            'source_files': self.analysis_results.get('source_files', {})
        }
        
        return summary
    
    def generate_recommendations(self, nps_metrics, feedback_analysis):
        """Generate actionable recommendations based on NPS analysis."""
        recommendations = []
        
        # Based on NPS score
        if nps_metrics['nps_score'] < 30:
            recommendations.append("🎯 Prioridad 1: Implementar programa de retención de clientes y mejora de experiencia")
        
        # Based on detractor percentage
        if nps_metrics['detractor_percentage'] > 15:
            recommendations.append("📞 Contactar detractores para entender problemas específicos y ofrecer soluciones")
        
        # Based on passive percentage
        if nps_metrics['passive_percentage'] > 30:
            recommendations.append("🚀 Programa de engagement para convertir clientes pasivos en promotores")
        
        # Based on feedback keywords
        if feedback_analysis.get('detractor_keywords'):
            top_issue = list(feedback_analysis['detractor_keywords'].keys())[0]
            recommendations.append(f"🔧 Abordar el problema principal: '{top_issue}' reportado frecuentemente")
        
        # General recommendations
        recommendations.append("📊 Implementar seguimiento mensual de NPS para monitorear tendencias")
        recommendations.append("💬 Establecer proceso de follow-up con todos los encuestados")
        
        return recommendations
    
    def export_results(self):
        """Export all analysis results to files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Export summary JSON
        summary = self.generate_executive_summary()
        summary_path = self.output_dir / f"nps_executive_summary_{timestamp}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        
        # Export full analysis results
        analysis_path = self.output_dir / f"nps_full_analysis_{timestamp}.json"
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(self.analysis_results, f, indent=2, ensure_ascii=False, default=str)
        
        # Export processed data
        data_path = self.output_dir / f"nps_processed_data_{timestamp}.csv"
        self.df_deduplicated.to_csv(data_path, index=False, encoding='utf-8')
        
        print(f"📄 Executive summary exported to: {summary_path}")
        print(f"📄 Full analysis exported to: {analysis_path}")
        print(f"📄 Processed data exported to: {data_path}")
        
        return summary_path, analysis_path, data_path
    
    def run_complete_analysis(self):
        """Run the complete NPS analysis pipeline."""
        print("🚀 Starting comprehensive NPS analysis...")
        print("=" * 60)
        
        # Load and clean data
        if not self.load_and_clean_data():
            return False
        
        # Calculate NPS metrics
        print("\n📊 Calculating NPS metrics...")
        self.calculate_nps_metrics()
        
        # Analyze temporal trends
        print("\n📈 Analyzing temporal trends...")
        self.analyze_temporal_trends()
        
        # Analyze feedback
        print("\n💬 Analyzing feedback...")
        self.analyze_feedback()
        
        # Analyze user evolution
        print("\n📈 Analyzing user evolution over time...")
        self.analyze_user_evolution()
        
        # Create visualizations
        print("\n📊 Creating visualizations...")
        self.create_visualizations()
        
        # Generate and export results
        print("\n📄 Generating executive summary...")
        summary = self.generate_executive_summary()
        
        # Export everything
        print("\n💾 Exporting results...")
        self.export_results()
        
        # Print executive summary
        print("\n" + "=" * 60)
        print("🎯 EXECUTIVE SUMMARY")
        print("=" * 60)
        print(f"NPS Score: {summary['nps_score']} ({summary['interpretation']})")
        print(f"Total Responses: {summary['total_responses']:,}")
        print(f"Analysis Period: {summary['data_period']}")
        
        print("\n🔍 Key Insights:")
        for insight in summary['key_insights']:
            print(f"  {insight}")
        
        print("\n💡 Recommendations:")
        for rec in summary['recommendations']:
            print(f"  {rec}")
        
        print("\n✅ Analysis complete!")
        return True

def main():
    """Main function to run NPS analysis from command line."""
    parser = argparse.ArgumentParser(
        description='Analyze NPS data from Intercom surveys',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file (backward compatible)
  python analyze_nps_data.py --file path/to/nps_file.csv
  
  # Multiple files
  python analyze_nps_data.py --files file1.csv file2.csv file3.csv
  
  # Multiple files with custom output directory
  python analyze_nps_data.py --files file1.csv file2.csv --output-dir outputs/custom/
        """
    )
    
    # Support both --file (single, backward compatible) and --files (multiple)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', '-f', help='Path to a single NPS CSV file (backward compatible)')
    group.add_argument('--files', nargs='+', help='Paths to one or more NPS CSV files')
    
    parser.add_argument('--output-dir', '-o', default='outputs/nps_analysis', 
                       help='Output directory for results (default: outputs/nps_analysis)')
    
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
    analyzer = NPSAnalyzer(file_paths, args.output_dir)
    success = analyzer.run_complete_analysis()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main()) 