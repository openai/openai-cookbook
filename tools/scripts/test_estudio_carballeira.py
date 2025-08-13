#!/usr/bin/env python3
"""
Test the CUIT scraper with a specific accountant name: Estudio Carballeira
"""

from cuitonline_scraper import CUITOnlineScraper
import json

def test_search():
    """Test searching for Estudio Carballeira"""
    
    print("=" * 60)
    print("Testing CUIT Scraper with: Estudio Carballeira")
    print("=" * 60)
    
    # Initialize the scraper with requests method (basic, fast)
    scraper = CUITOnlineScraper(method="requests")
    
    # Search for the accountant
    search_term = "Estudio Carballeira"
    print(f"\nSearching for: {search_term}")
    print("Method: requests (basic HTML parsing)")
    print()
    
    try:
        # Perform the search
        results = scraper.search_by_name(search_term)
        
        if results:
            print(f"✅ Found {len(results)} result(s)!\n")
            
            # Display each result
            for i, result in enumerate(results, 1):
                print(f"Result #{i}:")
                print(f"  CUIT: {result.cuit}")
                print(f"  Name: {result.name}")
                print(f"  Type: {result.tipo_persona}")
                print(f"  Status: {result.estado}")
                
                if result.direccion:
                    print(f"  Address: {result.direccion}")
                if result.localidad:
                    print(f"  City: {result.localidad}")
                if result.provincia:
                    print(f"  Province: {result.provincia}")
                if result.condicion_impositiva:
                    print(f"  Tax Status: {result.condicion_impositiva}")
                if result.detail_url:
                    print(f"  Detail URL: {result.detail_url}")
                
                print("-" * 40)
            
            # Export results
            print("\nExporting results...")
            scraper.export_results(results, "estudio_carballeira_results")
            print("✅ Results exported to outputs/ directory")
            
            # Also save as JSON for inspection
            json_data = []
            for result in results:
                json_data.append({
                    'cuit': result.cuit,
                    'name': result.name,
                    'tipo_persona': result.tipo_persona,
                    'estado': result.estado,
                    'direccion': result.direccion,
                    'localidad': result.localidad,
                    'provincia': result.provincia,
                    'condicion_impositiva': result.condicion_impositiva,
                    'search_url': result.search_url,
                    'detail_url': result.detail_url
                })
            
            print("\nJSON representation:")
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
            
        else:
            print("❌ No results found")
            print("\nPossible reasons:")
            print("1. The name might need to be more specific or less specific")
            print("2. The website structure might have changed")
            print("3. The accountant might not be listed on cuitonline.com")
            print("\nTrying alternative search variations...")
            
            # Try alternative searches
            alternatives = [
                "Carballeira",
                "Estudio Contable Carballeira",
                "Carballeira Estudio"
            ]
            
            for alt in alternatives:
                print(f"\nTrying: {alt}")
                alt_results = scraper.search_by_name(alt)
                if alt_results:
                    print(f"  ✅ Found {len(alt_results)} result(s) with '{alt}'")
                    for r in alt_results[:3]:  # Show first 3
                        print(f"    - {r.cuit}: {r.name}")
                else:
                    print(f"  ❌ No results with '{alt}'")
                    
    except Exception as e:
        print(f"❌ Error during search: {e}")
        print("\nError details:")
        import traceback
        traceback.print_exc()
        
        print("\nTroubleshooting:")
        print("1. Check internet connection")
        print("2. The website might be temporarily down")
        print("3. The website structure might have changed")
        print("4. Try using Selenium or Playwright methods for better compatibility")


if __name__ == "__main__":
    test_search()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nNext steps:")
    print("1. If no results, try the GUI: python cuit_lookup_gui.py")
    print("2. For JavaScript-heavy pages: Use method='selenium' or 'playwright'")
    print("3. Check the outputs/ directory for exported results")
    print("=" * 60)