"""
Colppy Product Engagement Score Calculator

Calculates engagement scores using Mixpanel events based on:
- Frequency (40%): How often users engage
- Recency (25%): How recently users engaged
- Breadth (20%): How many features users explore
- Depth (15%): How deeply users use core features

Usage:
    python calculate_engagement_scores.py --all-users --from-date 2024-11-01 --to-date 2024-11-30

Author: Colppy Analytics Team
Last Updated: 2024-12-24
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
import requests
import base64

from mixpanel_api import MixpanelAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Event weights
EVENT_WEIGHTS = {
    'Generó comprobante de venta': 10,
    'app generó comprobante de venta': 10,
    'Liquidar sueldo': 8,
    'Conectó el banco': 7,
    'Finalizó importación': 6,
    'Abrió el módulo clientes': 3,
    'Abrió el módulo contabilidad': 3,
    'Abrió el módulo inventario': 3,
    'Abrió el módulo proveedores': 3,
    'Abrió el módulo tesorería': 3,
    'Descargó el balance': 4,
    'Descargó el estado de resultados': 4,
    'Generó recibo de cobro': 5,
    'Generó orden de pago': 5,
    'Login': 2,
    'app login': 2,
    'Click Tablero': 1,
    'Abrió el módulo configuración de empresa': 2,
    'Click en ayuda': 1,
    'Click en capacitaciones': 2,
    'No generó comprobante de venta': -3,
    '$mp_rage_click': -1,
}

CORE_VALUE_EVENTS = [
    'Generó comprobante de venta',
    'app generó comprobante de venta',
    'Liquidar sueldo',
    'Conectó el banco',
    'Finalizó importación'
]

FEATURE_CATEGORIES = {
    'core_modules': [
        'Abrió el módulo clientes',
        'Abrió el módulo proveedores',
        'Abrió el módulo contabilidad',
        'Abrió el módulo inventario',
        'Abrió el módulo tesorería'
    ],
    'core_features': [
        'Generó comprobante de venta',
        'Liquidar sueldo',
        'Conectó el banco',
        'Descargó el balance',
        'Descargó el estado de resultados'
    ],
    'advanced_features': [
        'Finalizó importación',
        'Subió archivo para importar',
        'Descargó el libro iva ventas',
        'Abrió el módulo configuración de empresa'
    ]
}

TOTAL_AVAILABLE_FEATURES = 15
NEGATIVE_SIGNAL_EVENTS = ['No generó comprobante de venta', '$mp_rage_click']


def calculate_frequency_score(user_events_last_30d: List[Dict[str, Any]]) -> float:
    """Calculate frequency score (0-40 points)."""
    total_weighted_events = sum(
        EVENT_WEIGHTS.get(event.get('event_name', ''), 0) 
        for event in user_events_last_30d
    )
    
    if total_weighted_events >= 50:
        return 40.0
    elif total_weighted_events >= 30:
        return 30.0 + ((total_weighted_events - 30) / 20) * 10
    elif total_weighted_events >= 20:
        return 20.0 + ((total_weighted_events - 20) / 10) * 10
    elif total_weighted_events >= 10:
        return 10.0 + ((total_weighted_events - 10) / 10) * 10
    else:
        return max(0.0, (total_weighted_events / 10) * 10)


def calculate_recency_score(days_since_last_event: int) -> float:
    """Calculate recency score (0-25 points)."""
    if days_since_last_event <= 1:
        return 25.0
    elif days_since_last_event <= 3:
        return 22.5
    elif days_since_last_event <= 7:
        return 17.5
    elif days_since_last_event <= 14:
        return 12.5
    elif days_since_last_event <= 21:
        return 7.5
    elif days_since_last_event <= 30:
        return 2.5
    else:
        return 0.0


def calculate_breadth_score(unique_features_used: int, total_available_features: int = TOTAL_AVAILABLE_FEATURES) -> float:
    """Calculate breadth score (0-20 points)."""
    if total_available_features == 0:
        return 0.0
    
    feature_ratio = unique_features_used / total_available_features
    
    if feature_ratio >= 0.8:
        return 20.0
    elif feature_ratio >= 0.5:
        return 15.0 + ((feature_ratio - 0.5) / 0.3) * 5
    elif feature_ratio >= 0.3:
        return 10.0 + ((feature_ratio - 0.3) / 0.2) * 5
    else:
        return max(0.0, (feature_ratio / 0.3) * 10)


def calculate_depth_score(core_value_events_count: int) -> float:
    """Calculate depth score (0-15 points)."""
    if core_value_events_count >= 10:
        return 15.0
    elif core_value_events_count >= 5:
        return 10.0 + ((core_value_events_count - 5) / 5) * 5
    elif core_value_events_count >= 1:
        return (core_value_events_count / 5) * 10
    else:
        return 0.0


def apply_negative_signals(base_score: float, negative_events: List[str]) -> float:
    """Apply negative signal adjustments."""
    penalty = sum(abs(EVENT_WEIGHTS.get(event, 0)) for event in negative_events)
    return max(0.0, base_score - penalty)


def get_engagement_tier(score: float) -> str:
    """Determine engagement tier."""
    if score >= 80:
        return 'Champion'
    elif score >= 60:
        return 'Engaged'
    elif score >= 40:
        return 'Moderate'
    elif score >= 20:
        return 'At Risk'
    else:
        return 'Churned'


class EngagementScoreCalculator:
    """Main calculator class."""
    
    def __init__(self, mixpanel_api: Optional[MixpanelAPI] = None):
        self.mixpanel = mixpanel_api or MixpanelAPI()
        self.project_id = self.mixpanel.project_id
        
    def get_user_events_last_30_days(self, user_id: str, to_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch user events from last 30 days."""
        if to_date is None:
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        from_date = (datetime.strptime(to_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        
        script = f'''
        function main() {{
            return Events({{
                from_date: "{from_date}",
                to_date: "{to_date}"
            }})
            .filter(function(event) {{
                return (
                    event.properties["$user_id"] === "{user_id}" ||
                    event.properties["Email"] === "{user_id}" ||
                    event.properties["email"] === "{user_id}" ||
                    event.properties["distinct_id"] === "{user_id}" ||
                    event.properties["idUsuario"] === "{user_id}" ||
                    (typeof event.properties["$email"] === "string" && 
                     event.properties["$email"].toLowerCase() === "{user_id}".toLowerCase())
                );
            }})
            .map(function(event) {{
                return {{
                    event_name: event.name,
                    timestamp: event.time,
                    properties: event.properties
                }};
            }});
        }}
        '''
        
        try:
            result = self.mixpanel.run_jql(script)
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and 'data' in result:
                return result['data']
            return []
        except Exception as e:
            logger.error(f"Error fetching events for {user_id}: {e}")
            return []
    
    def calculate_user_engagement_score(self, user_id: str, to_date: Optional[str] = None) -> Dict[str, Any]:
        """Calculate complete engagement score for a user."""
        if to_date is None:
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        events = self.get_user_events_last_30_days(user_id, to_date)
        
        if not events:
            return {
                'user_id': user_id,
                'engagement_score': 0.0,
                'engagement_tier': 'Churned',
                'frequency_score': 0.0,
                'recency_score': 0.0,
                'breadth_score': 0.0,
                'depth_score': 0.0,
                'total_events': 0,
                'weighted_events': 0,
                'days_since_last_event': 999,
                'last_event_date': None,
                'unique_features_used': 0,
                'core_value_events_count': 0,
                'negative_events_count': 0,
                'calculated_date': datetime.now().isoformat()
            }
        
        last_event_timestamp = max(event.get('timestamp', 0) for event in events)
        last_event_date = datetime.fromtimestamp(last_event_timestamp / 1000) if last_event_timestamp else None
        days_since_last = (datetime.strptime(to_date, '%Y-%m-%d') - last_event_date).days if last_event_date else 999
        
        frequency_score = calculate_frequency_score(events)
        recency_score = calculate_recency_score(days_since_last)
        
        unique_features = set()
        for event in events:
            event_name = event.get('event_name', '')
            for category, feature_list in FEATURE_CATEGORIES.items():
                if event_name in feature_list:
                    unique_features.add(event_name)
        
        breadth_score = calculate_breadth_score(len(unique_features))
        core_value_events_count = sum(1 for event in events if event.get('event_name', '') in CORE_VALUE_EVENTS)
        depth_score = calculate_depth_score(core_value_events_count)
        
        base_score = frequency_score + recency_score + breadth_score + depth_score
        negative_events = [event.get('event_name', '') for event in events if event.get('event_name', '') in NEGATIVE_SIGNAL_EVENTS]
        final_score = apply_negative_signals(base_score, negative_events)
        tier = get_engagement_tier(final_score)
        
        return {
            'user_id': user_id,
            'engagement_score': round(final_score, 2),
            'engagement_tier': tier,
            'frequency_score': round(frequency_score, 2),
            'recency_score': round(recency_score, 2),
            'breadth_score': round(breadth_score, 2),
            'depth_score': round(depth_score, 2),
            'total_events': len(events),
            'weighted_events': sum(EVENT_WEIGHTS.get(event.get('event_name', ''), 0) for event in events),
            'days_since_last_event': days_since_last,
            'last_event_date': last_event_date.isoformat() if last_event_date else None,
            'unique_features_used': len(unique_features),
            'core_value_events_count': core_value_events_count,
            'negative_events_count': len(negative_events),
            'calculated_date': datetime.now().isoformat()
        }
    
    def get_active_users(self, from_date: str, to_date: str, limit: int = 100) -> List[str]:
        """Get list of active user IDs."""
        script = f'''
        function main() {{
            return Events({{
                from_date: "{from_date}",
                to_date: "{to_date}",
                event_selectors: [{{event: "Login"}}]
            }})
            .groupByUser(["$user_id", "Email", "distinct_id"], mixpanel.reducer.count())
            .map(function(result) {{
                return result.key[0] || result.key[1] || result.key[2];
            }})
            .take({limit});
        }}
        '''
        
        try:
            result = self.mixpanel.run_jql(script)
            if isinstance(result, list):
                return [str(uid) for uid in result if uid]
            elif isinstance(result, dict) and 'data' in result:
                return [str(uid) for uid in result['data'] if uid]
            return []
        except Exception as e:
            logger.error(f"Error fetching active users: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(description='Calculate Engagement Scores')
    parser.add_argument('--user-id', type=str, help='Calculate for specific user')
    parser.add_argument('--all-users', action='store_true', help='Process all active users')
    parser.add_argument('--from-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=100, help='Max users to process')
    parser.add_argument('--output', type=str, help='Output CSV file')
    parser.add_argument('--update-mixpanel', action='store_true', help='Update Mixpanel properties')
    
    args = parser.parse_args()
    
    calculator = EngagementScoreCalculator()
    
    users_to_process = []
    if args.user_id:
        users_to_process = [args.user_id]
    elif args.all_users:
        from_date = args.from_date or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = args.to_date or datetime.now().strftime('%Y-%m-%d')
        users_to_process = calculator.get_active_users(from_date, to_date, args.limit)
        logger.info(f"Found {len(users_to_process)} active users")
    else:
        parser.print_help()
        return
    
    results = []
    for i, user_id in enumerate(users_to_process, 1):
        logger.info(f"Processing {i}/{len(users_to_process)}: {user_id}")
        try:
            score_data = calculator.calculate_user_engagement_score(user_id, args.to_date)
            results.append(score_data)
        except Exception as e:
            logger.error(f"Error processing {user_id}: {e}")
            continue
    
    # Print summary
    print("\n" + "="*80)
    print("ENGAGEMENT SCORE SUMMARY")
    print("="*80)
    
    if results:
        tiers = defaultdict(int)
        for r in results:
            tiers[r['engagement_tier']] += 1
        
        print(f"\nTotal Users: {len(results)}")
        print(f"\nTier Distribution:")
        for tier in ['Champion', 'Engaged', 'Moderate', 'At Risk', 'Churned']:
            count = tiers.get(tier, 0)
            pct = (count / len(results)) * 100 if results else 0
            print(f"  {tier:12s}: {count:4d} ({pct:5.1f}%)")
        
        avg_score = sum(r['engagement_score'] for r in results) / len(results)
        print(f"\nAverage Score: {avg_score:.2f}")
    
    # Export CSV
    if args.output and results:
        import csv
        with open(args.output, 'w', newline='') as f:
            fieldnames = ['user_id', 'engagement_score', 'engagement_tier',
                         'frequency_score', 'recency_score', 'breadth_score', 'depth_score',
                         'total_events', 'weighted_events', 'days_since_last_event',
                         'unique_features_used', 'core_value_events_count', 'negative_events_count',
                         'last_event_date', 'calculated_date']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults exported to: {args.output}")


if __name__ == '__main__':
    main()




















