#!/usr/bin/env python3
"""
Mixpanel Webhook Server for Zapier Integration
Exposes a webhook endpoint that runs Mixpanel JQL queries and returns CSV data.

Usage:
    python mixpanel_webhook_server.py
    
    Then configure Zapier webhook to POST to:
    http://your-server:5000/webhook/mixpanel-query
    
    Or use ngrok for local testing:
    ngrok http 5000
"""

import sys
import os
import json
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response

# Load environment variables
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

# Add parent directory to path to import mixpanel_api
sys.path.insert(0, str(script_dir))
from mixpanel_api import MixpanelAPI

app = Flask(__name__)

# Initialize Mixpanel API
mixpanel = MixpanelAPI()


def flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    """Flatten nested dictionary for CSV export."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert lists to comma-separated strings
            items.append((new_key, ', '.join(str(item) for item in v)))
        else:
            items.append((new_key, v))
    return dict(items)


def convert_to_csv(data: List[Dict], flatten: bool = True) -> str:
    """Convert Mixpanel query results to CSV format."""
    if not data:
        return ""
    
    # Flatten nested dictionaries if needed
    if flatten:
        flattened_data = [flatten_dict(item) for item in data]
    else:
        flattened_data = data
    
    # Get all unique keys from all records
    all_keys = set()
    for record in flattened_data:
        all_keys.update(record.keys())
    
    # Sort keys for consistent column order
    fieldnames = sorted(all_keys)
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for record in flattened_data:
        # Convert all values to strings, handle None
        clean_record = {
            k: str(v) if v is not None else '' 
            for k, v in record.items()
        }
        writer.writerow(clean_record)
    
    return output.getvalue()


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'mixpanel-webhook-server'
    })


@app.route('/webhook/mixpanel-query', methods=['POST', 'GET'])
def mixpanel_query_webhook():
    """
    Webhook endpoint for Zapier to trigger Mixpanel queries.
    
    Accepts:
    - POST with JSON body containing:
        {
            "jql_query": "function main() { ... }",
            "query_file": "path/to/query.jql",  # Alternative to jql_query
            "format": "csv" or "json",  # Default: csv
            "flatten": true  # Flatten nested objects (default: true)
        }
    - GET with query parameters (for simple testing)
    """
    try:
        # Get query from request
        if request.method == 'POST':
            data = request.get_json() or {}
            jql_query = data.get('jql_query')
            query_file = data.get('query_file')
            output_format = data.get('format', 'csv').lower()
            flatten = data.get('flatten', True)
        else:  # GET request
            jql_query = request.args.get('jql_query')
            query_file = request.args.get('query_file')
            output_format = request.args.get('format', 'csv').lower()
            flatten = request.args.get('flatten', 'true').lower() == 'true'
        
        # Get JQL query
        if query_file:
            query_path = script_dir / query_file
            if not query_path.exists():
                return jsonify({
                    'error': f'Query file not found: {query_file}'
                }), 404
            with open(query_path, 'r', encoding='utf-8') as f:
                jql_query = f.read()
        
        if not jql_query:
            return jsonify({
                'error': 'Missing jql_query parameter. Provide either jql_query or query_file.'
            }), 400
        
        # Run Mixpanel query
        print(f"[{datetime.now()}] Running Mixpanel query...")
        result = mixpanel.run_jql(jql_query)
        
        # Handle different result formats
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict):
            # Check if result has a 'data' key
            if 'data' in result:
                data = result['data']
            else:
                data = [result]
        else:
            data = [{'result': str(result)}]
        
        # Return in requested format
        if output_format == 'json':
            return jsonify({
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'record_count': len(data),
                'data': data
            })
        else:  # CSV format
            csv_data = convert_to_csv(data, flatten=flatten)
            
            # Return CSV as response
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=mixpanel_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                }
            )
    
    except Exception as e:
        print(f"[{datetime.now()}] Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/webhook/mixpanel-query/predefined', methods=['POST', 'GET'])
def predefined_query_webhook():
    """
    Webhook endpoint for predefined queries.
    
    Query types:
    - "12_users_2025": Query for the 12 users from the example
    - "finalizar_wizard_6h": Users who completed wizard in last 6 hours
    
    Usage:
        POST/GET with: {"query_type": "12_users_2025", "format": "csv"}
    """
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            query_type = data.get('query_type')
            output_format = data.get('format', 'csv').lower()
        else:
            query_type = request.args.get('query_type')
            output_format = request.args.get('format', 'csv').lower()
        
        if not query_type:
            return jsonify({
                'error': 'Missing query_type parameter',
                'available_types': ['12_users_2025', 'finalizar_wizard_6h']
            }), 400
        
        # Define predefined queries
        predefined_queries = {
            '12_users_2025': '''
function main() {
  var targetEmails = [
    "danielacarando@gmail.com",
    "fliagfernandez@gmail.com",
    "matiasfagundes777@gmail.com",
    "kevinnnmaldonadoo@gmail.com",
    "aquinopedacredaiaradahiana@gmail.com",
    "milagrose071@gmail.com",
    "melaroberto186@gmail.com",
    "estudiocontablekobiak@gmail.com",
    "santiagomrex@gmail.com",
    "jorge_v_78@hotmail.com",
    "aquinomaximoenrique@gmail.com",
    "munozjorgeeduardo0@gmail.com"
  ];
  
  return Events({
    from_date: "2025-01-01",
    to_date: "2025-12-08"
  })
  .filter(function(event) {
    if (event.name.indexOf("$") === 0) return false;
    var email = event.properties["Email"] || 
                event.properties["$email"] || 
                event.properties["email"] ||
                event.distinct_id;
    if (!email) return false;
    return targetEmails.indexOf(email.toLowerCase()) >= 0;
  })
  .groupBy(
    [function(event) {
      return event.properties["Email"] || 
             event.properties["$email"] || 
             event.properties["email"] ||
             event.distinct_id;
    }, "name"],
    mixpanel.reducer.count()
  )
  .map(function(result) {
    return {
      email: result.key[0],
      event_name: result.key[1],
      count: result.value
    };
  });
}
            ''',
            'finalizar_wizard_6h': '''
function main() {
  var sixHoursAgo = new Date().getTime() - (6 * 60 * 60 * 1000);
  var today = new Date().toISOString().split('T')[0];
  
  return Events({
    from_date: today,
    to_date: today
  })
  .filter(function(event) {
    return event.name === "Finalizar wizard" && 
           event.time >= sixHoursAgo;
  })
  .map(function(event) {
    return {
      distinct_id: event.distinct_id,
      time: new Date(event.time).toISOString(),
      email: event.properties["$email"] || event.properties["Email"] || event.properties["email"],
      user_id: event.properties["User_id"] || event.properties["$user_id"] || event.properties["idUsuario"],
      company_id: event.properties["idEmpresa"] || event.properties["company_id"] || event.properties["Company_id"],
      company_name: event.properties["Company Name"] || event.properties["Nombre de Empresa"],
      plan_type: event.properties["Tipo Plan Empresa"] || event.properties["tipo_plan_empresa"]
    };
  });
}
            '''
        }
        
        if query_type not in predefined_queries:
            return jsonify({
                'error': f'Unknown query_type: {query_type}',
                'available_types': list(predefined_queries.keys())
            }), 400
        
        jql_query = predefined_queries[query_type]
        
        # Run query
        print(f"[{datetime.now()}] Running predefined query: {query_type}")
        result = mixpanel.run_jql(jql_query)
        
        # Handle result format
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict) and 'data' in result:
            data = result['data']
        else:
            data = [result] if result else []
        
        # Return in requested format
        if output_format == 'json':
            return jsonify({
                'status': 'success',
                'query_type': query_type,
                'timestamp': datetime.now().isoformat(),
                'record_count': len(data),
                'data': data
            })
        else:  # CSV
            csv_data = convert_to_csv(data, flatten=True)
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=mixpanel_{query_type}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                }
            )
    
    except Exception as e:
        print(f"[{datetime.now()}] Error: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Mixpanel Webhook Server")
    print("=" * 60)
    print(f"📡 Webhook endpoints:")
    print(f"   POST/GET http://localhost:5000/webhook/mixpanel-query")
    print(f"   POST/GET http://localhost:5000/webhook/mixpanel-query/predefined")
    print(f"   GET http://localhost:5000/health")
    print("=" * 60)
    print("\n💡 For Zapier integration:")
    print("   1. Use ngrok: ngrok http 5000")
    print("   2. Configure Zapier webhook to POST to your ngrok URL")
    print("   3. Send JSON: {\"query_type\": \"12_users_2025\", \"format\": \"csv\"}")
    print("=" * 60)
    print()
    
    app.run(host='0.0.0.0', port=5000, debug=True)






