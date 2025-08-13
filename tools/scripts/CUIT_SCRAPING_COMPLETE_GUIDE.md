# Complete CUIT Web Scraping Solution

This is a comprehensive web scraping solution for searching and extracting CUIT information from cuitonline.com, with multiple tools and automation options.

## 🚀 Quick Start

### 1. Setup (One-time)

```bash
# Navigate to scripts directory
cd tools/scripts

# Run the setup script
./setup_scraping_tools.sh

# Or manually install dependencies
pip install requests beautifulsoup4 lxml
pip install selenium  # Optional
pip install playwright && playwright install  # Optional
```

### 2. Basic Usage

```bash
# Activate virtual environment (if you used the setup script)
source cuit_scraper_env/bin/activate

# Run the command-line scraper
python cuitonline_scraper.py

# Or use the GUI application
python cuit_lookup_gui.py
```

## 📦 What's Included

### 1. **cuitonline_scraper.py** - Core Scraping Library
- Multiple scraping methods (requests, Selenium, Playwright)
- Anti-detection measures
- Rate limiting
- Export to CSV/JSON
- Batch processing support

### 2. **cuit_lookup_gui.py** - Desktop GUI Application
- User-friendly interface
- Single and batch search
- Real-time results display
- Export functionality
- No coding required

### 3. **automated_cuit_enrichment.py** - HubSpot Integration
- Automatically find companies without CUIT
- Search and validate CUITs
- Update HubSpot CRM
- Progress tracking and reporting

### 4. **afip_cuit_lookup.py** - Official AFIP API (Alternative)
- Direct access to government AFIP data
- Most accurate but requires paid API access
- See [AFIP_API_README.md](AFIP_API_README.md)

## 🎯 Choose Your Tool

### For Manual Lookups
Use the **GUI Application** - Perfect for:
- Non-technical users
- Quick lookups
- Visual results
- Easy export

```bash
python cuit_lookup_gui.py
```

### For Automation/Scripts
Use the **Core Library** - Perfect for:
- Integration with existing scripts
- Batch processing
- Custom workflows
- API development

```python
from cuitonline_scraper import CUITOnlineScraper

scraper = CUITOnlineScraper(method="playwright")
results = scraper.search_by_name("empresa ejemplo")
```

### For HubSpot Users
Use the **Automated Enrichment** - Perfect for:
- CRM data enrichment
- Bulk updates
- Scheduled runs
- Data validation

```bash
python automated_cuit_enrichment.py --limit 100
```

## 📋 Common Use Cases

### 1. Single Company Lookup

```python
from cuitonline_scraper import CUITOnlineScraper

scraper = CUITOnlineScraper()
results = scraper.search_by_name("verdier piazza")

for result in results:
    print(f"CUIT: {result.cuit}")
    print(f"Name: {result.name}")
    print(f"Status: {result.estado}")
```

### 2. Batch Processing from CSV

```python
import csv
from cuitonline_scraper import CUITOnlineScraper

scraper = CUITOnlineScraper(method="playwright")

# Read company names from CSV
with open('companies.csv', 'r') as f:
    reader = csv.DictReader(f)
    companies = [row['name'] for row in reader]

# Search for each company
all_results = []
for company in companies:
    results = scraper.search_by_name(company)
    all_results.extend(results)

# Export results
scraper.export_results(all_results, "batch_results")
```

### 3. Automated Daily Enrichment

```python
# schedule_enrichment.py
import schedule
import time
from automated_cuit_enrichment import AutomatedCUITEnrichment

def daily_enrichment():
    enrichment = AutomatedCUITEnrichment(
        scraper_method="playwright",
        use_afip_validation=False
    )
    enrichment.process_companies(limit=100)

# Run every day at 9 AM
schedule.every().day.at("09:00").do(daily_enrichment)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 4. API Integration

```python
from flask import Flask, jsonify
from cuitonline_scraper import CUITOnlineScraper

app = Flask(__name__)
scraper = CUITOnlineScraper()

@app.route('/api/cuit/<name>')
def get_cuit(name):
    results = scraper.search_by_name(name)
    return jsonify([{
        'cuit': r.cuit,
        'name': r.name,
        'status': r.estado
    } for r in results])

if __name__ == '__main__':
    app.run(debug=True)
