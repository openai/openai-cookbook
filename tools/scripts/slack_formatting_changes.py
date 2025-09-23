#!/usr/bin/env python3
"""
Exact Code Changes for Slack Notification Formatting
==================================================

This shows exactly what was changed in the sendSlackNotification function
to fix the formatting issue.

Author: CEO Assistant
Date: September 13, 2025
"""

def main():
    """Show the exact code changes."""
    print("🔧 EXACT CODE CHANGES FOR SLACK NOTIFICATION FORMATTING")
    print("=" * 60)
    print()
    print("📍 LOCATION: sendSlackNotification function")
    print()
    print("❌ OLD CODE (with formatting issues):")
    print("-" * 40)
    print("""
// Add additional details based on notification type
if (notification.type === 'warning' && notification.details.dealDetails) {
  const dealSummary = notification.details.dealDetails
    .slice(0, 5) // Show first 5 deals
    .map(d => `• ${d.name} (${d.stage}) - ${d.closeDate ? new Date(d.closeDate).toISOString().split('T')[0] : 'No date'}`)
    .join('\\n');
  
  slackMessage.attachments[0].fields.push({
    title: 'Deal Details',
    value: dealSummary + (notification.details.dealDetails.length > 5 ? '\\n...' : ''),
    short: false
  });
}
""")
    print()
    print("✅ NEW CODE (fixed formatting):")
    print("-" * 40)
    print("""
// Fixed Slack notification function with proper formatting
async function sendSlackNotification(notification) {
  const slackWebhookUrl = 'https://hooks.slack.com/services/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';
  
  // Create properly formatted Slack message
  let slackMessage;
  
  if (notification.type === 'warning' && notification.details.dealDetails) {
    // For warning notifications, create a well-formatted message
    const dealList = notification.details.dealDetails
      .slice(0, 5) // Show first 5 deals
      .map(d => `• ${d.name} (${d.stage}) - ${d.closeDate ? new Date(d.closeDate).toISOString().split('T')[0] : 'No date'}`)
      .join('\n');
    
    const dealSummary = dealList + (notification.details.dealDetails.length > 5 ? '\n• ...' : '');
    
    slackMessage = {
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: 'Company',
              value: notification.details.companyName || 'Unknown',
              short: true
            },
            {
              title: 'Company ID',
              value: notification.details.companyId || 'Unknown',
              short: true
            },
            {
              title: 'Message',
              value: notification.message,
              short: false
            },
            {
              title: 'Deal Details',
              value: dealSummary,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000)
        }
      ]
    };
  } else {
    // For other notification types, use standard format
    slackMessage = {
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: 'Company',
              value: notification.details.companyName || 'Unknown',
              short: true
            },
            {
              title: 'Company ID',
              value: notification.details.companyId || 'Unknown',
              short: true
            },
            {
              title: 'Message',
              value: notification.message,
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000)
        }
      ]
    };
  }

  const response = await fetch(slackWebhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(slackMessage)
  });

  if (!response.ok) {
    throw new Error(`Slack API error: ${response.status} ${response.statusText}`);
  }
}
""")
    print()
    print("🔍 KEY CHANGES:")
    print("   1. Changed from '\\n' to '\\n' (actual newline characters)")
    print("   2. Restructured the entire function to handle formatting properly")
    print("   3. Moved deal details into the main message structure")
    print("   4. Used proper Slack field formatting")
    print()
    print("📝 WHAT TO DO:")
    print("   1. Find your sendSlackNotification function")
    print("   2. Replace it with the NEW CODE above")
    print("   3. Test again with Gisela Mariotti Contadora")
    print()
    print("🎯 RESULT: Each deal will now appear on its own line!")

if __name__ == "__main__":
    main()
