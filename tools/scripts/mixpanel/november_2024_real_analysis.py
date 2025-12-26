"""
November 2024 Real Data Analysis - From MCP Mixpanel Queries

This script analyzes the real data fetched from MCP Mixpanel tools
for November 2024 and provides engagement insights.

Author: Colppy Analytics Team
Date: 2024-12-24
"""

import json
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

# Real data from MCP Mixpanel queries - November 2024
LOGIN_DATA = {
    "series": ["2024-11-01","2024-11-02","2024-11-03","2024-11-04","2024-11-05",
               "2024-11-06","2024-11-07","2024-11-08","2024-11-09","2024-11-10",
               "2024-11-11","2024-11-12","2024-11-13","2024-11-14","2024-11-15",
               "2024-11-16","2024-11-17","2024-11-18","2024-11-19","2024-11-20",
               "2024-11-21","2024-11-22","2024-11-23","2024-11-24","2024-11-25",
               "2024-11-26","2024-11-27","2024-11-28","2024-11-29","2024-11-30"],
    "values": {
        "Login": {
            "2024-11-01": 9216, "2024-11-02": 1297, "2024-11-03": 825,
            "2024-11-04": 9958, "2024-11-05": 9791, "2024-11-06": 10349,
            "2024-11-07": 9590, "2024-11-08": 9213, "2024-11-09": 1335,
            "2024-11-10": 1026, "2024-11-11": 10029, "2024-11-12": 10037,
            "2024-11-13": 10384, "2024-11-14": 9307, "2024-11-15": 8891,
            "2024-11-16": 1217, "2024-11-17": 619, "2024-11-18": 1431,
            "2024-11-19": 9779, "2024-11-20": 9568, "2024-11-21": 9381,
            "2024-11-22": 9101, "2024-11-23": 1129, "2024-11-24": 644,
            "2024-11-25": 9386, "2024-11-26": 9267, "2024-11-27": 8897,
            "2024-11-28": 8660, "2024-11-29": 8559, "2024-11-30": 1280
        }
    }
}

INVOICE_DATA = {
    "series": ["2024-11-01","2024-11-02","2024-11-03","2024-11-04","2024-11-05",
               "2024-11-06","2024-11-07","2024-11-08","2024-11-09","2024-11-10",
               "2024-11-11","2024-11-12","2024-11-13","2024-11-14","2024-11-15",
               "2024-11-16","2024-11-17","2024-11-18","2024-11-19","2024-11-20",
               "2024-11-21","2024-11-22","2024-11-23","2024-11-24","2024-11-25",
               "2024-11-26","2024-11-27","2024-11-28","2024-11-29","2024-11-30"],
    "values": {
        "Generó comprobante de venta": {
            "2024-11-01": 14393, "2024-11-02": 3049, "2024-11-03": 1054,
            "2024-11-04": 11020, "2024-11-05": 10657, "2024-11-06": 8833,
            "2024-11-07": 9066, "2024-11-08": 8614, "2024-11-09": 2072,
            "2024-11-10": 1247, "2024-11-11": 9317, "2024-11-12": 8335,
            "2024-11-13": 8589, "2024-11-14": 7980, "2024-11-15": 7285,
            "2024-11-16": 1864, "2024-11-17": 681, "2024-11-18": 1326,
            "2024-11-19": 8150, "2024-11-20": 7748, "2024-11-21": 8284,
            "2024-11-22": 7598, "2024-11-23": 1948, "2024-11-24": 780,
            "2024-11-25": 8138, "2024-11-26": 7722, "2024-11-27": 7750,
            "2024-11-28": 7591, "2024-11-29": 7370, "2024-11-30": 3054
        }
    }
}

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║     NOVEMBER 2024 ENGAGEMENT ANALYSIS - REAL DATA                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Project: Colppy User Level Production (2201475)
Period: November 1-30, 2024
Analysis Date: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """

═══════════════════════════════════════════════════════════════════════════════
""")

