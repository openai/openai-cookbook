# Meta Ads API - Campaign Status Detection Guide
# ==============================================

## Overview
This guide documents how to use the Meta Ads API to identify when campaigns are currently active and running, similar to the Google Ads API documentation.

## Prerequisites
- Meta Ads API access token with `ads_read` permission
- Ad account ID: `act_111192969640236` (Colppy)
- Python environment with `facebook-business` SDK

## Environment Variables
```bash
META_ADS_ACCESS_TOKEN=your_access_token_here
META_ADS_ACCOUNT_ID=act_111192969640236
META_ADS_APP_ID=4098296043769963
META_ADS_APP_SECRET=your_app_secret_here
```

## Campaign Status Detection

### 1. Basic Campaign Status Check

```python
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

# Initialize API
FacebookAdsApi.init(access_token=ACCESS_TOKEN)
account = AdAccount(ACCOUNT_ID)

# Get campaigns with status
campaigns = account.get_campaigns(fields=['id', 'name', 'status'])

for campaign in campaigns:
    status = campaign.get('status')
    if status == 'ACTIVE':
        print(f"✅ ACTIVE: {campaign.get('name')}")
    elif status == 'PAUSED':
        print(f"⏸️ PAUSED: {campaign.get('name')}")
    elif status == 'DELETED':
        print(f"🗑️ DELETED: {campaign.get('name')}")
```

### 2. Detailed Campaign Status with Timing

```python
def get_campaign_status_details():
    """Get detailed campaign status including timing information"""
    
    campaigns = account.get_campaigns(fields=[
        'id', 'name', 'status', 'created_time', 'updated_time',
        'start_time', 'stop_time', 'effective_status'
    ])
    
    active_campaigns = []
    paused_campaigns = []
    
    for campaign in campaigns:
        campaign_data = {
            'id': campaign.get('id'),
            'name': campaign.get('name'),
            'status': campaign.get('status'),
            'effective_status': campaign.get('effective_status'),
            'created_time': campaign.get('created_time'),
            'updated_time': campaign.get('updated_time'),
            'start_time': campaign.get('start_time'),
            'stop_time': campaign.get('stop_time')
        }
        
        if campaign_data['status'] == 'ACTIVE':
            active_campaigns.append(campaign_data)
        else:
            paused_campaigns.append(campaign_data)
    
    return active_campaigns, paused_campaigns
```

### 3. Real-Time Campaign Activity Check

```python
def check_campaign_activity():
    """Check which campaigns are currently running"""
    
    from datetime import datetime
    
    campaigns = account.get_campaigns(fields=[
        'id', 'name', 'status', 'effective_status', 
        'start_time', 'stop_time', 'budget_remaining'
    ])
    
    current_time = datetime.now()
    active_now = []
    
    for campaign in campaigns:
        status = campaign.get('status')
        effective_status = campaign.get('effective_status')
        start_time = campaign.get('start_time')
        stop_time = campaign.get('stop_time')
        
        # Check if campaign is currently active
        is_active_now = False
        
        if status == 'ACTIVE' and effective_status == 'ACTIVE':
            # Check timing constraints
            if start_time:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if current_time < start_dt:
                    continue  # Campaign hasn't started yet
            
            if stop_time:
                stop_dt = datetime.fromisoformat(stop_time.replace('Z', '+00:00'))
                if current_time > stop_dt:
                    continue  # Campaign has ended
            
            is_active_now = True
        
        if is_active_now:
            active_now.append({
                'id': campaign.get('id'),
                'name': campaign.get('name'),
                'status': status,
                'effective_status': effective_status,
                'budget_remaining': campaign.get('budget_remaining')
            })
    
    return active_now
```

### 4. Campaign Performance Status

