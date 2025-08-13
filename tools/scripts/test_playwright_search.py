#!/usr/bin/env python3
"""
Test CUIT scraper with Playwright method for better JavaScript handling
"""

from cuitonline_scraper import CUITOnlineScraper
import json

def test_with_playwright():
    """Test searching with Playwright for better results"""
    
    print("=" * 60)
    print("Testing CUIT Scraper with Playwright")
    print("Searching for: Estudio Carballeira")
    print("=" * 60)
    
    # Initialize with Playwright
    scraper = CUITOnlineScraper(method="playwright", headless=True)
    
    search_terms = [
        "Estudio Carballeira",
        "Carballeira",
        "Estudio Contable Carballeira",
        "Carballeira Contador",
        "Contador Carballeira"
    ]
    
    all_results = []
    
    for search_term in search_terms:
        print(f"\n🔍 Searching for: {search_term}")
        
        try:
            results = scraper.search_by_name(search_term)
            
            if results:
                print(f"✅ Found {len(results)} result(s)!")
                all_results.extend(results)
                
                for i, result in enumerate(results[:5], 1):  # Show max 5 results per search
                    print(f"\n  Result #{i}:")
                    print(f"    CUIT: {result.cuit}")
                    print(f"    Name: {result.name}")
                    print(f"    Type: {result.tipo_persona}")
                    print(f"    Status: {result.estado}")
                    
                    if result.detail_url:
                        print(f"    URL: {result.detail_url}")
                        
                        # Try to get more details if URL is available
                        try:
                            details = scraper.get_cuit_details(result.detail_url)
                            if details:
                                if details.direccion:
                                    print(f"    Address: {details.direccion}")
                                if details.localidad:
                                    print(f"    City: {details.localidad}")
                                if details.provincia:
                                    print(f"    Province: {details.provincia}")
                        except:
                            pass
                
                if len(results) > 5:
                    print(f"\n  ... and {len(results) - 5} more results")
                    
            else:
                print("❌ No results found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Export all unique results
    if all_results:
        # Remove duplicates based on CUIT
        unique_results = []
        seen_cuits = set()
        
        for result in all_results:
            if result.cuit not in seen_cuits:
                seen_cuits.add(result.cuit)
                unique_results.append(result)
        
        print(f"\n📊 Total unique results found: {len(unique_results)}")
        
        # Export results
        print("\n💾 Exporting results...")
        scraper.export_results(unique_results, "carballeira_playwright_results")
        print("✅ Results exported to outputs/ directory")
        
        # Show summary
        print("\n📋 Summary of found CUITs:")
        for result in unique_results:
            print(f"  - {result.cuit}: {result.name}")
    else:
        print("\n❌ No results found with any search term")
        print("\nPossible reasons:")
        print("1. The accountant might not be registered on cuitonline.com")
        print("2. The name might be registered differently")
        print("3. Try searching with just the last name or variations")


def test_direct_cuit():
    """Test if we can search by a known CUIT if you have one"""
    print("\n" + "=" * 60)
    print("Alternative: Direct CUIT Search")
    print("=" * 60)
    
    print("\nIf you have a specific CUIT number, you can search directly.")
    print("For example, if the CUIT is 20-12345678-9, you can:")
    print()
    print("scraper = CUITOnlineScraper()")
    print('results = scraper.search_by_name("20-12345678-9")')
    print()
    print("Or use the GUI for easier searching:")
    print("python cuit_lookup_gui.py")


if __name__ == "__main__":
    test_with_playwright()
    test_direct_cuit()
    
    print("\n" + "=" * 60)
    print("Additional Options:")
    print("=" * 60)
    print("\n1. Use the GUI for manual search:")
    print("   python cuit_lookup_gui.py")
    print("\n2. Try with Selenium (alternative method):")
    print("   pip install selenium")
    print("   Then use method='selenium' in the scraper")
    print("\n3. Check the official AFIP API option:")
    print("   See afip_cuit_lookup.py for government data access")