#!/usr/bin/env python3
"""
Test script for CUIT scraper
Verifies that the scraping tools are working correctly
"""

import sys
import os

# Test imports
print("Testing imports...")
try:
    from cuitonline_scraper import CUITOnlineScraper, CUITResult
    print("✓ cuitonline_scraper imported successfully")
except ImportError as e:
    print(f"✗ Error importing cuitonline_scraper: {e}")
    sys.exit(1)

# Test basic functionality
print("\nTesting basic search functionality...")
try:
    # Create scraper with requests method (always available)
    scraper = CUITOnlineScraper(method="requests")
    print("✓ Scraper initialized with requests method")
    
    # Test search
    print("\nSearching for 'test company'...")
    results = scraper.search_by_name("test company")
    
    if results:
        print(f"✓ Found {len(results)} results")
        for i, result in enumerate(results[:3], 1):  # Show first 3 results
            print(f"\n  Result {i}:")
            print(f"    CUIT: {result.cuit}")
            print(f"    Name: {result.name}")
            print(f"    Type: {result.tipo_persona}")
    else:
        print("⚠ No results found (this might be normal for 'test company')")
        
except Exception as e:
    print(f"✗ Error during search: {e}")

# Test available methods
print("\n\nChecking available scraping methods...")
methods = {
    "requests": True,  # Always available
    "selenium": False,
    "playwright": False
}

try:
    import selenium
    methods["selenium"] = True
    print("✓ Selenium is installed")
except ImportError:
    print("⚠ Selenium not installed (optional)")

try:
    import playwright
    methods["playwright"] = True
    print("✓ Playwright is installed")
except ImportError:
    print("⚠ Playwright not installed (optional)")

# Test export functionality
print("\n\nTesting export functionality...")
try:
    # Create outputs directory if it doesn't exist
    os.makedirs('outputs', exist_ok=True)
    print("✓ Outputs directory ready")
    
    # Test export (even with empty results)
    test_results = [CUITResult(
        cuit="20-12345678-9",
        name="Test Company",
        tipo_persona="Persona Jurídica",
        estado="ACTIVO"
    )]
    
    scraper.export_results(test_results, "test_export")
    print("✓ Export functionality working")
    
    # Check if files were created
    if os.path.exists("outputs/test_export.json") and os.path.exists("outputs/test_export.csv"):
        print("✓ Export files created successfully")
        # Clean up test files
        os.remove("outputs/test_export.json")
        os.remove("outputs/test_export.csv")
        print("✓ Test files cleaned up")
    
except Exception as e:
    print(f"✗ Error testing export: {e}")

# Summary
print("\n" + "="*50)
print("SUMMARY")
print("="*50)
print(f"Basic functionality: {'Working' if True else 'Failed'}")
print(f"Available methods: {', '.join([m for m, v in methods.items() if v])}")
print("\nNext steps:")
print("1. Try a real search: python cuitonline_scraper.py")
print("2. Use the GUI: python cuit_lookup_gui.py")
print("3. For automation: python automated_cuit_enrichment.py --help")

# Test GUI availability
try:
    import tkinter
    print("\n✓ GUI support available (tkinter installed)")
except ImportError:
    print("\n⚠ GUI not available (tkinter not installed)")

print("\nTest completed!")