```python
def get_campaign_performance_status():
    """Get campaign status with performance metrics"""
    
    # Get campaigns with performance data
    campaigns = account.get_campaigns(fields=[
        'id', 'name', 'status', 'effective_status',
        'budget_remaining', 'daily_budget', 'lifetime_budget'
    ])
    
    performance_status = []
    
    for campaign in campaigns:
        # Get insights for the last 7 days
        insights = campaign.get_insights(fields=[
            'impressions', 'clicks', 'spend', 'ctr', 'cpc'
        ], params={
            'time_range': {
                'since': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'until': datetime.now().strftime('%Y-%m-%d')
            }
        })
        
        total_impressions = 0
        total_clicks = 0
        total_spend = 0
        
        for insight in insights:
            total_impressions += int(insight.get('impressions', 0))
            total_clicks += int(insight.get('clicks', 0))
            total_spend += float(insight.get('spend', 0))
        
        performance_status.append({
            'id': campaign.get('id'),
            'name': campaign.get('name'),
            'status': campaign.get('status'),
            'effective_status': campaign.get('effective_status'),
            'budget_remaining': campaign.get('budget_remaining'),
            'daily_budget': campaign.get('daily_budget'),
            'lifetime_budget': campaign.get('lifetime_budget'),
            'last_7_days': {
                'impressions': total_impressions,
                'clicks': total_clicks,
                'spend': total_spend,
                'ctr': (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
                'cpc': total_spend / total_clicks if total_clicks > 0 else 0
            }
        })
    
    return performance_status
```

### 5. Campaign Status Summary

```python
def get_campaign_status_summary():
    """Get a comprehensive summary of all campaign statuses"""
    
    campaigns = account.get_campaigns(fields=[
        'id', 'name', 'status', 'effective_status',
        'created_time', 'updated_time', 'start_time', 'stop_time',
        'budget_remaining', 'daily_budget', 'lifetime_budget'
    ])
    
    summary = {
        'total_campaigns': 0,
        'active_campaigns': 0,
        'paused_campaigns': 0,
        'deleted_campaigns': 0,
        'campaigns_with_budget': 0,
        'campaigns_running_now': 0,
        'campaign_details': []
    }
    
    current_time = datetime.now()
    
    for campaign in campaigns:
        summary['total_campaigns'] += 1
        
        status = campaign.get('status')
        effective_status = campaign.get('effective_status')
        
        # Count by status
        if status == 'ACTIVE':
            summary['active_campaigns'] += 1
        elif status == 'PAUSED':
            summary['paused_campaigns'] += 1
        elif status == 'DELETED':
            summary['deleted_campaigns'] += 1
        
        # Check if campaign has budget
        if campaign.get('budget_remaining') and float(campaign.get('budget_remaining', 0)) > 0:
            summary['campaigns_with_budget'] += 1
        
        # Check if campaign is running now
        is_running_now = False
        if status == 'ACTIVE' and effective_status == 'ACTIVE':
            start_time = campaign.get('start_time')
            stop_time = campaign.get('stop_time')
            
            if start_time:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if current_time < start_dt:
                    is_running_now = False
                else:
                    is_running_now = True
            
            if stop_time and is_running_now:
                stop_dt = datetime.fromisoformat(stop_time.replace('Z', '+00:00'))
                if current_time > stop_dt:
                    is_running_now = False
        
        if is_running_now:
            summary['campaigns_running_now'] += 1
        
        # Add campaign details
        summary['campaign_details'].append({
            'id': campaign.get('id'),
            'name': campaign.get('name'),
            'status': status,
            'effective_status': effective_status,
            'is_running_now': is_running_now,
            'budget_remaining': campaign.get('budget_remaining'),
            'daily_budget': campaign.get('daily_budget'),
            'lifetime_budget': campaign.get('lifetime_budget'),
            'created_time': campaign.get('created_time'),
            'updated_time': campaign.get('updated_time'),
            'start_time': campaign.get('start_time'),
            'stop_time': campaign.get('stop_time')
        })
    
    return summary
```

## Status Values Reference

### Campaign Status Values:
- **`ACTIVE`**: Campaign is active and can serve ads
- **`PAUSED`**: Campaign is paused and not serving ads
- **`DELETED`**: Campaign is deleted
- **`ARCHIVED`**: Campaign is archived

### Effective Status Values:
- **`ACTIVE`**: Campaign is effectively active (considering all factors)
- **`PAUSED`**: Campaign is effectively paused
- **`DELETED`**: Campaign is effectively deleted
- **`PENDING_REVIEW`**: Campaign is pending review
- **`DISAPPROVED`**: Campaign is disapproved
- **`PREAPPROVED`**: Campaign is pre-approved
- **`PENDING_BILLING_INFO`**: Campaign is pending billing information
- **`CAMPAIGN_PAUSED`**: Campaign is paused
- **`ADGROUP_PAUSED`**: Ad group is paused
- **`AD_PAUSED`**: Ad is paused
- **`ACCOUNT_OVERSPENT`**: Account has overspent
- **`CAMPAIGN_OVERSPENT`**: Campaign has overspent
- **`ADGROUP_OVERSPENT`**: Ad group has overspent
- **`AD_OVERSPENT`**: Ad has overspent

