# CUIT Online Web Scraper

A comprehensive web scraper for searching and extracting CUIT information from cuitonline.com.

## Features

- **Multiple Scraping Methods**: Choose between requests, Selenium, or Playwright
- **Anti-Detection**: Built-in measures to avoid bot detection
- **Rate Limiting**: Automatic delays to respect server limits
- **Export Options**: Save results as JSON or CSV
- **Detailed Extraction**: Get complete CUIT information including address, tax status, and activities
- **Batch Processing**: Search multiple names efficiently

## Installation

### Option 1: Basic Installation (Requests + BeautifulSoup)

```bash
pip install requests beautifulsoup4 lxml
```

### Option 2: Selenium Installation (For JavaScript-heavy pages)

```bash
# Install Selenium
pip install selenium

# Download ChromeDriver
# For macOS (using Homebrew):
brew install chromedriver

# For Ubuntu/Debian:
sudo apt-get update
sudo apt-get install chromium-chromedriver

# For Windows:
# Download from https://chromedriver.chromium.org/
# Add to PATH or place in project directory
```

### Option 3: Playwright Installation (Modern alternative)

```bash
# Install Playwright
pip install playwright

# Install browser drivers
playwright install chromium
playwright install-deps  # Install system dependencies (Linux only)
```

### Complete Installation (All methods)

```bash
# Create virtual environment
python -m venv cuit_scraper_env
source cuit_scraper_env/bin/activate  # On Windows: cuit_scraper_env\Scripts\activate

# Install all dependencies
pip install requests beautifulsoup4 lxml selenium playwright

# Install Playwright browsers
playwright install chromium
```

## Usage

### Basic Search

```python
from cuitonline_scraper import CUITOnlineScraper

# Using requests (fastest, but may not work for all pages)
scraper = CUITOnlineScraper(method="requests")
results = scraper.search_by_name("verdier piazza")

# Print results
for result in results:
    print(f"CUIT: {result.cuit}")
    print(f"Name: {result.name}")
    print(f"Type: {result.tipo_persona}")
    print(f"Status: {result.estado}")

# Export to files
scraper.export_results(results, "search_results")
```

### Using Selenium (for JavaScript rendering)

```python
# Use Selenium for better compatibility
scraper = CUITOnlineScraper(method="selenium", headless=True)
results = scraper.search_by_name("empresa ejemplo sa")

# Get detailed information
if results and results[0].detail_url:
    details = scraper.get_cuit_details(results[0].detail_url)
    print(f"Address: {details.direccion}")
    print(f"Tax Status: {details.condicion_impositiva}")
```

### Using Playwright (recommended for automation)

```python
# Playwright offers better performance and reliability
scraper = CUITOnlineScraper(method="playwright", headless=True)
results = scraper.search_by_name("gomez martin")
```

### Batch Processing

```python
# Search multiple names
names_to_search = [
    "verdier piazza",
    "gomez martin",
    "empresa ejemplo sa",
    "consultora abc"
]

all_results = []
scraper = CUITOnlineScraper(method="playwright")

for name in names_to_search:
    print(f"Searching for: {name}")
    results = scraper.search_by_name(name)
    all_results.extend(results)
    
# Export all results
scraper.export_results(all_results, "batch_search_results")
```

## Automation Examples

### Scheduled Scraping

```python
import schedule
import time

def daily_cuit_search():
    scraper = CUITOnlineScraper(method="playwright")
    
    # Read names from file
    with open("names_to_search.txt", "r") as f:
        names = [line.strip() for line in f]
    
    results = []
    for name in names:
        results.extend(scraper.search_by_name(name))
    
    # Save results with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d")
    scraper.export_results(results, f"daily_results_{timestamp}")

# Schedule daily at 9 AM
schedule.every().day.at("09:00").do(daily_cuit_search)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Integration with Existing Systems

```python
# Integrate with your HubSpot CRM
from cuitonline_scraper import CUITOnlineScraper
from hubspot_api import HubSpotClient

def enrich_hubspot_with_cuit():
    scraper = CUITOnlineScraper(method="playwright")
    hubspot = HubSpotClient()
    
    # Get companies without CUIT
    companies = hubspot.get_companies_without_cuit()
    
    for company in companies:
        # Search by company name
        results = scraper.search_by_name(company['name'])
        
        if results:
            # Update HubSpot with CUIT
            hubspot.update_company(company['id'], {
                'cuit_numero': results[0].cuit,
                'condicion_fiscal': results[0].condicion_impositiva,
                'cuit_verified': True
            })
```

## Handling Common Issues

### Ad Blocker Detection

The site may detect and block access if it thinks you're using an ad blocker. The scraper handles this automatically, but if issues persist:

```python
# Use Playwright with stealth mode
scraper = CUITOnlineScraper(method="playwright", headless=False)  # Run with GUI

