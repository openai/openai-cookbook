# HubSpot Complete Data Retrieval - Quick Reference

## 🚨 CRITICAL: Always Use Complete Pagination

**Never limit HubSpot data retrieval to 100 records unless explicitly requested by user.**

---

## 🚀 Quick Usage Examples

### Complete Contacts Analysis
```bash
# August 2025 contacts (all records)
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type contacts \
  --start-date 2025-08-01 \
  --end-date 2025-08-31

# Specific properties only
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type contacts \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --properties email firstname lastname utm_campaign activo
```

### Complete Deals Analysis
```bash
# August 2025 deals (all records)
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type deals \
  --start-date 2025-08-01 \
  --end-date 2025-08-31

# With associations
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type deals \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --associations companies contacts
```

### Complete Companies Analysis
```bash
# August 2025 companies (all records)
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type companies \
  --start-date 2025-08-01 \
  --end-date 2025-08-31
```

---

## 📊 What You Get

### Output Files
- **Raw Data**: `hubspot_{object_type}_{start_date}_{end_date}_{timestamp}.json`
- **Analysis**: `hubspot_{object_type}_analysis_{start_date}_{end_date}_{timestamp}.json`

### Console Output
```
🔍 Starting contacts retrieval with complete pagination...
📋 Properties: 18 fields
🔍 Filters: 1 filter groups
📄 Fetching page 1...
   📊 Retrieved 100 records (Total: 100)
📄 Fetching page 2...
   📊 Retrieved 100 records (Total: 200)
...
✅ All records retrieved. Total: 1,115

📊 CONTACTS ANALYSIS RESULTS
============================
📈 SUMMARY STATISTICS
------------------------------
Total Records: 1,115
With Email: 1,105 (99.1%)
With Company: 20 (1.8%)
With Deals: 206 (18.5%)
```

---

## 🔧 Customization

### Custom Properties
```bash
# Only specific fields
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type contacts \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --properties email utm_campaign activo fecha_activo num_associated_deals
```

### With Associations
```bash
# Include related objects
python tools/scripts/hubspot_complete_retrieval_template.py \
  --object-type deals \
  --start-date 2025-08-01 \
  --end-date 2025-08-31 \
  --associations companies contacts
```

---

## 📋 Default Properties by Object Type

### Contacts
- email, firstname, lastname, company, lifecyclestage
- createdate, utm_campaign, utm_source, utm_medium, utm_term, utm_content
- activo, fecha_activo, num_associated_deals, hs_lead_status
- hs_analytics_source, hs_analytics_source_data_1, hs_analytics_source_data_2

### Deals
- dealname, dealstage, amount, closedate, createdate
- pipeline, dealtype, hs_analytics_source, description
- hubspot_owner_id, hs_deal_stage_probability, hs_forecast_probability
- hs_forecast_category, hs_next_step, hs_notes_last_contacted

### Companies
- name, domain, industry, createdate, lifecyclestage
- num_associated_deals, hs_analytics_source, city, state, country
- phone, website, description, annualrevenue, numberofemployees, type
- hs_analytics_source_data_1, hs_analytics_source_data_2

---

## ⚠️ Important Notes

### Environment Setup
```bash
# Set HubSpot API key
export HUBSPOT_API_KEY="your_token_here"

# Or use .env file
source .env
```

### Date Format
- **Input**: YYYY-MM-DD (e.g., 2025-08-01)
- **API**: Automatically converted to ISO format with timezone

### Rate Limiting
- Built-in 0.1 second delay between requests
- Handles API rate limits gracefully
- Reports errors without stopping analysis

---

## 🎯 When to Use This Template

### ✅ Use This Template For:
- **Monthly analysis** (complete datasets)
- **Quarterly reports** (all records)
- **Year-over-year comparisons** (complete data)
- **Campaign analysis** (all contacts/deals)
- **Data exports** (complete datasets)

### ❌ Don't Use For:
- **Quick samples** (use MCP tools with limit=10)
- **Real-time dashboards** (use MCP tools)
- **Testing** (use MCP tools with small limits)

---

## 🔍 Troubleshooting

### Common Issues

**"HUBSPOT_API_KEY not found"**
```bash
export HUBSPOT_API_KEY="your_token_here"
```

**"No records found"**
- Check date range contains actual data
- Verify object type is correct
- Check HubSpot account has data in period

**Rate limit errors**
- Script handles automatically
- Increase delay if needed: `time.sleep(0.2)`

---

## 📚 Related Documentation

- **[HubSpot Pagination Standards](tools/docs/README_HUBSPOT_PAGINATION_STANDARDS.md)** - Complete methodology
- **[HubSpot Configuration](tools/docs/README_HUBSPOT_CONFIGURATION.md)** - Field mappings
- **[HubSpot API Docs](https://developers.hubspot.com/docs/api/crm/search)** - Official documentation

---

**⚠️ REMEMBER: Complete data retrieval is critical for accurate business analysis. Always use this template for comprehensive analysis.**