## Complete Example Script

```python
#!/usr/bin/env python3
"""
Meta Ads Campaign Status Detection
=================================

Complete script to detect active campaigns and their status
"""

import os
from datetime import datetime, timedelta
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

# Configuration
ACCESS_TOKEN = os.environ.get('META_ADS_ACCESS_TOKEN')
ACCOUNT_ID = os.environ.get('META_ADS_ACCOUNT_ID', 'act_111192969640236')

def main():
    """Main function to check campaign status"""
    
    # Initialize API
    FacebookAdsApi.init(access_token=ACCESS_TOKEN)
    account = AdAccount(ACCOUNT_ID)
    
    print("🚀 Meta Ads Campaign Status Detection")
    print("=" * 50)
    
    # Get campaign status summary
    summary = get_campaign_status_summary()
    
    print(f"📊 Campaign Status Summary:")
    print(f"  Total Campaigns: {summary['total_campaigns']}")
    print(f"  Active Campaigns: {summary['active_campaigns']}")
    print(f"  Paused Campaigns: {summary['paused_campaigns']}")
    print(f"  Deleted Campaigns: {summary['deleted_campaigns']}")
    print(f"  Campaigns with Budget: {summary['campaigns_with_budget']}")
    print(f"  Campaigns Running Now: {summary['campaigns_running_now']}")
    
    print(f"\n🎯 Currently Active Campaigns:")
    for campaign in summary['campaign_details']:
        if campaign['is_running_now']:
            print(f"  ✅ {campaign['name']} (ID: {campaign['id']})")
            print(f"     Status: {campaign['status']}")
            print(f"     Effective Status: {campaign['effective_status']}")
            print(f"     Budget Remaining: ${campaign['budget_remaining']}")
            print()
    
    print(f"\n⏸️ Paused Campaigns:")
    for campaign in summary['campaign_details']:
        if campaign['status'] == 'PAUSED':
            print(f"  ⏸️ {campaign['name']} (ID: {campaign['id']})")
            print(f"     Effective Status: {campaign['effective_status']}")
            print()

if __name__ == "__main__":
    main()
```

## Usage Examples

### 1. Check Active Campaigns Only
```python
active_campaigns = check_campaign_activity()
for campaign in active_campaigns:
    print(f"Running: {campaign['name']}")
```

### 2. Get Campaign Performance Status
```python
performance = get_campaign_performance_status()
for campaign in performance:
    if campaign['status'] == 'ACTIVE':
        print(f"Active: {campaign['name']}")
        print(f"  Last 7 days: {campaign['last_7_days']['impressions']} impressions")
```

### 3. Monitor Campaign Status Changes
```python
# Run this periodically to monitor status changes
summary = get_campaign_status_summary()
print(f"Currently running: {summary['campaigns_running_now']} campaigns")
```

## Error Handling

```python
from facebook_business.exceptions import FacebookRequestError

try:
    campaigns = account.get_campaigns(fields=['id', 'name', 'status'])
except FacebookRequestError as e:
    print(f"API Error: {e}")
    if e.api_error_code() == 200:
        print("Permission denied - check ads_read permission")
    elif e.api_error_code() == 190:
        print("Invalid access token")
```

## Best Practices

1. **Check Both Status and Effective Status**: Always check both fields for accurate status
2. **Consider Timing**: Check start_time and stop_time for campaigns with scheduling
3. **Monitor Budget**: Check budget_remaining to ensure campaigns can still serve
4. **Handle Errors**: Always wrap API calls in try-catch blocks
5. **Rate Limiting**: Implement delays between API calls if processing many campaigns
6. **Caching**: Cache results for a few minutes to avoid excessive API calls

## Integration with Other Tools

This campaign status detection can be integrated with:
- **HubSpot**: Update contact properties based on campaign activity
- **Mixpanel**: Track campaign performance events
- **Slack**: Send notifications when campaigns go live/pause
- **Email**: Send daily campaign status reports
