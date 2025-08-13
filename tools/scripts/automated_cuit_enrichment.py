#!/usr/bin/env python3
"""
Automated CUIT Enrichment Pipeline
Combines web scraping from cuitonline.com with HubSpot CRM updates

This script automates the process of:
1. Finding companies in HubSpot that need CUIT information
2. Searching for their CUITs on cuitonline.com
3. Updating HubSpot with the found information
"""

import os
import sys
import json
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from cuitonline_scraper import CUITOnlineScraper, CUITResult
    from hubspot_api.client import HubSpotClient
    from afip_cuit_lookup import AFIPCUITLookupService
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all required modules are installed")
    sys.exit(1)


class AutomatedCUITEnrichment:
    """Automated pipeline for CUIT enrichment"""
    
    def __init__(self, 
                 scraper_method: str = "playwright",
                 use_afip_validation: bool = False,
                 dry_run: bool = False):
        """
        Initialize the enrichment pipeline
        
        Args:
            scraper_method: Method for web scraping ("requests", "selenium", "playwright")
            use_afip_validation: Whether to validate CUITs with AFIP API
            dry_run: If True, don't update HubSpot, just show what would be done
        """
        self.scraper = CUITOnlineScraper(method=scraper_method, headless=True)
        self.hubspot = HubSpotClient()
        self.afip_service = None
        self.dry_run = dry_run
        
        if use_afip_validation:
            try:
                self.afip_service = AFIPCUITLookupService()
                logging.info("AFIP validation service initialized")
            except Exception as e:
                logging.warning(f"AFIP service not available: {e}")
        
        # Setup logging
        log_filename = f"cuit_enrichment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f"outputs/{log_filename}"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.stats = {
            'companies_processed': 0,
            'cuits_found': 0,
            'cuits_validated': 0,
            'hubspot_updated': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
    
    def find_companies_needing_cuit(self, limit: int = 100) -> List[Dict]:
        """
        Find HubSpot companies that need CUIT information
        
        Args:
            limit: Maximum number of companies to process
            
        Returns:
            List of company dictionaries
        """
        self.logger.info("Finding companies without CUIT...")
        
        try:
            # Search for companies without CUIT
            filter_groups = [{
                "filters": [
                    {
                        "propertyName": "name",
                        "operator": "HAS_PROPERTY"
                    },
                    {
                        "propertyName": "cuit_numero",
                        "operator": "NOT_HAS_PROPERTY"
                    }
                ]
            }]
            
            properties = [
                "hs_object_id",
                "name",
                "cuit_numero",
                "domain",
                "address",
                "city",
                "state"
            ]
            
            response = self.hubspot.client.crm.companies.search_api.do_search(
                public_object_search_request={
                    "filterGroups": filter_groups,
                    "properties": properties,
                    "limit": limit
                }
            )
            
            companies = []
            for company in response.results:
                companies.append({
                    'id': company.id,
                    'name': company.properties.get('name', ''),
                    'domain': company.properties.get('domain', ''),
                    'address': company.properties.get('address', ''),
                    'city': company.properties.get('city', ''),
                    'state': company.properties.get('state', '')
                })
            
            self.logger.info(f"Found {len(companies)} companies without CUIT")
            return companies
            
        except Exception as e:
            self.logger.error(f"Error finding companies: {e}")
            return []
    
    def search_cuit_for_company(self, company: Dict) -> Optional[CUITResult]:
        """
        Search for a company's CUIT on cuitonline.com
        
        Args:
            company: Company dictionary with name and other info
            
        Returns:
            CUITResult if found, None otherwise
        """
        company_name = company.get('name', '')
        if not company_name:
            return None
        
        self.logger.info(f"Searching CUIT for: {company_name}")
        
        # Try different search variations
        search_variations = [
            company_name,  # Full name
            company_name.split(' S.A.')[0] if ' S.A.' in company_name else None,
            company_name.split(' SRL')[0] if ' SRL' in company_name else None,
            company_name.split(' S.R.L.')[0] if ' S.R.L.' in company_name else None,
            ' '.join(company_name.split()[:2])  # First two words
        ]
        
        # Remove None values and duplicates
        search_variations = list(filter(None, dict.fromkeys(search_variations)))
        
        for search_term in search_variations:
            try:
                results = self.scraper.search_by_name(search_term)
                
                if results:
                    # Try to match by name similarity
                    best_match = self._find_best_match(results, company_name)
                    if best_match:
                        self.logger.info(f"Found CUIT {best_match.cuit} for {company_name}")
                        return best_match
                        
            except Exception as e:
                self.logger.error(f"Error searching for {search_term}: {e}")
        
        self.logger.warning(f"No CUIT found for {company_name}")
        return None
    
    def _find_best_match(self, results: List[CUITResult], company_name: str) -> Optional[CUITResult]:
        """Find the best matching result based on name similarity"""
        if not results:
            return None
        
        # If only one result, return it
        if len(results) == 1:
            return results[0]
        
        # Simple name matching
        company_name_upper = company_name.upper().strip()
        
        for result in results:
            result_name_upper = result.name.upper().strip()
            
            # Exact match
            if company_name_upper == result_name_upper:
                return result
            
            # Contains match
            if company_name_upper in result_name_upper or result_name_upper in company_name_upper:
                return result
        
        # Return first result if no good match
        return results[0]
    
    def validate_cuit_with_afip(self, cuit: str) -> bool:
        """
        Validate CUIT with AFIP if service is available
        
        Args:
            cuit: CUIT to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not self.afip_service:
            return True  # Skip validation if service not available
        
        try:
            result = self.afip_service.lookup_cuit(cuit)
            return result and not result.error
        except Exception as e:
            self.logger.warning(f"AFIP validation failed for {cuit}: {e}")
            return True  # Don't block on AFIP errors
    
    def update_company_with_cuit(self, company_id: str, cuit_result: CUITResult) -> bool:
        """
        Update HubSpot company with CUIT information
        
        Args:
            company_id: HubSpot company ID
            cuit_result: CUIT search result
            
        Returns:
            True if updated successfully
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would update company {company_id} with CUIT {cuit_result.cuit}")
            return True
        
        try:
            properties = {
                'cuit_numero': cuit_result.cuit,
                'cuit_source': 'cuitonline.com',
                'cuit_search_date': datetime.now().isoformat()
            }
            
            # Add additional information if available
            if cuit_result.tipo_persona:
                properties['tipo_persona'] = cuit_result.tipo_persona
            
            if cuit_result.estado:
                properties['cuit_estado'] = cuit_result.estado
            
            if cuit_result.condicion_impositiva:
                properties['condicion_fiscal'] = cuit_result.condicion_impositiva
            
            if cuit_result.direccion:
                properties['cuit_direccion'] = cuit_result.direccion
            
            if cuit_result.localidad:
                properties['cuit_localidad'] = cuit_result.localidad
            
            if cuit_result.provincia:
                properties['cuit_provincia'] = cuit_result.provincia
            
            # Validate with AFIP if enabled
            if self.afip_service:
                is_valid = self.validate_cuit_with_afip(cuit_result.cuit)
                properties['afip_validated'] = is_valid
                if is_valid:
                    self.stats['cuits_validated'] += 1
            
            # Update HubSpot
            self.hubspot.client.crm.companies.basic_api.update(
                company_id=company_id,
                simple_public_object_input={"properties": properties}
            )
            
            self.logger.info(f"Updated company {company_id} with CUIT {cuit_result.cuit}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating company {company_id}: {e}")
            return False
    
    def process_companies(self, companies: List[Dict] = None, limit: int = 100):
        """
        Main processing function
        
        Args:
            companies: List of companies to process (if None, will find automatically)
            limit: Maximum number of companies to process
        """
        self.logger.info("Starting automated CUIT enrichment")
        
        # Get companies if not provided
        if not companies:
            companies = self.find_companies_needing_cuit(limit)
        
        if not companies:
            self.logger.info("No companies to process")
            return
        
        # Process each company
        for i, company in enumerate(companies, 1):
            self.logger.info(f"Processing {i}/{len(companies)}: {company['name']}")
            self.stats['companies_processed'] += 1
            
            try:
                # Search for CUIT
                cuit_result = self.search_cuit_for_company(company)
                
                if cuit_result:
                    self.stats['cuits_found'] += 1
                    
                    # Update HubSpot
                    if self.update_company_with_cuit(company['id'], cuit_result):
                        self.stats['hubspot_updated'] += 1
                    else:
                        self.stats['errors'] += 1
                        
            except Exception as e:
                self.logger.error(f"Error processing company {company['name']}: {e}")
                self.stats['errors'] += 1
            
            # Progress update
            if i % 10 == 0:
                self._print_progress()
        
        # Final summary
        self._print_final_summary()
    
    def _print_progress(self):
        """Print progress statistics"""
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        rate = self.stats['companies_processed'] / elapsed if elapsed > 0 else 0
        
        self.logger.info(
            f"Progress: {self.stats['companies_processed']} processed, "
            f"{self.stats['cuits_found']} found, "
            f"{self.stats['hubspot_updated']} updated "
            f"({rate:.2f} companies/sec)"
        )
    
    def _print_final_summary(self):
        """Print final summary"""
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        
        summary = f"""
========================================
CUIT Enrichment Summary
========================================
Total companies processed: {self.stats['companies_processed']}
CUITs found: {self.stats['cuits_found']}
CUITs validated (AFIP): {self.stats['cuits_validated']}
HubSpot updates: {self.stats['hubspot_updated']}
Errors: {self.stats['errors']}
Success rate: {(self.stats['cuits_found'] / self.stats['companies_processed'] * 100) if self.stats['companies_processed'] > 0 else 0:.1f}%
Total time: {elapsed:.1f} seconds
Average time per company: {elapsed / self.stats['companies_processed'] if self.stats['companies_processed'] > 0 else 0:.1f} seconds
========================================
        """
        
        self.logger.info(summary)
        
        # Save summary to file
        os.makedirs('outputs', exist_ok=True)
        summary_file = f"outputs/enrichment_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(summary_file, 'w') as f:
            f.write(summary)
    
    def export_results(self, filename: str = None):
        """Export processing results"""
        if not filename:
            filename = f"enrichment_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        os.makedirs('outputs', exist_ok=True)
        
        # Export statistics
        stats_file = f"outputs/{filename}_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2, default=str)
        
        self.logger.info(f"Results exported to {stats_file}")


