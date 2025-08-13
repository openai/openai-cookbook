#!/bin/bash
# Setup script for CUIT scraping tools

echo "==================================="
echo "CUIT Scraping Tools Setup"
echo "==================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "Python version:"
python3 --version
echo

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv cuit_scraper_env

# Activate virtual environment
echo "Activating virtual environment..."
source cuit_scraper_env/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install basic requirements
echo "Installing basic requirements..."
pip install requests beautifulsoup4 lxml

# Ask about optional dependencies
echo
read -p "Install Selenium for JavaScript support? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing Selenium..."
    pip install selenium
    
    echo
    echo "Note: You'll need to install ChromeDriver separately:"
    echo "  - macOS: brew install chromedriver"
    echo "  - Ubuntu: sudo apt-get install chromium-chromedriver"
    echo "  - Windows: Download from https://chromedriver.chromium.org/"
fi

echo
read -p "Install Playwright for modern web automation? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing Playwright..."
    pip install playwright
    
    echo "Installing Playwright browsers..."
    playwright install chromium
    
    # Check if on Linux and install dependencies
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Installing system dependencies for Playwright..."
        playwright install-deps
    fi
fi

# Install pandas for data export
echo
echo "Installing pandas for data export..."
pip install pandas

# Create outputs directory
echo "Creating outputs directory..."
mkdir -p outputs

echo
echo "==================================="
echo "Setup complete!"
echo "==================================="
echo
echo "To use the tools:"
echo "1. Activate the virtual environment:"
echo "   source cuit_scraper_env/bin/activate"
echo
echo "2. Run the scraper:"
echo "   python cuitonline_scraper.py"
echo
echo "3. Or use the GUI:"
echo "   python cuit_lookup_gui.py"
echo
echo "4. For automated enrichment:"
echo "   python automated_cuit_enrichment.py --help"
echo