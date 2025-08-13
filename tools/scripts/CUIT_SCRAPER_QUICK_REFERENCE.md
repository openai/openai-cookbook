# CUIT Web Scraper - Quick Reference

## 🚀 Installation (5 minutes)

```bash
cd tools/scripts
./setup_scraping_tools.sh
# Choose options when prompted
```

## 🎯 Quick Usage

### Option 1: GUI (Easiest)
```bash
python cuit_lookup_gui.py
```
- Type name → Click Search → Export results

### Option 2: Command Line
```python
# test_example.py
from cuitonline_scraper import CUITOnlineScraper

scraper = CUITOnlineScraper()
results = scraper.search_by_name("verdier piazza")

for r in results:
    print(f"{r.cuit}: {r.name}")
```

### Option 3: Automated HubSpot Update
```bash
python automated_cuit_enrichment.py --limit 50
```

## 📋 Common Commands

```bash
# Test if everything works
python test_cuit_scraper.py

# Search single company
python -c "from cuitonline_scraper import CUITOnlineScraper; s=CUITOnlineScraper(); print(s.search_by_name('empresa ejemplo'))"

# Batch search with export
python automated_cuit_enrichment.py --dry-run --limit 10

# Use advanced scraping (Playwright)
python automated_cuit_enrichment.py --method playwright --limit 100
```

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| No results found | Try partial name, remove "S.A.", "SRL" |
| Import error | Run `pip install requests beautifulsoup4` |
| Selenium error | Install with `pip install selenium` |
| Playwright error | Run `playwright install chromium` |
| Rate limit | Increase delay: `scraper.min_request_interval = 5` |

## 📁 Files Created

- `cuitonline_scraper.py` - Core library
- `cuit_lookup_gui.py` - Desktop GUI app
- `automated_cuit_enrichment.py` - HubSpot integration
- `test_cuit_scraper.py` - Test script
- `outputs/` - Results directory

## 💡 Pro Tips

1. **Start Simple**: Use requests method first
2. **GUI for Manual**: Best for occasional lookups
3. **Automate Bulk**: Use scripts for 100+ companies
4. **Cache Results**: Avoid re-scraping same data
5. **Rate Limit**: 2-5 seconds between requests

## 📞 Need Help?

1. Run test script: `python test_cuit_scraper.py`
2. Check full guide: `CUIT_SCRAPING_COMPLETE_GUIDE.md`
3. Enable debug: Add `logging.basicConfig(level=logging.DEBUG)`

---
*Created for Colppy CRM CUIT enrichment project*