# Analyze Login Data
login_values = LOGIN_DATA["values"]["Login"]
total_logins = sum(login_values.values())
avg_daily_logins = total_logins / len(login_values)
max_logins_day = max(login_values.items(), key=lambda x: x[1])
min_logins_day = min(login_values.items(), key=lambda x: x[1])

# Analyze Invoice Data
invoice_values = INVOICE_DATA["values"]["Generó comprobante de venta"]
total_invoices = sum(invoice_values.values())
avg_daily_invoices = total_invoices / len(invoice_values)
max_invoices_day = max(invoice_values.items(), key=lambda x: x[1])
min_invoices_day = min(invoice_values.items(), key=lambda x: x[1])

# Calculate engagement metrics
# Assuming each login = 2 points, each invoice = 10 points
total_weighted_events = (total_logins * 2) + (total_invoices * 10)

# Estimate unique users (assuming average user logs in 20 times per month)
estimated_unique_users = total_logins / 20 if total_logins > 0 else 0

# Calculate average engagement per user
avg_weighted_events_per_user = total_weighted_events / estimated_unique_users if estimated_unique_users > 0 else 0

print("📊 EVENT-LEVEL ANALYSIS")
print("="*80)

print("\n🔐 LOGIN EVENTS")
print("-"*80)
print(f"   Total Logins (November 2024): {total_logins:,}")
print(f"   Average Daily Logins: {avg_daily_logins:,.0f}")
print(f"   Peak Day: {max_logins_day[0]} - {max_logins_day[1]:,} logins")
print(f"   Low Day: {min_logins_day[0]} - {min_logins_day[1]:,} logins")
print(f"   Estimated Unique Users: {estimated_unique_users:,.0f}")

print("\n💰 INVOICE GENERATION EVENTS")
print("-"*80)
print(f"   Total Invoices Generated: {total_invoices:,}")
print(f"   Average Daily Invoices: {avg_daily_invoices:,.0f}")
print(f"   Peak Day: {max_invoices_day[0]} - {max_invoices_day[1]:,} invoices")
print(f"   Low Day: {min_invoices_day[0]} - {min_invoices_day[1]:,} invoices")

# Calculate invoice-to-login ratio
invoice_login_ratio = (total_invoices / total_logins * 100) if total_logins > 0 else 0
print(f"   Invoice-to-Login Ratio: {invoice_login_ratio:.1f}%")

print("\n📈 ENGAGEMENT METRICS")
print("-"*80)
print(f"   Total Weighted Events: {total_weighted_events:,}")
print(f"   Estimated Unique Users: {estimated_unique_users:,.0f}")
print(f"   Average Weighted Events per User: {avg_weighted_events_per_user:.1f}")

# Estimate engagement score distribution
# Based on weighted events per user
if avg_weighted_events_per_user >= 50:
    estimated_avg_score = 85
    estimated_tier = "Champion"
elif avg_weighted_events_per_user >= 30:
    estimated_avg_score = 70
    estimated_tier = "Engaged"
elif avg_weighted_events_per_user >= 20:
    estimated_avg_score = 55
    estimated_tier = "Moderate"
elif avg_weighted_events_per_user >= 10:
    estimated_avg_score = 35
    estimated_tier = "At Risk"
else:
    estimated_avg_score = 15
    estimated_tier = "Churned"

print(f"\n   Estimated Average Engagement Score: {estimated_avg_score:.0f}")
print(f"   Estimated Average Tier: {estimated_tier}")

print("\n📅 DAILY TRENDS ANALYSIS")
print("-"*80)

# Identify patterns
weekday_logins = []
weekend_logins = []

for date_str, count in login_values.items():
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    if date_obj.weekday() < 5:  # Monday-Friday
        weekday_logins.append(count)
    else:  # Saturday-Sunday
        weekend_logins.append(count)

avg_weekday_logins = sum(weekday_logins) / len(weekday_logins) if weekday_logins else 0
avg_weekend_logins = sum(weekend_logins) / len(weekend_logins) if weekend_logins else 0

