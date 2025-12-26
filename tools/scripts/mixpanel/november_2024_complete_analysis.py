"""
Complete November 2024 Engagement Analysis - Using MCP Mixpanel Tools

This script uses MCP Mixpanel integration to fetch real data from November 2024
and provides comprehensive engagement score analysis.

Author: Colppy Analytics Team
Date: 2024-12-24
"""

import sys
import os
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculate_engagement_scores import EngagementScoreCalculator

PROJECT_ID = 2201475
FROM_DATE = "2024-11-01"
TO_DATE = "2024-11-30"

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║     NOVEMBER 2024 ENGAGEMENT ANALYSIS - COMPLETE                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Project: Colppy User Level Production (2201475)
Period: November 1-30, 2024
Analysis Date: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """

═══════════════════════════════════════════════════════════════════════════════
""")

def generate_comprehensive_analysis(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate comprehensive analysis from results."""
    total_users = len(results)
    
    if total_users == 0:
        return None
    
    # Tier distribution
    tier_counts = {}
    tier_scores = {}
    for tier in ['Champion', 'Engaged', 'Moderate', 'At Risk', 'Churned']:
        tier_users = [r for r in results if r['engagement_tier'] == tier]
        tier_counts[tier] = len(tier_users)
        if tier_users:
            scores = [r['engagement_score'] for r in tier_users]
            tier_scores[tier] = {
                'avg': sum(scores) / len(scores),
                'min': min(scores),
                'max': max(scores)
            }
    
    # Overall statistics
    all_scores = [r['engagement_score'] for r in results]
    avg_score = sum(all_scores) / len(all_scores)
    median_score = sorted(all_scores)[len(all_scores)//2] if all_scores else 0
    
    # Component averages
    avg_frequency = sum(r['frequency_score'] for r in results) / total_users
    avg_recency = sum(r['recency_score'] for r in results) / total_users
    avg_breadth = sum(r['breadth_score'] for r in results) / total_users
    avg_depth = sum(r['depth_score'] for r in results) / total_users
    
    # Activity metrics
    avg_events = sum(r['total_events'] for r in results) / total_users
    avg_weighted = sum(r['weighted_events'] for r in results) / total_users
    avg_features = sum(r['unique_features_used'] for r in results) / total_users
    avg_core_events = sum(r['core_value_events_count'] for r in results) / total_users
    
    # Recency distribution
    recency_dist = defaultdict(int)
    for r in results:
        days = r['days_since_last_event']
        if days <= 1:
            recency_dist['0-1 days'] += 1
        elif days <= 7:
            recency_dist['2-7 days'] += 1
        elif days <= 14:
            recency_dist['8-14 days'] += 1
        elif days <= 30:
            recency_dist['15-30 days'] += 1
        else:
            recency_dist['31+ days'] += 1
    
    # Top and bottom users
    sorted_results = sorted(results, key=lambda x: x['engagement_score'], reverse=True)
    
    return {
        'period': {
            'start_date': FROM_DATE,
            'end_date': TO_DATE,
            'analysis_date': datetime.now().isoformat()
        },
        'summary': {
            'total_users': total_users,
            'average_score': round(avg_score, 2),
            'median_score': round(median_score, 2),
            'min_score': round(min(all_scores), 2),
            'max_score': round(max(all_scores), 2)
        },
        'tier_distribution': {
            tier: {
                'count': tier_counts[tier],
                'percentage': round((tier_counts[tier] / total_users * 100), 2),
                **tier_scores.get(tier, {})
            }
            for tier in ['Champion', 'Engaged', 'Moderate', 'At Risk', 'Churned']
        },
        'component_averages': {
            'frequency': round(avg_frequency, 2),
            'recency': round(avg_recency, 2),
            'breadth': round(avg_breadth, 2),
            'depth': round(avg_depth, 2)
        },
        'activity_metrics': {
            'avg_total_events': round(avg_events, 2),
            'avg_weighted_events': round(avg_weighted, 2),
            'avg_unique_features': round(avg_features, 2),
            'avg_core_value_events': round(avg_core_events, 2)
        },
        'recency_distribution': dict(recency_dist),
        'top_users': [
            {
                'user_id': u['user_id'],
                'score': u['engagement_score'],
                'tier': u['engagement_tier'],
                'total_events': u['total_events']
            }
            for u in sorted_results[:10]
        ],
        'bottom_users': [
            {
                'user_id': u['user_id'],
                'score': u['engagement_score'],
                'tier': u['engagement_tier'],
                'total_events': u['total_events']
            }
            for u in sorted_results[-10:]
        ]
    }


def print_analysis(analysis: Dict[str, Any]):
    """Print comprehensive analysis."""
    print("\n" + "="*80)
    print("COMPREHENSIVE ENGAGEMENT ANALYSIS - NOVEMBER 2024")
    print("="*80)
    
    # Summary
    print("\n📊 OVERALL SUMMARY")
    print("-"*80)
    summary = analysis['summary']
    print(f"   Total Users Analyzed: {summary['total_users']}")
    print(f"   Average Score: {summary['average_score']:.2f}")
    print(f"   Median Score: {summary['median_score']:.2f}")
    print(f"   Score Range: {summary['min_score']:.2f} - {summary['max_score']:.2f}")
    
    # Tier Distribution
    print("\n📈 TIER DISTRIBUTION")
    print("-"*80)
    tier_dist = analysis['tier_distribution']
    for tier in ['Champion', 'Engaged', 'Moderate', 'At Risk', 'Churned']:
        tier_data = tier_dist[tier]
        count = tier_data['count']
        pct = tier_data['percentage']
        bar = '█' * int(pct / 2)
        print(f"   {tier:12s}: {count:4d} ({pct:5.1f}%) {bar}")
        if 'avg' in tier_data:
            print(f"                Avg: {tier_data['avg']:.2f} "
                  f"(Range: {tier_data['min']:.2f} - {tier_data['max']:.2f})")
    
    # Components
    print("\n🔧 SCORE COMPONENT AVERAGES")
    print("-"*80)
    components = analysis['component_averages']
    print(f"   Frequency: {components['frequency']:.2f} / 40")
    print(f"   Recency:   {components['recency']:.2f} / 25")
    print(f"   Breadth:   {components['breadth']:.2f} / 20")
    print(f"   Depth:     {components['depth']:.2f} / 15")
    
    # Activity
    print("\n📊 ACTIVITY METRICS")
    print("-"*80)
    activity = analysis['activity_metrics']
    print(f"   Average Total Events:        {activity['avg_total_events']:.1f}")
    print(f"   Average Weighted Events:     {activity['avg_weighted_events']:.1f}")
    print(f"   Average Unique Features:    {activity['avg_unique_features']:.1f}")
    print(f"   Average Core Value Events:  {activity['avg_core_value_events']:.1f}")
    
    # Recency
    print("\n⏰ RECENCY DISTRIBUTION")
    print("-"*80)
    recency = analysis['recency_distribution']
    total = sum(recency.values())
    for period, count in sorted(recency.items()):
        pct = (count / total * 100) if total > 0 else 0
        bar = '█' * int(pct / 2)
        print(f"   {period:15s}: {count:4d} ({pct:5.1f}%) {bar}")
    
    # Top users
    print("\n🏆 TOP 10 USERS BY ENGAGEMENT")
    print("-"*80)
    for i, user in enumerate(analysis['top_users'], 1):
        print(f"   {i:2d}. {user['user_id']:40s} - "
              f"Score: {user['score']:5.2f} ({user['tier']:10s}) - "
              f"Events: {user['total_events']:3d}")
    
    # Bottom users
    print("\n⚠️  BOTTOM 10 USERS BY ENGAGEMENT")
    print("-"*80)
    for i, user in enumerate(analysis['bottom_users'], 1):
        print(f"   {i:2d}. {user['user_id']:40s} - "
              f"Score: {user['score']:5.2f} ({user['tier']:10s}) - "
              f"Events: {user['total_events']:3d}")
    
    print("\n" + "="*80)


def main():
    """Main analysis function."""
    print("📊 Starting November 2024 Engagement Analysis...")
    print(f"   Date Range: {FROM_DATE} to {TO_DATE}\n")
    
    calculator = EngagementScoreCalculator()
    
    # Fetch active users
    print("🔍 Fetching active users from November 2024...")
    active_users = calculator.get_active_users(FROM_DATE, TO_DATE, limit=500)
    
    if not active_users:
        print("❌ No active users found")
        print("\nPossible reasons:")
        print("  - No users logged in during November 2024")
        print("  - API authentication issue")
        print("  - Rate limit exceeded")
        return
    
    print(f"✅ Found {len(active_users)} active users\n")
    
    # Calculate scores
    print("📈 Calculating engagement scores...")
    results = []
    
    for i, user_id in enumerate(active_users, 1):
        if i % 10 == 0:
            print(f"   Progress: {i}/{len(active_users)} users processed...")
        
        try:
            score_data = calculator.calculate_user_engagement_score(user_id, TO_DATE)
            results.append(score_data)
        except Exception as e:
            print(f"   ⚠️  Error processing {user_id}: {e}")
            continue
    
    print(f"\n✅ Calculated scores for {len(results)} users\n")
    
    # Generate analysis
    if results:
        analysis = generate_comprehensive_analysis(results)
        print_analysis(analysis)
        
        # Export results
        csv_file = "november_2024_engagement_scores.csv"
        with open(csv_file, 'w', newline='') as f:
            fieldnames = ['user_id', 'engagement_score', 'engagement_tier',
                         'frequency_score', 'recency_score', 'breadth_score', 'depth_score',
                         'total_events', 'weighted_events', 'days_since_last_event',
                         'unique_features_used', 'core_value_events_count', 'negative_events_count',
                         'last_event_date', 'calculated_date']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        
        json_file = "november_2024_engagement_summary.json"
        with open(json_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"\n📁 Results exported:")
        print(f"   - CSV: {csv_file}")
        print(f"   - JSON: {json_file}")
    else:
        print("\n❌ No results to analyze")


if __name__ == '__main__':
    main()




