```

## 🔧 Configuration Options

### Scraping Methods

1. **requests** (Default)
   - Fastest method
   - Works for static content
   - May miss JavaScript-rendered content

2. **selenium**
   - Handles JavaScript
   - Requires ChromeDriver
   - Good compatibility

3. **playwright**
   - Modern alternative to Selenium
   - Better performance
   - Built-in browser management

### Rate Limiting

Adjust rate limiting to avoid being blocked:

```python
scraper = CUITOnlineScraper()
scraper.min_request_interval = 5.0  # 5 seconds between requests
```

### Headless Mode

Run browsers without GUI (faster):

```python
scraper = CUITOnlineScraper(method="playwright", headless=True)
```

## 🛠️ Troubleshooting

### Common Issues

1. **"No module named 'selenium'"**
   ```bash
   pip install selenium
   ```

2. **"ChromeDriver not found"**
   - macOS: `brew install chromedriver`
   - Ubuntu: `sudo apt-get install chromium-chromedriver`
   - Windows: Download from [ChromeDriver](https://chromedriver.chromium.org/)

3. **"Playwright browsers not installed"**
   ```bash
   playwright install chromium
   playwright install-deps  # Linux only
   ```

4. **"Ad blocker detected"**
   - The scraper handles this automatically
   - Try using Selenium or Playwright methods
   - Run with `headless=False` to debug

5. **"No results found"**
   - Try variations of the company name
   - Remove suffixes like "S.A.", "SRL"
   - Use only the first few words

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

scraper = CUITOnlineScraper()
```

## 📊 Export Formats

### CSV Export
```csv
CUIT,Name,Type,Status,Address,City,Province
20-12345678-9,"EXAMPLE COMPANY","Persona Jurídica","ACTIVO","Street 123","Buenos Aires","CAPITAL FEDERAL"
```

### JSON Export
```json
[
  {
    "cuit": "20-12345678-9",
    "name": "EXAMPLE COMPANY",
    "tipo_persona": "Persona Jurídica",
    "estado": "ACTIVO",
    "direccion": "Street 123",
    "localidad": "Buenos Aires",
    "provincia": "CAPITAL FEDERAL"
  }
]
```

## 🔒 Best Practices

1. **Respect Rate Limits**
   - Don't make requests too quickly
   - Use built-in rate limiting
   - Consider caching results

2. **Handle Errors Gracefully**
   ```python
   try:
       results = scraper.search_by_name(name)
   except Exception as e:
       print(f"Error searching {name}: {e}")
   ```

3. **Save Results Regularly**
   - Export after each batch
   - Keep backups of scraped data
   - Avoid re-scraping same data

4. **Monitor Performance**
   - Track success rates
   - Log errors for debugging
   - Adjust methods as needed

## 🚨 Legal & Ethical Considerations

- **Terms of Service**: Always respect the website's ToS
- **Rate Limiting**: Don't overload servers
- **Data Privacy**: Handle personal data responsibly
- **Commercial Use**: Verify you have rights to use the data
- **Attribution**: Credit data sources appropriately

## 📈 Performance Tips

1. **Use Appropriate Method**
   - Start with `requests` (fastest)
   - Use `playwright` only when needed
   - Batch similar operations

2. **Optimize Searches**
   - Clean company names before searching
   - Remove common suffixes
   - Try multiple variations

3. **Cache Results**
   ```python
   import json
   import os
   
   cache_file = 'cuit_cache.json'
   cache = {}
   
   if os.path.exists(cache_file):
       with open(cache_file, 'r') as f:
           cache = json.load(f)
   
   def search_with_cache(name):
       if name in cache:
           return cache[name]
       
       results = scraper.search_by_name(name)
       cache[name] = results
       
       with open(cache_file, 'w') as f:
           json.dump(cache, f)
       
       return results
   ```

## 🔄 Integration Examples

### With Pandas DataFrame

```python
import pandas as pd
from cuitonline_scraper import CUITOnlineScraper

# Read companies
df = pd.read_csv('companies.csv')

# Add CUIT column
scraper = CUITOnlineScraper()

def get_cuit(name):
    results = scraper.search_by_name(name)
    return results[0].cuit if results else None

df['cuit'] = df['company_name'].apply(get_cuit)

# Save enriched data
df.to_csv('companies_with_cuit.csv', index=False)
```

### With Database

```python
import sqlite3
from cuitonline_scraper import CUITOnlineScraper

conn = sqlite3.connect('companies.db')
cursor = conn.cursor()

# Get companies without CUIT
cursor.execute("SELECT id, name FROM companies WHERE cuit IS NULL")
companies = cursor.fetchall()

scraper = CUITOnlineScraper()

for company_id, name in companies:
    results = scraper.search_by_name(name)
    if results:
        cursor.execute(
            "UPDATE companies SET cuit = ? WHERE id = ?",
            (results[0].cuit, company_id)
        )

conn.commit()
conn.close()
```

## 📞 Support

For issues or questions:

1. Check the troubleshooting section
2. Review the example code
3. Enable debug logging
4. Test with different scraping methods

## 🎉 Summary

You now have a complete CUIT scraping solution with:

- ✅ Multiple scraping methods
- ✅ GUI application for easy use
- ✅ Automated HubSpot integration
- ✅ Batch processing capabilities
- ✅ Export to CSV/JSON
- ✅ Rate limiting and error handling
- ✅ Comprehensive documentation

Choose the tool that best fits your needs and start enriching your data with official CUIT information!