print(f"   Average Weekday Logins: {avg_weekday_logins:,.0f}")
print(f"   Average Weekend Logins: {avg_weekend_logins:,.0f}")
print(f"   Weekday/Weekend Ratio: {(avg_weekday_logins / avg_weekend_logins) if avg_weekend_logins > 0 else 0:.2f}")

# Weekly patterns
weeks = defaultdict(list)
for date_str, count in login_values.items():
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    week_num = date_obj.isocalendar()[1]
    weeks[week_num].append(count)

print("\n   Weekly Patterns:")
for week_num in sorted(weeks.keys()):
    week_total = sum(weeks[week_num])
    print(f"     Week {week_num}: {week_total:,} logins")

print("\n💡 KEY INSIGHTS")
print("="*80)

insights = []

# High activity insight
if total_logins > 200000:
    insights.append("✅ Very high login activity - strong user engagement")
elif total_logins > 100000:
    insights.append("✅ High login activity - good user engagement")
else:
    insights.append("⚠️ Moderate login activity - monitor engagement trends")

# Invoice generation insight
if total_invoices > 200000:
    insights.append("✅ Very high invoice generation - core value being delivered")
elif total_invoices > 100000:
    insights.append("✅ High invoice generation - good core value usage")
else:
    insights.append("⚠️ Moderate invoice generation - opportunity to increase core feature usage")

# Consistency insight
login_variance = sum((v - avg_daily_logins)**2 for v in login_values.values()) / len(login_values)
if login_variance < avg_daily_logins * 0.5:
    insights.append("✅ Consistent daily activity - stable user base")
else:
    insights.append("⚠️ Variable daily activity - investigate peak/low days")

# Invoice-to-login ratio insight
if invoice_login_ratio > 80:
    insights.append("✅ High invoice-to-login ratio - users getting value")
elif invoice_login_ratio > 50:
    insights.append("✅ Good invoice-to-login ratio - healthy usage")
else:
    insights.append("⚠️ Low invoice-to-login ratio - opportunity to increase core feature adoption")

for i, insight in enumerate(insights, 1):
    print(f"   {i}. {insight}")

print("\n📋 RECOMMENDATIONS")
print("="*80)

recommendations = []

if avg_weekend_logins < avg_weekday_logins * 0.3:
    recommendations.append("Consider weekend engagement campaigns to increase activity")

if invoice_login_ratio < 50:
    recommendations.append("Focus on increasing invoice generation - core value feature")

if estimated_avg_score < 60:
    recommendations.append("Overall engagement is moderate - implement engagement improvement initiatives")

if max_logins_day[1] > avg_daily_logins * 2:
    recommendations.append(f"Investigate peak day ({max_logins_day[0]}) - understand what drove high engagement")

for i, rec in enumerate(recommendations, 1):
    print(f"   {i}. {rec}")

print("\n" + "="*80)
print("✅ Analysis Complete")
print("="*80)

# Export summary
summary = {
    "period": {
        "start_date": "2024-11-01",
        "end_date": "2024-11-30",
        "analysis_date": datetime.now().isoformat()
    },
    "login_metrics": {
        "total_logins": total_logins,
        "average_daily": avg_daily_logins,
        "peak_day": {"date": max_logins_day[0], "count": max_logins_day[1]},
        "low_day": {"date": min_logins_day[0], "count": min_logins_day[1]},
        "estimated_unique_users": estimated_unique_users
    },
    "invoice_metrics": {
        "total_invoices": total_invoices,
        "average_daily": avg_daily_invoices,
        "peak_day": {"date": max_invoices_day[0], "count": max_invoices_day[1]},
        "low_day": {"date": min_invoices_day[0], "count": min_invoices_day[1]},
        "invoice_to_login_ratio": invoice_login_ratio
    },
    "engagement_metrics": {
        "total_weighted_events": total_weighted_events,
        "average_per_user": avg_weighted_events_per_user,
        "estimated_average_score": estimated_avg_score,
        "estimated_tier": estimated_tier
    },
    "daily_data": {
        "logins": login_values,
        "invoices": invoice_values
    }
}

with open("november_2024_engagement_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\n📁 Summary exported to: november_2024_engagement_summary.json")




















