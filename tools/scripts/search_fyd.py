#!/usr/bin/env python3
"""
Search for Estudio FyD - Fratantoni, Diez & Asociados
"""

import sys
from cuitonline_scraper import CUITOnlineScraper
import json

def search_firm(name):
    """Search for a firm by name and display results"""
    
    print("=" * 70)
    print(f"Searching for: {name}")
    print("=" * 70)
    
    # Initialize scraper with Playwright for better results
    scraper = CUITOnlineScraper(method="playwright", headless=True)
    
    # Try different variations of the name
    search_variations = [
        name,  # Full name as provided
        "Fratantoni Diez Asociados",  # Without special characters
        "Fratantoni Diez",  # Shorter version
        "FyD Fratantoni",  # Alternative order
        "Estudio FyD",  # Just the beginning
        "Fratantoni",  # Just the main name
        "FYD",  # Just the acronym
        "F&D",  # Alternative acronym
    ]
    
    all_results = []
    unique_cuits = set()
    
    for variation in search_variations:
        print(f"\n🔍 Trying: {variation}")
        
        try:
            results = scraper.search_by_name(variation)
            
            if results:
                print(f"✅ Found {len(results)} result(s)")
                
                # Add unique results
                for result in results:
                    if result.cuit not in unique_cuits:
                        unique_cuits.add(result.cuit)
                        all_results.append(result)
                        
                        # Display first few results
                        if len([r for r in results if r.cuit == result.cuit]) > 0:
                            print(f"    CUIT: {result.cuit}")
                            print(f"    Name: {result.name}")
                            if result.tipo_persona != "Unknown":
                                print(f"    Type: {result.tipo_persona}")
                            if result.estado != "Unknown":
                                print(f"    Status: {result.estado}")
            else:
                print("❌ No results")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if all_results:
        print(f"\n✅ Total unique CUITs found: {len(all_results)}")
        print("\nAll unique results:")
        
        for i, result in enumerate(all_results, 1):
            print(f"\n{i}. CUIT: {result.cuit}")
            print(f"   Name: {result.name}")
            print(f"   Search URL: {result.search_url}")
            
        # Export results
        print("\n💾 Exporting results...")
        scraper.export_results(all_results, "fyd_fratantoni_results")
        print("✅ Results exported to outputs/fyd_fratantoni_results.*")
        
        # Also create a detailed JSON
        detailed_results = []
        for result in all_results:
            detailed_results.append({
                'cuit': result.cuit,
                'name': result.name,
                'tipo_persona': result.tipo_persona,
                'estado': result.estado,
                'direccion': result.direccion,
                'localidad': result.localidad,
                'provincia': result.provincia,
                'condicion_impositiva': result.condicion_impositiva,
                'search_variation': 'Multiple variations tested'
            })
        
        print("\nDetailed JSON:")
        print(json.dumps(detailed_results, indent=2, ensure_ascii=False))
        
    else:
        print("\n❌ No CUITs found for any variation")
        print("\nPossible reasons:")
        print("1. The firm might be registered under a different name")
        print("2. The firm might not be listed on cuitonline.com")
        print("3. Try searching with individual partner names")
        
        # Based on the website info, suggest searching for partners
        print("\nFrom their website (www.fyd.com.ar), you might try searching for:")
        print("- Individual partner names (socios)")
        print("- The address: Av. Leandro N. Alem 1026, Buenos Aires")


if __name__ == "__main__":
    # Get the firm name from command line argument or use default
    if len(sys.argv) > 1:
        firm_name = " ".join(sys.argv[1:])
    else:
        firm_name = "Estudio FyD - Fratantoni, Diez & Asociados"
    
    search_firm(firm_name)