# Or add custom headers
scraper.session.headers.update({
    'Referer': 'https://www.google.com/',
    'Cache-Control': 'no-cache'
})
```

### Rate Limiting

The scraper includes automatic rate limiting. Adjust if needed:

```python
scraper = CUITOnlineScraper(method="requests")
scraper.min_request_interval = 5.0  # 5 seconds between requests
```

### No Results Found

If searches return no results:

1. **Check the search term**: Try variations of the name
2. **Use different method**: Switch from requests to Selenium/Playwright
3. **Check site changes**: The site structure may have changed

## API Usage (Programmatic)

```python
from cuitonline_scraper import CUITOnlineScraper, CUITResult

class CUITEnrichmentService:
    def __init__(self):
        self.scraper = CUITOnlineScraper(method="playwright")
    
    def find_cuit(self, name: str) -> Optional[str]:
        """Find CUIT for a given name"""
        results = self.scraper.search_by_name(name)
        return results[0].cuit if results else None
    
    def get_company_info(self, name: str) -> Dict:
        """Get complete company information"""
        results = self.scraper.search_by_name(name)
        
        if not results:
            return None
        
        # Get detailed info if available
        if results[0].detail_url:
            details = self.scraper.get_cuit_details(results[0].detail_url)
            if details:
                return {
                    'cuit': details.cuit,
                    'legal_name': details.name,
                    'type': details.tipo_persona,
                    'status': details.estado,
                    'address': details.direccion,
                    'city': details.localidad,
                    'province': details.provincia,
                    'tax_status': details.condicion_impositiva,
                    'activities': details.actividades
                }
        
        return {
            'cuit': results[0].cuit,
            'legal_name': results[0].name,
            'type': results[0].tipo_persona,
            'status': results[0].estado
        }
```

## Best Practices

1. **Respect Rate Limits**: Don't make requests too quickly
2. **Use Appropriate Method**: 
   - `requests`: Fast, but may miss JavaScript content
   - `selenium`: Good compatibility, but slower
   - `playwright`: Best for automation, modern and fast
3. **Handle Errors Gracefully**: Always check if results exist
4. **Export Data Regularly**: Save results to avoid re-scraping
5. **Monitor Changes**: The site structure may change over time

## Troubleshooting

### ImportError: No module named 'selenium'
```bash
pip install selenium
```

### ChromeDriver not found
```bash
# macOS
brew install chromedriver

# Ubuntu
sudo apt-get install chromium-chromedriver

# Or download manually from https://chromedriver.chromium.org/
```

### Playwright browsers not installed
```bash
playwright install chromium
playwright install-deps  # Linux only
```

### No results returned
- Try different search terms
- Switch to Selenium or Playwright method
- Check if the site is accessible in your browser
- Verify the site structure hasn't changed

## Legal Considerations

- Respect the website's terms of service
- Don't overload the server with requests
- Use the data responsibly and in compliance with privacy laws
- Consider caching results to minimize requests

## Performance Tips

1. **Use Headless Mode**: Faster and uses less resources
2. **Batch Searches**: Group multiple searches together
3. **Cache Results**: Store results locally to avoid re-scraping
4. **Use Appropriate Method**: `requests` is fastest, use others only when needed

## Example Output

```json
{
  "cuit": "20-12345678-9",
  "name": "VERDIER PIAZZA JUAN",
  "tipo_persona": "Persona Física",
  "estado": "ACTIVO",
  "direccion": "AV. CORRIENTES 1234",
  "localidad": "CIUDAD AUTONOMA BUENOS AIRES",
  "provincia": "CAPITAL FEDERAL",
  "condicion_impositiva": "RESPONSABLE INSCRIPTO",
  "actividades": [
    "SERVICIOS DE CONSULTORIA",
    "ACTIVIDADES PROFESIONALES"
  ],
  "search_url": "https://www.cuitonline.com/search/verdier%20piazza",
  "detail_url": "https://www.cuitonline.com/detalle/20123456789/verdier-piazza-juan.html"
}
```

## Advanced Configuration

### Custom Headers
```python
scraper = CUITOnlineScraper()
scraper.session.headers.update({
    'Custom-Header': 'value'
})
```

### Proxy Support
```python
scraper = CUITOnlineScraper()
scraper.session.proxies = {
    'http': 'http://proxy.example.com:8080',
    'https': 'https://proxy.example.com:8080'
}
```

### Custom Timeout
```python
scraper = CUITOnlineScraper()
scraper.session.timeout = 60  # 60 seconds
```

## Contributing

Feel free to improve the scraper by:
- Adding new extraction patterns
- Improving error handling
- Adding support for more browsers
- Enhancing the parsing logic

## Disclaimer

This scraper is for educational and legitimate business purposes only. Always respect the website's terms of service and robots.txt file. The authors are not responsible for any misuse of this tool.