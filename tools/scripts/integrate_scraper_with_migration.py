#!/usr/bin/env python3
"""
Integration Example: Web Scraper + CUIT Migration
Shows how to combine web scraping with the existing migration workflow
"""

import sys
import os
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing migration tools
from complete_july_2025_cuit_migration import (
    is_valid_cuit, clean_cuit, load_colppy_empresas,
    get_hubspot_deals_data, process_cuit_mapping
)

# Import scraping tools
from scripts.cuitonline_scraper import CUITOnlineScraper
from scripts.afip_cuit_lookup import AFIPCUITLookupService


class EnhancedCUITMigrationWithScraping:
    """Enhanced migration that combines multiple data sources"""
    
    def __init__(self):
        # Initialize scrapers
        self.web_scraper = CUITOnlineScraper(method="playwright", headless=True)
        self.afip_service = None
        
        # Try to initialize AFIP service
        try:
            self.afip_service = AFIPCUITLookupService()
            print("✓ AFIP service available")
        except:
            print("⚠ AFIP service not available (continuing with web scraping only)")
    
    def find_missing_cuits(self, companies: List[Dict]) -> List[Dict]:
        """
        Find CUITs for companies that don't have them
        
        Args:
            companies: List of company dictionaries
            
        Returns:
            List of companies with found CUITs
        """
        missing_cuit_companies = []
        
        for company in companies:
            if not company.get('cuit') or not is_valid_cuit(company.get('cuit', '')):
                missing_cuit_companies.append(company)
        
        print(f"Found {len(missing_cuit_companies)} companies without valid CUIT")
        return missing_cuit_companies
    
    def search_cuit_for_company(self, company: Dict) -> Optional[str]:
        """
        Search for company CUIT using multiple sources
        
        Args:
            company: Company dictionary
            
        Returns:
            CUIT if found, None otherwise
        """
        company_name = company.get('name', '')
        if not company_name:
            return None
        
        print(f"Searching CUIT for: {company_name}")
        
        # Method 1: Try web scraping first
        try:
            results = self.web_scraper.search_by_name(company_name)
            if results:
                # Validate and return first valid CUIT
                for result in results:
                    if is_valid_cuit(result.cuit):
                        print(f"  Found via web scraping: {result.cuit}")
                        return clean_cuit(result.cuit)
        except Exception as e:
            print(f"  Web scraping error: {e}")
        
        # Method 2: Try AFIP API if available
        if self.afip_service and company.get('potential_cuit'):
            try:
                afip_result = self.afip_service.lookup_cuit(company['potential_cuit'])
                if afip_result and not afip_result.error:
                    print(f"  Validated via AFIP: {afip_result.cuit}")
                    return clean_cuit(afip_result.cuit)
            except Exception as e:
                print(f"  AFIP lookup error: {e}")
        
        print(f"  No CUIT found for {company_name}")
        return None
    
    def run_enhanced_migration(self):
        """Run the enhanced migration with web scraping"""
        print("Starting Enhanced CUIT Migration with Web Scraping")
        print("=" * 60)
        
        # Step 1: Load data using existing functions
        print("Loading Colppy empresas...")
        empresas = load_colppy_empresas()
        
        print("Loading HubSpot deals...")
        deals_data = get_hubspot_deals_data()
        
        # Step 2: Process existing mappings
        print("Processing existing CUIT mappings...")
        mapping_results = process_cuit_mapping(empresas, deals_data)
        
        # Step 3: Find companies still missing CUITs
        companies_to_update = mapping_results.get('updates_to_apply', [])
        missing_cuit_companies = self.find_missing_cuits(companies_to_update)
        
        # Step 4: Search for missing CUITs
        print(f"\nSearching for {len(missing_cuit_companies)} missing CUITs...")
        found_cuits = 0
        
        for i, company in enumerate(missing_cuit_companies, 1):
            print(f"\nProcessing {i}/{len(missing_cuit_companies)}")
            
            cuit = self.search_cuit_for_company(company)
            if cuit:
                company['cuit'] = cuit
                company['cuit_source'] = 'web_scraping'
                found_cuits += 1
        
        # Step 5: Update results
        print(f"\nFound {found_cuits} additional CUITs via web scraping")
        
        # Update the mapping results
        enhanced_results = mapping_results.copy()
        enhanced_results['web_scraping_results'] = {
            'companies_searched': len(missing_cuit_companies),
            'cuits_found': found_cuits,
            'success_rate': (found_cuits / len(missing_cuit_companies) * 100) if missing_cuit_companies else 0
        }
        
        return enhanced_results
    
    def export_enhanced_results(self, results: Dict):
        """Export enhanced results with web scraping data"""
        from datetime import datetime
        import json
        import csv
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export JSON report
        json_file = f"outputs/enhanced_migration_{timestamp}.json"
        os.makedirs('outputs', exist_ok=True)
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # Export CSV with all companies
        csv_file = f"outputs/enhanced_migration_companies_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'company_id', 'company_name', 'cuit', 'cuit_source',
                'is_valid', 'needs_update'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for update in results.get('updates_to_apply', []):
                writer.writerow({
                    'company_id': update.get('company_id'),
                    'company_name': update.get('company_name'),
                    'cuit': update.get('cuit'),
                    'cuit_source': update.get('cuit_source', 'colppy'),
                    'is_valid': is_valid_cuit(update.get('cuit', '')),
                    'needs_update': update.get('needs_update', True)
                })
        
        print(f"\nResults exported to:")
        print(f"- {json_file}")
        print(f"- {csv_file}")


def main():
    """Main execution"""
    try:
        # Create enhanced migration instance
        migration = EnhancedCUITMigrationWithScraping()
        
        # Run the migration
        results = migration.run_enhanced_migration()
        
        # Print summary
        print("\n" + "=" * 60)
        print("ENHANCED MIGRATION SUMMARY")
        print("=" * 60)
        
        # Original migration stats
        print(f"Companies processed: {results['summary']['total_companies']}")
        print(f"Valid CUITs found: {results['summary']['valid_cuits']}")
        print(f"Invalid CUITs: {results['summary']['invalid_cuits']}")
        
        # Web scraping stats
        if 'web_scraping_results' in results:
            ws_results = results['web_scraping_results']
            print(f"\nWeb Scraping Results:")
            print(f"- Companies searched: {ws_results['companies_searched']}")
            print(f"- CUITs found: {ws_results['cuits_found']}")
            print(f"- Success rate: {ws_results['success_rate']:.1f}%")
        
        # Export results
        migration.export_enhanced_results(results)
        
        print("\n✅ Enhanced migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Enhanced CUIT Migration with Web Scraping")
    print("This combines the existing migration with web scraping capabilities")
    print()
    
    # Check dependencies
    print("Checking dependencies...")
    try:
        from cuitonline_scraper import CUITOnlineScraper
        print("✓ Web scraper available")
    except ImportError:
        print("✗ Web scraper not found. Run: pip install requests beautifulsoup4")
        sys.exit(1)
    
    print()
    
    # Ask for confirmation
    response = input("Continue with enhanced migration? (y/n): ")
    if response.lower() == 'y':
        main()
    else:
        print("Migration cancelled.")