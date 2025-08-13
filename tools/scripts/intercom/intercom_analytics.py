#!/usr/bin/env python3
# Suppress urllib3 warnings about OpenSSL/LibreSSL
import warnings
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

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
import time
from tqdm import tqdm
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import threading
import itertools
warnings.filterwarnings('ignore')

# Load environment variables from .env file
load_dotenv()

# Intercom API configuration
INTERCOM_ACCESS_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
if not INTERCOM_ACCESS_TOKEN:
    raise ValueError("INTERCOM_ACCESS_TOKEN not found in environment variables.")

class IntercomAnalytics:
    def __init__(self, access_token, output_dir='intercom_reports'):
        self.access_token = access_token
        self.api_url = "https://api.intercom.io"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def _make_request(self, endpoint, method='GET', params=None, data=None, paginate=True):
        """Make request to Intercom API with pagination and rate limiting handling"""
        url = f"{self.api_url}/{endpoint}"
        all_data = []
        next_page = None
        max_attempts = 3  # Maximum retries per request
        timeout_seconds = 30  # Timeout for each individual request
        total_timeout = 300  # 5 minutes total timeout for all pagination 
        start_time = time.time()
        
        while True:
            # Check if total timeout exceeded
            if time.time() - start_time > total_timeout:
                print(f"[{time.strftime('%H:%M:%S')}] Total API request timeout of {total_timeout}s exceeded. Returning data collected so far.")
                return all_data
                
            # Initialize params if None
            if params is None:
                params = {}
                
            # Handle pagination
            if next_page:
                params['starting_after'] = next_page
            
            attempt = 0
            while attempt < max_attempts:
                try:
                    print(f"[{time.strftime('%H:%M:%S')}] API request to {endpoint} (attempt {attempt+1}/{max_attempts})")
                    if method == 'GET':
                        response = requests.get(url, headers=self.headers, params=params, timeout=timeout_seconds)
                    elif method == 'POST':
                        response = requests.post(url, headers=self.headers, json=data, timeout=timeout_seconds)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    response.raise_for_status()
                    response_data = response.json()
                    print(f"[{time.strftime('%H:%M:%S')}] API response received, status code: {response.status_code}")
                    
                    # Extract data based on response structure
                    if 'data' in response_data:
                        all_data.extend(response_data['data'])
                    else:
                        # Some endpoints don't return data in a 'data' field
                        all_data.append(response_data)
                    
                    # Handle pagination
                    if paginate and 'pages' in response_data and 'next' in response_data['pages']:
                        next_page = response_data['pages']['next']['starting_after']
                        print(f"[{time.strftime('%H:%M:%S')}] Pagination: next_page={next_page}")
                        # Add a small delay to respect rate limits
                        time.sleep(0.5)
                    else:
                        return all_data
                    
                    break  # Successful request, exit retry loop
                
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Rate limit exceeded
                        retry_after = int(e.response.headers.get('Retry-After', 10))
                        print(f"[{time.strftime('%H:%M:%S')}] Rate limit hit. Waiting for {retry_after} seconds...")
                        time.sleep(retry_after)
                        attempt += 1
                        continue
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] HTTP Error: {e}")
                        print(f"[{time.strftime('%H:%M:%S')}] Response content: {e.response.content}")
                        raise
                except requests.exceptions.Timeout:
                    print(f"[{time.strftime('%H:%M:%S')}] Request timeout after {timeout_seconds}s. Retrying ({attempt+1}/{max_attempts})...")
                    attempt += 1
                    if attempt >= max_attempts:
                        print(f"[{time.strftime('%H:%M:%S')}] Max retries reached. Returning data collected so far.")
                        return all_data
                except Exception as e:
                    print(f"[{time.strftime('%H:%M:%S')}] Error making request to {endpoint}: {str(e)}")
                    attempt += 1
                    if attempt >= max_attempts:
                        print(f"[{time.strftime('%H:%M:%S')}] Max retries reached. Returning data collected so far.")
                        return all_data
                    time.sleep(2 * attempt)  # Exponential backoff
        
        return all_data
    
    def get_team_members(self):
        """Get all team members/admins"""
        print("Fetching team members...")
        admins = self._make_request('admins')
        
        # Convert to DataFrame for analysis
        admin_data = []
        for admin in admins:
            admin_data.append({
                'id': admin.get('id'),
                'name': admin.get('name'),
                'email': admin.get('email'),
                'job_title': admin.get('job_title'),
                'has_inbox_seat': admin.get('has_inbox_seat', False),
                'team_ids': admin.get('team_ids', []),
                'away_mode_enabled': admin.get('away_mode_enabled', False),
                'away_mode_reassign': admin.get('away_mode_reassign', False)
            })
        
        admin_df = pd.DataFrame(admin_data)
        return admin_df
    
    def get_teams(self):
        """Get all teams from Intercom"""
        print("Fetching teams...")
        teams = self._make_request('teams')
        
        team_data = []
        for team in teams:
            # Handle None values for timestamps
            created_at = team.get('created_at')
            updated_at = team.get('updated_at')
            
            team_data.append({
                'id': team.get('id'),
                'name': team.get('name'),
                'admin_ids': team.get('admin_ids', []),
                'created_at': datetime.fromtimestamp(created_at) if created_at else None,
                'updated_at': datetime.fromtimestamp(updated_at) if updated_at else None
            })
        
        team_df = pd.DataFrame(team_data)
        return team_df
    
    def get_conversations(self, start_date=None, end_date=None, limit=None):
        """Get conversations within a date range"""
        # Add overall method timeout
        overall_timeout = 600  # 10 minutes total timeout for the entire method
        method_start_time = time.time()
        
        # Convert dates to Unix timestamps if provided
        params = {}
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            params['created_after'] = int(start_date.timestamp())
        
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            params['created_before'] = int(end_date.timestamp())
        
        print(f"Fetching conversations{' from ' + start_date.strftime('%Y-%m-%d') if start_date else ''}{' to ' + end_date.strftime('%Y-%m-%d') if end_date else ''}...")
        
        # If limit is provided, adjust pagination
        if limit:
            params['per_page'] = min(limit, 50)  # Intercom typically limits to 50 per page
            paginate = limit > 50
        else:
            params['per_page'] = 50
            paginate = True
        
        # Make the API request with progress feedback
        conversations = []
        total_estimated = None
        fetched = 0
        start_time = time.time()
        
        def heartbeat_indicator():
            """Print a heartbeat indicator to show the script is running"""
            spinner = itertools.cycle(['-', '\\', '|', '/'])
            while not heartbeat_stop_event.is_set():
                elapsed = time.time() - start_time
                # Also check the overall method timeout
                if time.time() - method_start_time > overall_timeout:
                    print(f"\r[{time.strftime('%H:%M:%S')}] WARNING: Operation taking too long ({int(elapsed)}s). Consider canceling with Ctrl+C", end="", flush=True)
                else:
                    print(f"\r[{time.strftime('%H:%M:%S')}] Script running... {next(spinner)} (elapsed: {int(elapsed)}s)", end="", flush=True)
                time.sleep(1)
        
        # Start heartbeat indicator in a separate thread
        heartbeat_stop_event = threading.Event()
        heartbeat_thread = threading.Thread(target=heartbeat_indicator)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()
        
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Fetching conversations from Intercom API...")
            with tqdm(desc=f"Fetching conversations", unit='conv', total=total_estimated) as fetch_bar:
                # Check if we've exceeded the overall timeout
                if time.time() - method_start_time > overall_timeout:
                    print(f"[{time.strftime('%H:%M:%S')}] Overall timeout of {overall_timeout}s exceeded. Returning data collected so far.")
                    heartbeat_stop_event.set()
                    heartbeat_thread.join(timeout=0.5)
                    return pd.DataFrame()
                    
                api_data = self._make_request('conversations', params=params, paginate=paginate)
                
                # Stop the heartbeat indicator as we now have data
                heartbeat_stop_event.set()
                heartbeat_thread.join(timeout=0.5)
                
                if isinstance(api_data, dict):
                    if 'conversations' in api_data:
                        conversations = api_data['conversations']
                        fetch_bar.update(len(conversations))
                        elapsed = time.time() - start_time
                        print(f"[{time.strftime('%H:%M:%S')}] Fetched {len(conversations)} conversations in {elapsed:.2f}s")
                    else:
                        conversations = []
                elif isinstance(api_data, list):
                    # If paginated, update bar as we go
                    for idx in range(0, len(api_data), 50):
                        batch = api_data[idx:idx+50]
                        conversations.extend(batch)
                        fetch_bar.update(len(batch))
                        elapsed = time.time() - start_time
                        if (idx + 50) % 200 == 0 or idx + 50 >= len(api_data):
                            print(f"[{time.strftime('%H:%M:%S')}] Fetched {len(conversations)} conversations in {elapsed:.2f}s")
                else:
                    conversations = []
                    
                total_elapsed = time.time() - start_time
                print(f"[{time.strftime('%H:%M:%S')}] Completed fetching {len(conversations)} conversations in {total_elapsed:.2f}s")
        except Exception as e:
            # Make sure to stop the heartbeat thread if there's an exception
            heartbeat_stop_event.set()
            if heartbeat_thread.is_alive():
                heartbeat_thread.join(timeout=0.5)
            print(f"[{time.strftime('%H:%M:%S')}] Error during conversation fetching: {str(e)}")
            return pd.DataFrame()
        
        # Handle different types of responses
        if isinstance(conversations, dict):
            if 'conversations' in conversations:
                conversations = conversations['conversations']
                print(f"Found conversations array in response with {len(conversations)} items")
                print(f"First conversation: {conversations[0]['id'] if conversations and isinstance(conversations[0], dict) and 'id' in conversations[0] else 'No ID found'}")
            else:
                print(f"Conversation list not found in API response. Keys: {conversations.keys()}")
                conversations = []
        elif isinstance(conversations, list):
            print(f"API response is a list with {len(conversations)} items")
            # Periodic feedback during fetching
            for idx in range(0, len(conversations), 50):
                print(f"Fetched {min(idx+50, len(conversations))} conversations so far...")
        else:
            print(f"Unexpected API response type: {type(conversations)}")
            conversations = []
            
        # Handle missing conversations array
        if not conversations:
            print("No conversations found in API response")
            return pd.DataFrame()
        
        # Limit the number of conversations if specified
        if limit and len(conversations) > limit:
            conversations = conversations[:limit]
        
        # Process conversations
        conversation_data = []
        total_to_process = len(conversations)
        for i, conv in enumerate(tqdm(conversations, desc='Processing conversations', unit='conv', total=total_to_process)):
            try:
                # Skip if the conv is not a dict
                if not isinstance(conv, dict):
                    print(f"Conversation {i} is not a dict: {type(conv)}")
                    continue
                # Check if this is the conversations object itself instead of an item
                if 'conversations' in conv and isinstance(conv['conversations'], list):
                    print(f"Found nested conversations list in item {i}. Processing those conversations instead.")
                    nested_conversations = conv['conversations']
                    for nested_conv in nested_conversations:
                        if isinstance(nested_conv, dict) and 'id' in nested_conv:
                            print(f"Processing nested conversation with ID: {nested_conv['id']}")
                            # Process nested conversation and add to data
                            conversations.append(nested_conv)
                    continue
                # Fetch conversation ID
                if 'id' not in conv:
                    print(f"No ID in conversation {i}. Keys: {conv.keys()}")
                    continue
                conv_id = conv['id']
                # Extract timestamps
                created_at_timestamp = conv.get('created_at')
                updated_at_timestamp = conv.get('updated_at')
                # Process the conversation details
                conversation = {
                    'id': conv_id,
                    'created_at': datetime.fromtimestamp(float(created_at_timestamp)) if created_at_timestamp is not None else None,
                    'updated_at': datetime.fromtimestamp(float(updated_at_timestamp)) if updated_at_timestamp is not None else None,
                    'state': conv.get('state'),
                    'read': conv.get('read', False),
                    'priority': conv.get('priority', 'normal'),
                    'rating': None,
                    'rating_remark': None,
                    'admin_assignee_id': conv.get('admin_assignee_id'),
                    'team_assignee_id': conv.get('team_assignee_id'),
                    'source': conv.get('source', {}).get('type', ''),
                    'message_count': 0,
                    'first_response_time': None,
                    'tags': []
                }
                # Extract statistics if available
                stats = conv.get('statistics', {})
                if stats:
                    conversation['first_response_time'] = stats.get('median_time_to_reply')
                    conversation['message_count'] = stats.get('count_conversation_parts', 0) + 1  # +1 for the initial message
                # Extract tags if available
                tags = conv.get('tags', {}).get('tags', [])
                conversation['tags'] = [tag.get('name') for tag in tags if isinstance(tag, dict) and 'name' in tag]
                # Extract SLA if available
                sla = conv.get('sla_applied')
                if sla:
                    conversation['sla_status'] = sla.get('status')
                    sla_timestamp = sla.get('sla_status_updated_timestamp')
                    if sla_timestamp:
                        conversation['sla_applied_at'] = datetime.fromtimestamp(float(sla_timestamp)) if sla_timestamp is not None else None
                # Extract rating if available
                rating = conv.get('conversation_rating')
                if rating:
                    conversation['rating'] = rating.get('rating')
                    conversation['rating_remark'] = rating.get('remark')
                conversation_data.append(conversation)
            except Exception as e:
                print(f"Error processing conversation: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if not conversation_data:
            print("No valid conversations found")
            return pd.DataFrame()
        
        conversation_df = pd.DataFrame(conversation_data)
        print(f"Successfully processed {len(conversation_df)} conversations")
        return conversation_df

    def get_satisfaction_metrics(self, start_date=None, end_date=None):
        """Get CSAT metrics"""
        print("Fetching CSAT metrics...")
        params = {}
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            params['from'] = int(start_date.timestamp())
        
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
            params['to'] = int(end_date.timestamp())
        
        csat_metrics = self._make_request('conversations/satisfaction', params=params, paginate=False)
        
        # Process CSAT data
        csat_data = []
        for metric in csat_metrics:
            csat_data.append({
                'date': datetime.fromtimestamp(metric.get('date')).strftime('%Y-%m-%d'),
                'total_responses': metric.get('total_responses'),
                'satisfied_responses': metric.get('satisfied_responses'),
                'neutral_responses': metric.get('neutral_responses'),
                'dissatisfied_responses': metric.get('dissatisfied_responses'),
                'satisfaction_score': metric.get('satisfaction_score')
            })
        
        csat_df = pd.DataFrame(csat_data)
        return csat_df
    
    def get_team_performance(self, conversations_df, admin_df, team_df):
        """Calculate team performance metrics from conversations data"""
        print("Analyzing team performance...")
        
        # Check if conversations dataframe is empty
        if conversations_df.empty:
            print("No conversations data available for team performance analysis")
            # Return empty dataframes
            admin_metrics = pd.DataFrame(columns=[
                'admin_name', 'total_conversations', 'median_response_time', 
                'average_rating', 'hours_since_last_update', 'csat_percentage'
            ])
            team_metrics = pd.DataFrame(columns=[
                'team_name', 'total_conversations', 'median_response_time', 
                'average_rating', 'csat_percentage'
            ])
            return admin_metrics, team_metrics
            
        # Check if required columns exist
        required_columns = ['id', 'admin_assignee_id', 'team_assignee_id', 'updated_at']
        for col in required_columns:
            if col not in conversations_df.columns:
                print(f"Required column '{col}' not found in conversations data")
                # Return empty dataframes
                admin_metrics = pd.DataFrame(columns=[
                    'admin_name', 'total_conversations', 'median_response_time', 
                    'average_rating', 'hours_since_last_update', 'csat_percentage'
                ])
                team_metrics = pd.DataFrame(columns=[
                    'team_name', 'total_conversations', 'median_response_time', 
                    'average_rating', 'csat_percentage'
                ])
                return admin_metrics, team_metrics
        
        # Convert ID columns to strings to avoid type issues
        conversations_df = conversations_df.copy()
        admin_df = admin_df.copy()
        team_df = team_df.copy()
        
        # Convert ID columns to strings
        if 'admin_assignee_id' in conversations_df.columns:
            conversations_df['admin_assignee_id'] = conversations_df['admin_assignee_id'].astype(str)
        if 'team_assignee_id' in conversations_df.columns:
            conversations_df['team_assignee_id'] = conversations_df['team_assignee_id'].astype(str)
        if 'id' in admin_df.columns:
            admin_df['id'] = admin_df['id'].astype(str)
        if 'id' in team_df.columns:
            team_df['id'] = team_df['id'].astype(str)
        
        # Join admin and team data
        performance_df = conversations_df.copy()
        
        # Only merge if we have both dataframes with required columns
        if not admin_df.empty and 'id' in admin_df.columns and 'name' in admin_df.columns:
            performance_df = performance_df.merge(
                admin_df[['id', 'name']], 
                left_on='admin_assignee_id', 
                right_on='id', 
                how='left', 
                suffixes=('', '_admin')
            )
            performance_df.rename(columns={'name': 'admin_name'}, inplace=True)
        else:
            print("Admin data missing or incomplete")
            performance_df['admin_name'] = 'Unknown'
            
        if not team_df.empty and 'id' in team_df.columns and 'name' in team_df.columns:
            performance_df = performance_df.merge(
                team_df[['id', 'name']], 
                left_on='team_assignee_id', 
                right_on='id', 
                how='left', 
                suffixes=('', '_team')
            )
            performance_df.rename(columns={'name': 'team_name'}, inplace=True)
        else:
            print("Team data missing or incomplete")
            performance_df['team_name'] = 'Unknown'
        
        # Create empty result dataframes
        admin_metrics = pd.DataFrame(columns=[
            'admin_name', 'total_conversations', 'median_response_time', 
            'average_rating', 'hours_since_last_update', 'csat_percentage'
        ])
        
        team_metrics = pd.DataFrame(columns=[
            'team_name', 'total_conversations', 'median_response_time', 
            'average_rating', 'csat_percentage'
        ])
        
        # Check if admin_name and team_name columns exist
        if 'admin_name' not in performance_df.columns or performance_df['admin_name'].isna().all():
            print("No valid admin names in data")
            return admin_metrics, team_metrics
            
        if 'team_name' not in performance_df.columns or performance_df['team_name'].isna().all():
            print("No valid team names in data")
            return admin_metrics, team_metrics
            
        # Fill missing values for calculations
        for col in ['first_response_time', 'rating']:
            if col not in performance_df.columns:
                performance_df[col] = np.nan
        
        # Calculate admin metrics
        admin_stats = []
        for admin_name, group in performance_df.groupby('admin_name'):
            if admin_name is None or pd.isna(admin_name):
                continue
                
            # Skip if admin name is empty
            if not admin_name:
                continue
                
            total_convs = len(group)
            med_resp_time = group['first_response_time'].median() if 'first_response_time' in group.columns else np.nan
            avg_rating = group['rating'].mean() if 'rating' in group.columns else np.nan
            
            # Calculate hours since last update
            try:
                if 'updated_at' in group.columns and not group['updated_at'].isna().all():
                    max_update = group['updated_at'].max()
                    if max_update is not None:
                        hours_since = (datetime.now() - max_update).total_seconds() / 3600
                    else:
                        hours_since = np.nan
                else:
                    hours_since = np.nan
            except Exception as e:
                print(f"Error calculating hours since update: {e}")
                hours_since = np.nan
        
            # Calculate CSAT percentage
            try:
                if 'rating' in group.columns and not group['rating'].isna().all():
                    ratings = group['rating'].dropna()
                    if len(ratings) > 0:
                        csat = (ratings >= 4).sum() / len(ratings) * 100
                    else:
                        csat = np.nan
                else:
                    csat = np.nan
            except Exception as e:
                print(f"Error calculating CSAT: {e}")
                csat = np.nan
            
            admin_stats.append({
                'admin_name': admin_name,
                'total_conversations': total_convs,
                'median_response_time': med_resp_time,
                'average_rating': avg_rating,
                'hours_since_last_update': hours_since,
                'csat_percentage': csat
            })
        
        # Create admin metrics DataFrame
        if admin_stats:
            admin_metrics = pd.DataFrame(admin_stats)
        
        # Calculate team metrics
        team_stats = []
        for team_name, group in performance_df.groupby('team_name'):
            if team_name is None or pd.isna(team_name):
                continue
                
            # Skip if team name is empty
            if not team_name:
                continue
                
            total_convs = len(group)
            med_resp_time = group['first_response_time'].median() if 'first_response_time' in group.columns else np.nan
            avg_rating = group['rating'].mean() if 'rating' in group.columns else np.nan
        
            # Calculate CSAT percentage
            try:
                if 'rating' in group.columns and not group['rating'].isna().all():
                    ratings = group['rating'].dropna()
                    if len(ratings) > 0:
                        csat = (ratings >= 4).sum() / len(ratings) * 100
                    else:
                        csat = np.nan
                else:
                    csat = np.nan
            except Exception as e:
                print(f"Error calculating CSAT: {e}")
                csat = np.nan
            
            team_stats.append({
                'team_name': team_name,
                'total_conversations': total_convs,
                'median_response_time': med_resp_time,
                'average_rating': avg_rating,
                'csat_percentage': csat
            })
        
        # Create team metrics DataFrame
        if team_stats:
            team_metrics = pd.DataFrame(team_stats)
        
        return admin_metrics, team_metrics
    
    def analyze_conversation_topics(self, conversations_df, n_clusters=8):
        """Analyze conversation topics using clustering"""
        print("Analyzing conversation topics...")
        # For this analysis, we'd need the actual conversation content
        # In a real implementation, you would fetch conversation parts
        # Here we'll simulate with just a basic structure
        
        # This is a placeholder - in a real implementation, you'd fetch and process conversation content
        if 'content' not in conversations_df.columns:
            print("No conversation content available for topic analysis")
            return None
        
        # Ensure we have content to analyze
        conversations_with_content = conversations_df[conversations_df['content'].notna()]
        
        if len(conversations_with_content) == 0:
            print("No conversation content available for topic analysis")
            return None
        
        # Vectorize the content
        vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        X = vectorizer.fit_transform(conversations_with_content['content'])
        
        # Cluster conversations
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        clusters = kmeans.fit_predict(X)
        
        # Get top terms for each cluster
        feature_names = vectorizer.get_feature_names_out()
        cluster_centers = kmeans.cluster_centers_
        
        cluster_keywords = {}
        for i in range(n_clusters):
            # Get top 10 keywords for this cluster
            order_centroids = cluster_centers[i].argsort()[::-1]
            keywords = [feature_names[idx] for idx in order_centroids[:10]]
            cluster_keywords[i] = keywords
        
        # Add cluster labels to conversations
        cluster_df = conversations_with_content.copy()
        cluster_df['cluster'] = clusters
        
        return cluster_df, cluster_keywords
    
    def analyze_response_times(self, conversations_df, admin_metrics=None, team_metrics=None):
        """Analyze response times"""
        print("Analyzing response times...")
        
        # Check if conversations_df is empty
        if conversations_df.empty:
            print("No conversation data available for response time analysis")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            
        # Create a copy to avoid modifying the original
        response_time_df = conversations_df.copy()
        
        # Check if admin_name and team_name columns exist
        if 'admin_name' not in response_time_df.columns and admin_metrics is not None:
            # Join with admin metrics to get admin names
            if 'admin_assignee_id' in response_time_df.columns and not admin_metrics.empty:
                admin_name_mapping = admin_metrics[['id', 'admin_name']].rename(columns={'id': 'admin_assignee_id'})
                response_time_df = response_time_df.merge(admin_name_mapping, on='admin_assignee_id', how='left')
            else:
                print("Cannot add admin_name: missing required columns")
                
        if 'team_name' not in response_time_df.columns and team_metrics is not None:
            # Join with team metrics to get team names
            if 'team_assignee_id' in response_time_df.columns and not team_metrics.empty:
                team_name_mapping = team_metrics[['id', 'team_name']].rename(columns={'id': 'team_assignee_id'})
                response_time_df = response_time_df.merge(team_name_mapping, on='team_assignee_id', how='left')
            else:
                print("Cannot add team_name: missing required columns")
        
        # Check again after potential merges
        if ('admin_name' not in response_time_df.columns or response_time_df['admin_name'].isna().all()) and \
           ('team_name' not in response_time_df.columns or response_time_df['team_name'].isna().all()):
            print("Missing admin or team name data.")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Filter conversations with response time data
        if 'first_response_time' not in response_time_df.columns or response_time_df['first_response_time'].isna().all():
            print("No response time data available")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            
        response_time_df = response_time_df[response_time_df['first_response_time'].notna()].copy()
        
        if len(response_time_df) == 0:
            print("No response time data available after filtering")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Convert response time to minutes
        response_time_df['response_time_minutes'] = response_time_df['first_response_time'] / 60
        
        # Calculate stats by team and admin (filter out missing names)
        admin_response_df = response_time_df[response_time_df['admin_name'].notna()] if 'admin_name' in response_time_df.columns else pd.DataFrame()
        team_response_df = response_time_df[response_time_df['team_name'].notna()] if 'team_name' in response_time_df.columns else pd.DataFrame()
        
        admin_response_times = pd.DataFrame()
        if not admin_response_df.empty and 'admin_name' in admin_response_df.columns:
            admin_response_times = admin_response_df.groupby('admin_name').agg({
                'response_time_minutes': ['mean', 'median', 'min', 'max', 'count']
            }).reset_index()
            
            admin_response_times.columns = ['admin_name', 'mean_response_time', 'median_response_time', 
                                            'min_response_time', 'max_response_time', 'conversation_count']
        else:
            print("No admin response time data available")
        
        team_response_times = pd.DataFrame()
        if not team_response_df.empty and 'team_name' in team_response_df.columns:
            team_response_times = team_response_df.groupby('team_name').agg({
                'response_time_minutes': ['mean', 'median', 'min', 'max', 'count']
            }).reset_index()
            
            team_response_times.columns = ['team_name', 'mean_response_time', 'median_response_time', 
                                          'min_response_time', 'max_response_time', 'conversation_count']
        else:
            print("No team response time data available")
        
        # Calculate response time distribution by hour of day
        hourly_response_times = pd.DataFrame()
        if 'created_at' in response_time_df.columns:
            response_time_df['hour_of_day'] = response_time_df['created_at'].dt.hour
            hourly_response_times = response_time_df.groupby('hour_of_day').agg({
                'response_time_minutes': ['mean', 'median', 'count']
            }).reset_index()
        
            hourly_response_times.columns = ['hour_of_day', 'mean_response_time', 
                                            'median_response_time', 'conversation_count']
        else:
            print("No created_at timestamp data available for hourly analysis")
        
        return admin_response_times, team_response_times, hourly_response_times
    
    def visualize_team_performance(self, admin_metrics, team_metrics, output_dir=None):
        """Visualize team performance metrics"""
        if output_dir is None:
            output_dir = self.output_dir
            
        os.makedirs(output_dir, exist_ok=True)
        
        # Skip visualization if data is missing
        if admin_metrics is None and team_metrics is None:
            print("No team performance data available for visualization")
            return
        
        # Admin performance visualization
        if admin_metrics is not None and not admin_metrics.empty:
            # Admin response time visualization
            if 'median_response_time' in admin_metrics.columns:
                plt.figure(figsize=(14, 8))
                admin_sorted = admin_metrics.sort_values('median_response_time')
                plt.bar(admin_sorted['admin_name'], admin_sorted['median_response_time'] / 60)  # Convert to minutes
                plt.xticks(rotation=45, ha='right')
                plt.xlabel('Admin')
                plt.ylabel('Median Response Time (minutes)')
                plt.title('Admin Response Times')
                plt.tight_layout()
                plt.savefig(os.path.join(output_dir, 'admin_response_times.png'))
                plt.close()
            
            # Admin CSAT visualization
            if 'csat_percentage' in admin_metrics.columns:
                plt.figure(figsize=(14, 8))
                admin_sorted = admin_metrics.sort_values('csat_percentage', ascending=False)
                plt.bar(admin_sorted['admin_name'], admin_sorted['csat_percentage'])
                plt.xticks(rotation=45, ha='right')
                plt.xlabel('Admin')
                plt.ylabel('CSAT Percentage')
                plt.title('Admin CSAT Percentages')
                plt.axhline(y=admin_sorted['csat_percentage'].mean(), color='r', linestyle='-', label='Average')
                plt.legend()
                plt.tight_layout()
                plt.savefig(os.path.join(output_dir, 'admin_csat.png'))
                plt.close()
            
            # Save admin metrics to CSV
            admin_metrics.to_csv(os.path.join(output_dir, 'admin_metrics.csv'), index=False)
        
        # Team performance visualization
        if team_metrics is not None and not team_metrics.empty:
            # Team response time visualization
            if 'median_response_time' in team_metrics.columns:
                plt.figure(figsize=(14, 8))
                team_sorted = team_metrics.sort_values('median_response_time')
                plt.bar(team_sorted['team_name'], team_sorted['median_response_time'] / 60)  # Convert to minutes
                plt.xticks(rotation=45, ha='right')
                plt.xlabel('Team')
                plt.ylabel('Median Response Time (minutes)')
                plt.title('Team Response Times')
                plt.tight_layout()
                plt.savefig(os.path.join(output_dir, 'team_response_times.png'))
                plt.close()
            
            # Team CSAT visualization
            if 'csat_percentage' in team_metrics.columns:
                plt.figure(figsize=(14, 8))
                team_sorted = team_metrics.sort_values('csat_percentage', ascending=False)
                plt.bar(team_sorted['team_name'], team_sorted['csat_percentage'])
                plt.xticks(rotation=45, ha='right')
                plt.xlabel('Team')
                plt.ylabel('CSAT Percentage')
                plt.title('Team CSAT Percentages')
                plt.axhline(y=team_sorted['csat_percentage'].mean(), color='r', linestyle='-', label='Average')
                plt.legend()
                plt.tight_layout()
                plt.savefig(os.path.join(output_dir, 'team_csat.png'))
                plt.close()
            
            # Save team metrics to CSV
            team_metrics.to_csv(os.path.join(output_dir, 'team_metrics.csv'), index=False)
    
    def visualize_response_time_analysis(self, admin_response_times, team_response_times, hourly_response_times, output_dir=None):
        """Visualize response time analysis"""
        if output_dir is None:
            output_dir = self.output_dir
            
        os.makedirs(output_dir, exist_ok=True)
        
        # Skip visualization if all data is None
        if admin_response_times is None and team_response_times is None and hourly_response_times is None:
            print("No response time data available for visualization")
            return
        
        # Admin response time distribution
        if admin_response_times is not None and not admin_response_times.empty:
            plt.figure(figsize=(14, 8))
            admin_sorted = admin_response_times.sort_values('median_response_time')
            sns.barplot(x='admin_name', y='median_response_time', data=admin_sorted)
            plt.xticks(rotation=45, ha='right')
            plt.xlabel('Admin')
            plt.ylabel('Median Response Time (minutes)')
            plt.title('Admin Response Time Distribution')
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'admin_response_distribution.png'))
            plt.close()
            
            # Save admin response time data to CSV
            admin_response_times.to_csv(os.path.join(output_dir, 'admin_response_times.csv'), index=False)
        
        # Team response time distribution
        if team_response_times is not None and not team_response_times.empty:
            plt.figure(figsize=(14, 8))
            team_sorted = team_response_times.sort_values('median_response_time')
            sns.barplot(x='team_name', y='median_response_time', data=team_sorted)
            plt.xticks(rotation=45, ha='right')
            plt.xlabel('Team')
            plt.ylabel('Median Response Time (minutes)')
            plt.title('Team Response Time Distribution')
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'team_response_distribution.png'))
            plt.close()
            
            # Save team response time data to CSV
            team_response_times.to_csv(os.path.join(output_dir, 'team_response_times.csv'), index=False)
        
        # Hourly response time distribution
        if hourly_response_times is not None and not hourly_response_times.empty:
            plt.figure(figsize=(14, 8))
            sns.lineplot(x='hour_of_day', y='median_response_time', data=hourly_response_times, marker='o')
            plt.xticks(range(24))
            plt.xlabel('Hour of Day')
            plt.ylabel('Median Response Time (minutes)')
            plt.title('Response Time by Hour of Day')
            plt.grid(True)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'hourly_response_times.png'))
            plt.close()
            
            # Save hourly response time data to CSV
            hourly_response_times.to_csv(os.path.join(output_dir, 'hourly_response_times.csv'), index=False)
    
    def visualize_conversation_metrics(self, conversation_metrics, volume_over_time, first_response_times, resolution_times, output_dir=None):
        """Visualize conversation metrics"""
        if output_dir is None:
            output_dir = self.output_dir
            
        os.makedirs(output_dir, exist_ok=True)
        
        # Check if we have valid data to visualize
        if (conversation_metrics is None or conversation_metrics.empty) and \
           (volume_over_time is None or volume_over_time.empty) and \
           (first_response_times is None or first_response_times.empty) and \
           (resolution_times is None or resolution_times.empty):
            print("No conversation metrics data to visualize")
            return

        # Volume over time visualization
        if volume_over_time is not None and not volume_over_time.empty and 'date' in volume_over_time.columns:
            plt.figure(figsize=(14, 8))
            volume_over_time = volume_over_time.sort_values('date')
            plt.plot(volume_over_time['date'], volume_over_time['count'], marker='o')
            plt.xlabel('Date')
            plt.ylabel('Conversation Count')
            plt.title('Conversation Volume Over Time')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'conversation_volume.png'))
            plt.close()
            
            # Save to CSV
            volume_over_time.to_csv(os.path.join(output_dir, 'conversation_volume.csv'), index=False)
        
        # First response time visualization
        if first_response_times is not None and not first_response_times.empty and 'date' in first_response_times.columns and 'first_response_time' in first_response_times.columns:
            plt.figure(figsize=(14, 8))
            first_response_times = first_response_times.sort_values('date')
            plt.plot(first_response_times['date'], first_response_times['first_response_time'] / 60, marker='o')  # Convert to minutes
            plt.xlabel('Date')
            plt.ylabel('First Response Time (minutes)')
            plt.title('First Response Time Trend')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'first_response_time.png'))
            plt.close()
            
            # Save to CSV
            first_response_times.to_csv(os.path.join(output_dir, 'first_response_time.csv'), index=False)
        
        # Resolution time visualization
        if resolution_times is not None and not resolution_times.empty and 'date' in resolution_times.columns and 'resolution_time' in resolution_times.columns:
            plt.figure(figsize=(14, 8))
            resolution_times = resolution_times.sort_values('date')
            plt.plot(resolution_times['date'], resolution_times['resolution_time'], marker='o')
            plt.xlabel('Date')
            plt.ylabel('Resolution Time (hours)')
            plt.title('Resolution Time Trend')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, 'resolution_time.png'))
            plt.close()
            
            # Save to CSV
            resolution_times.to_csv(os.path.join(output_dir, 'resolution_time.csv'), index=False)
        
        # Basic metrics visualization if available
        if conversation_metrics is not None and not conversation_metrics.empty:
            if 'date' in conversation_metrics.columns and 'conversation_count' in conversation_metrics.columns:
                # Line plot of conversation count
                plt.figure(figsize=(14, 8))
                conversation_metrics = conversation_metrics.sort_values('date')
                plt.plot(conversation_metrics['date'], conversation_metrics['conversation_count'], marker='o')
                plt.xlabel('Date')
                plt.ylabel('Conversation Count')
                plt.title('Daily Conversation Count')
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(os.path.join(output_dir, 'daily_conversation_count.png'))
                plt.close()
            
            # Save conversation metrics to CSV
            conversation_metrics.to_csv(os.path.join(output_dir, 'conversation_metrics.csv'), index=False)
    
    def run_full_analysis(self, start_date=None, end_date=None, limit=1000):
        """Run full analysis of Intercom data"""
        # Get admin and team data
        admin_df = self.get_team_members()
        team_df = self.get_teams()
        
        # Get conversation data
        conversations_df = self.get_conversations(start_date, end_date, limit=limit)
        
        # Check if we have any valid conversation data
        if conversations_df.empty:
            print("No conversation data found for the specified date range.")
            results = {
                'admin_df': admin_df,
                'team_df': team_df,
                'conversations_df': conversations_df,
                'admin_metrics': pd.DataFrame(),
                'team_metrics': pd.DataFrame(),
                'response_times': {
                    'admin_response_times': pd.DataFrame(),
                    'team_response_times': pd.DataFrame(),
                    'hourly_response_times': pd.DataFrame()
                },
                'conversation_metrics': pd.DataFrame(),
                'volume_over_time': pd.DataFrame(),
                'first_response_times': pd.DataFrame(),
                'resolution_times': pd.DataFrame(),
                'satisfaction_metrics': pd.DataFrame()
            }
            return results
            
        # Team performance analysis
        admin_metrics, team_metrics = self.get_team_performance(conversations_df, admin_df, team_df)
        
        # Response time analysis
        admin_response_times, team_response_times, hourly_response_times = self.analyze_response_times(
            conversations_df, admin_metrics, team_metrics
        )
        
        # Process conversation metrics
        if 'created_at' in conversations_df.columns:
            # Add date column for grouping
            conversations_df['date'] = conversations_df['created_at'].dt.date
            
            # Group conversations by date
            conversation_metrics = conversations_df.groupby('date').agg({
                'id': 'count',
                'first_response_time': 'median'
            }).reset_index()
            
            conversation_metrics.rename(columns={
                'id': 'conversation_count',
                'first_response_time': 'median_response_time'
            }, inplace=True)
            
            # Visualize conversation volume over time
            volume_over_time = conversations_df.groupby('date').size().reset_index(name='count')
        
            # Analyze first response times
            first_response_times = conversations_df.groupby('date')['first_response_time'].median().reset_index()
        
            # Analyze resolution times
            resolution_times = conversations_df[conversations_df['state'] == 'closed'].copy()
            if not resolution_times.empty and 'created_at' in resolution_times.columns and 'updated_at' in resolution_times.columns:
                resolution_times['resolution_time'] = (resolution_times['updated_at'] - resolution_times['created_at']).dt.total_seconds() / 3600
                resolution_times = resolution_times.groupby('date')['resolution_time'].median().reset_index()
            else:
                resolution_times = pd.DataFrame(columns=['date', 'resolution_time'])
        else:
            # Create empty dataframes if no conversation data
            conversation_metrics = pd.DataFrame(columns=['date', 'conversation_count', 'median_response_time'])
            volume_over_time = pd.DataFrame(columns=['date', 'count'])
            first_response_times = pd.DataFrame(columns=['date', 'first_response_time'])
            resolution_times = pd.DataFrame(columns=['date', 'resolution_time'])
        
        # Get satisfaction metrics
        try:
            satisfaction_metrics = self.get_satisfaction_metrics(start_date, end_date)
        except Exception as e:
            print(f"Error fetching satisfaction metrics: {e}")
            satisfaction_metrics = pd.DataFrame(columns=['date', 'total_responses', 'satisfied_responses', 
                                                        'neutral_responses', 'dissatisfied_responses', 'satisfaction_score'])
        
        # Visualize results
        if admin_metrics.empty and team_metrics.empty:
            print("No team performance data to visualize")
        else:
            self.visualize_team_performance(admin_metrics, team_metrics)
            
        if all(df.empty for df in [admin_response_times, team_response_times, hourly_response_times]):
            print("No response time data to visualize")
        else:
            self.visualize_response_time_analysis(admin_response_times, team_response_times, hourly_response_times)
            
        if all(df.empty for df in [conversation_metrics, volume_over_time, first_response_times, resolution_times]):
            print("No conversation metrics data to visualize")
        else:
            self.visualize_conversation_metrics(conversation_metrics, volume_over_time, first_response_times, resolution_times)
        
        # Return all results
        results = {
            'admin_df': admin_df,
            'team_df': team_df,
            'conversations_df': conversations_df,
            'admin_metrics': admin_metrics,
            'team_metrics': team_metrics,
            'response_times': {
            'admin_response_times': admin_response_times,
            'team_response_times': team_response_times,
                'hourly_response_times': hourly_response_times
            },
            'conversation_metrics': conversation_metrics,
            'volume_over_time': volume_over_time,
            'first_response_times': first_response_times,
            'resolution_times': resolution_times,
            'satisfaction_metrics': satisfaction_metrics
        }
            
        return results

    def export_results_to_zip(self, output_dir=None, zip_name=None):
        """Export all visualization results to a zip file for easy sharing"""
        if output_dir is None:
            output_dir = self.output_dir
            
        if zip_name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_name = f"intercom_analysis_{timestamp}.zip"
        
        import zipfile
        import glob
        
        # Path to the zip file
        zip_path = os.path.join(output_dir, zip_name)
        
        print(f"Creating zip archive at {zip_path}...")
        
        # Create a zip file
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all CSV files in the output directory
            csv_files = glob.glob(os.path.join(output_dir, '*.csv'))
            for csv_file in csv_files:
                zipf.write(csv_file, os.path.basename(csv_file))
                
            # Add all PNG files in the output directory
            png_files = glob.glob(os.path.join(output_dir, '*.png'))
            for png_file in png_files:
                zipf.write(png_file, os.path.basename(png_file))
                
            # Add a README file with information about the analysis
            readme_path = os.path.join(output_dir, 'README.txt')
            with open(readme_path, 'w') as f:
                f.write("Intercom Analytics Report\n")
                f.write("=======================\n\n")
                f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("Contents:\n")
                f.write("- CSV files with raw data and metrics\n")
                f.write("- PNG files with visualizations\n\n")
                f.write("For more information, contact the data analytics team.\n")
            
            zipf.write(readme_path, os.path.basename(readme_path))
            
            # Cleanup temporary README file
            os.remove(readme_path)
        
        print(f"Export completed. Results saved to {zip_path}")
        return zip_path

def main():
    parser = argparse.ArgumentParser(description='Intercom Analytics Tool')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--limit', type=int, default=1000, help='Limit number of conversations to fetch')
    parser.add_argument('--output-dir', type=str, default='intercom_reports', help='Output directory for reports')
    parser.add_argument('--export-zip', action='store_true', help='Export results to a zip file')
    parser.add_argument('--zip-name', type=str, help='Name for the zip file (default: intercom_analysis_TIMESTAMP.zip)')
    
    args = parser.parse_args()
    
    try:
        # Create analytics instance
        analytics = IntercomAnalytics(INTERCOM_ACCESS_TOKEN, output_dir=args.output_dir)
        
        # Run full analysis
        results = analytics.run_full_analysis(args.start_date, args.end_date, limit=args.limit)
        
        # Export results to zip if requested
        if args.export_zip:
            zip_path = analytics.export_results_to_zip(zip_name=args.zip_name)
            print(f"\nAnalysis results exported to: {zip_path}")
        
        print(f"\nAnalysis completed successfully! Reports saved to {args.output_dir}/")
        
    except Exception as e:
        print(f"Error running analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    main() 