def main():
    """Main execution function"""
    
    # Configuration
    config = {
        'scraper_method': 'playwright',  # or 'selenium' or 'requests'
        'use_afip_validation': False,  # Set to True if AFIP API is configured
        'dry_run': False,  # Set to True to test without updating HubSpot
        'limit': 50  # Number of companies to process
    }
    
    # Create enrichment pipeline
    enrichment = AutomatedCUITEnrichment(
        scraper_method=config['scraper_method'],
        use_afip_validation=config['use_afip_validation'],
        dry_run=config['dry_run']
    )
    
    # Process companies
    enrichment.process_companies(limit=config['limit'])
    
    # Export results
    enrichment.export_results()


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description='Automated CUIT Enrichment for HubSpot')
    parser.add_argument('--method', choices=['requests', 'selenium', 'playwright'], 
                       default='playwright', help='Scraping method to use')
    parser.add_argument('--limit', type=int, default=50, 
                       help='Maximum number of companies to process')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Run without updating HubSpot')
    parser.add_argument('--use-afip', action='store_true', 
                       help='Validate CUITs with AFIP API')
    
    args = parser.parse_args()
    
    # Run with arguments
    enrichment = AutomatedCUITEnrichment(
        scraper_method=args.method,
        use_afip_validation=args.use_afip,
        dry_run=args.dry_run
    )
    
    enrichment.process_companies(limit=args.limit)
    enrichment.export_results()