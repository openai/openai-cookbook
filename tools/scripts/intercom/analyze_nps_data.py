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
    python analyze_nps_data.py --file path/to/nps_file.csv [--output-dir outputs/]
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
    def __init__(self, file_path, output_dir="outputs/nps_analysis"):
        """Initialize NPS Analyzer with file path and output directory."""
        self.file_path = file_path
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
        """Load and clean the NPS data."""
        print(f"🔄 Loading NPS data from: {self.file_path}")
        
        try:
            # Load CSV with proper encoding
            self.df = pd.read_csv(self.file_path, encoding='utf-8')
            
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
            
            print(f"✅ Loaded {final_count:,} complete NPS responses ({initial_count - final_count:,} incomplete removed)")
            
            # Identify duplicates
            self.identify_duplicates()
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading data: {str(e)}")
            return False
    
    def identify_duplicates(self):
        """Identify and handle duplicate responses."""
        # Check for duplicates based on email and date
        duplicates_by_email = self.df.groupby('email').size()
        duplicate_emails = duplicates_by_email[duplicates_by_email > 1]
        
        if len(duplicate_emails) > 0:
            print(f"⚠️  Found {len(duplicate_emails)} emails with multiple responses")
            
            # For analysis, keep the most recent response per email
            self.df_deduplicated = self.df.sort_values('received_at').groupby('email').tail(1)
            
            print(f"📊 After deduplication: {len(self.df_deduplicated):,} unique responses")
            
            # Store duplicate info for reporting
            self.analysis_results['duplicates'] = {
                'total_duplicate_emails': len(duplicate_emails),
                'total_responses_before': len(self.df),
                'total_responses_after': len(self.df_deduplicated)
            }
        else:
            self.df_deduplicated = self.df.copy()
            print("✅ No duplicates found")
    
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
        """Create comprehensive NPS visualizations."""
        df = self.df_deduplicated
        
        # Set up the plotting style
        plt.style.use('default')
        fig = plt.figure(figsize=(20, 16))
        
        # 1. NPS Distribution
        ax1 = plt.subplot(3, 3, 1)
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
        ax2 = plt.subplot(3, 3, 2)
        df['nps_category'] = df['nps_score'].apply(self.categorize_nps_score)
        category_counts = df['nps_category'].value_counts()
        colors_pie = ['#388e3c', '#ff9800', '#d32f2f']
        wedges, texts, autotexts = ax2.pie(category_counts.values, labels=category_counts.index, 
                                          autopct='%1.1f%%', colors=colors_pie, startangle=90)
        ax2.set_title('Categorías NPS', fontsize=14, fontweight='bold')
        
        # 3. Monthly Trend
        monthly_stats, weekly_stats = self.analyze_temporal_trends()
        if len(monthly_stats) > 1:
            ax3 = plt.subplot(3, 3, 3)
            months = [str(m) for m in monthly_stats.index]
            ax3.plot(months, monthly_stats['nps_score'], marker='o', linewidth=2, markersize=8)
            ax3.set_title('Evolución NPS Mensual', fontsize=14, fontweight='bold')
            ax3.set_xlabel('Mes')
            ax3.set_ylabel('NPS Score')
            ax3.grid(True, alpha=0.3)
            ax3.tick_params(axis='x', rotation=45)
        
        # 4. Response Volume Over Time
        ax4 = plt.subplot(3, 3, 4)
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
            ax5 = plt.subplot(3, 3, 5)
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
        ax6 = plt.subplot(3, 3, 6)
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
            ax7 = plt.subplot(3, 3, 7)
            df['hour'] = df['received_at'].dt.hour
            hourly_responses = df.groupby('hour').size()
            ax7.bar(hourly_responses.index, hourly_responses.values, alpha=0.7, color='lightcoral')
            ax7.set_title('Respuestas por Hora del Día', fontsize=14, fontweight='bold')
            ax7.set_xlabel('Hora')
            ax7.set_ylabel('Cantidad de Respuestas')
            ax7.grid(axis='y', alpha=0.3)
        
        # 8. Weekly Trend (Recent 8 weeks)
        if len(weekly_stats) > 1:
            ax8 = plt.subplot(3, 3, 8)
            weeks = [str(w) for w in weekly_stats.index]
            ax8.plot(weeks, weekly_stats['nps_score'], marker='s', linewidth=2, markersize=6, color='orange')
            ax8.set_title('Evolución NPS Semanal (Últimas 8 semanas)', fontsize=14, fontweight='bold')
            ax8.set_xlabel('Semana')
            ax8.set_ylabel('NPS Score')
            ax8.grid(True, alpha=0.3)
            ax8.tick_params(axis='x', rotation=45)
        
        # 9. Summary Stats Box
        ax9 = plt.subplot(3, 3, 9)
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
        
        ax9.text(0.1, 0.9, summary_text, transform=ax9.transAxes, fontsize=12,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
        
        plt.tight_layout()
        
        # Save the plot
        plot_path = self.output_dir / f"nps_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"📊 Visualizations saved to: {plot_path}")
        
        return plot_path
    
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
            'data_period': f"{self.df_deduplicated['received_at'].min()} to {self.df_deduplicated['received_at'].max()}"
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
    parser = argparse.ArgumentParser(description='Analyze NPS data from Intercom surveys')
    parser.add_argument('--file', '-f', required=True, help='Path to NPS CSV file')
    parser.add_argument('--output-dir', '-o', default='outputs/nps_analysis', 
                       help='Output directory for results (default: outputs/nps_analysis)')
    
    args = parser.parse_args()
    
    # Validate file exists
    if not os.path.exists(args.file):
        print(f"❌ Error: File not found: {args.file}")
        return 1
    
    # Run analysis
    analyzer = NPSAnalyzer(args.file, args.output_dir)
    success = analyzer.run_complete_analysis()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main()) 