#!/usr/bin/env python3
"""
CUIT Creation Date Lookup Service
Retrieves creation dates for Argentine CUITs from multiple sources:
- RNS (Registro Nacional de Sociedades) - for all companies
- IGJ (Inspección General de Justicia) - for CABA companies
- ARCA/AFIP - via existing service (doesn't provide creation date, but validates CUIT)

This service attempts multiple sources to maximize success rate.
"""

import os
import sys
import requests
import time
import re
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
from bs4 import BeautifulSoup

# Try to import playwright for advanced scraping
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None  # type: ignore
    PlaywrightTimeout = Exception  # type: ignore
    print("⚠️  Playwright not available. Some scraping features may be limited.")

# Try to import existing AFIP service
try:
    from afip_cuit_lookup import AFIPCUITLookupService
    AFIP_AVAILABLE = True
except ImportError:
    AFIP_AVAILABLE = False
    print("⚠️  AFIP service not available. Will skip AFIP validation.")


@dataclass
class CreationDateResult:
    """Result of creation date lookup"""
    cuit: str
    creation_date: Optional[str] = None  # Format: YYYY-MM-DD
    source: Optional[str] = None  # 'rns', 'igj', 'afip', 'manual'
    razon_social: Optional[str] = None
    error: bool = False
    error_message: Optional[str] = None
    raw_data: Optional[Dict] = None


class CUITCreationDateLookup:
    """
    Service to lookup creation dates for CUITs from multiple sources
    """
    
    def __init__(self, use_playwright: bool = True, use_afip: bool = True):
        """
        Initialize the lookup service
        
        Args:
            use_playwright: Use Playwright for JavaScript-heavy sites (recommended)
            use_afip: Use AFIP service for validation (requires credentials)
        """
        self.use_playwright = use_playwright and PLAYWRIGHT_AVAILABLE
        self.use_afip = use_afip and AFIP_AVAILABLE
        
        # Initialize AFIP service if available
        self.afip_service = None
        if self.use_afip:
            try:
                self.afip_service = AFIPCUITLookupService()
            except Exception as e:
                print(f"⚠️  Could not initialize AFIP service: {e}")
                self.afip_service = None
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 2.0  # 2 seconds between requests to be respectful
        
        # Session for requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _format_cuit(self, cuit: str) -> str:
        """Format CUIT to numeric format (11 digits)"""
        formatted = ''.join(filter(str.isdigit, cuit))
        if len(formatted) != 11:
            raise ValueError(f"Invalid CUIT format: {cuit} (should be 11 digits)")
        return formatted
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse various date formats to YYYY-MM-DD
        
        Args:
            date_str: Date string in various formats
            
        Returns:
            Date in YYYY-MM-DD format or None if parsing fails
        """
        if not date_str:
            return None
        
        # Common date formats in Argentina
        date_formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y-%m-%d',
            '%d/%m/%y',
            '%d-%m-%y',
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                # Handle 2-digit years
                if dt.year < 100:
                    if dt.year < 50:
                        dt = dt.replace(year=2000 + dt.year)
                    else:
                        dt = dt.replace(year=1900 + dt.year)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
    
    def lookup_rns(self, cuit: str) -> Optional[CreationDateResult]:
        """
        Lookup creation date from Registro Nacional de Sociedades (RNS)
        
        Args:
            cuit: CUIT number
            
        Returns:
            CreationDateResult or None
        """
        try:
            self._rate_limit()
            formatted_cuit = self._format_cuit(cuit)
            
            # RNS search URL
            # Note: This is the public search interface
            rns_url = "https://www.argentina.gob.ar/justicia/registro-nacional-sociedades"
            
            if self.use_playwright:
                return self._lookup_rns_playwright(formatted_cuit)
            else:
                return self._lookup_rns_requests(formatted_cuit)
                
        except Exception as e:
            return CreationDateResult(
                cuit=cuit,
                error=True,
                error_message=f"RNS lookup error: {str(e)}"
            )
    
    def _lookup_rns_playwright(self, cuit: str) -> Optional[CreationDateResult]:
        """Lookup RNS using Playwright (handles JavaScript)"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate to RNS search page
                rns_url = "https://www.argentina.gob.ar/justicia/registro-nacional-sociedades"
                page.goto(rns_url, wait_until="networkidle", timeout=30000)
                
                # Wait for search form to load
                page.wait_for_selector('input[type="text"]', timeout=10000)
                
                # Enter CUIT in search field
                # Note: The actual selector may need adjustment based on the site structure
                search_input = page.query_selector('input[type="text"]')
                if search_input:
                    search_input.fill(cuit)
                    search_input.press('Enter')
                    
                    # Wait for results
                    page.wait_for_timeout(3000)
                    
                    # Extract creation date from results
                    # This is a placeholder - actual implementation depends on page structure
                    content = page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Look for date patterns in the page
                    date_pattern = r'(\d{2}[/-]\d{2}[/-]\d{4})'
                    dates = re.findall(date_pattern, content)
                    
                    if dates:
                        # Try to identify the creation date (usually the earliest date)
                        creation_date = None
                        for date_str in dates:
                            parsed = self._parse_date(date_str)
                            if parsed:
                                if not creation_date or parsed < creation_date:
                                    creation_date = parsed
                        
                        if creation_date:
                            # Try to extract company name
                            razon_social = None
                            name_elements = soup.find_all(['h1', 'h2', 'h3', 'strong'])
                            for elem in name_elements:
                                text = elem.get_text(strip=True)
                                if text and len(text) > 5:
                                    razon_social = text
                                    break
                            
                            browser.close()
                            return CreationDateResult(
                                cuit=cuit,
                                creation_date=creation_date,
                                source='rns',
                                razon_social=razon_social
                            )
                
                browser.close()
                return None
                
        except Exception as e:
            return CreationDateResult(
                cuit=cuit,
                error=True,
                error_message=f"RNS Playwright error: {str(e)}"
            )
    
    def _lookup_rns_requests(self, cuit: str) -> Optional[CreationDateResult]:
        """Lookup RNS using requests (simpler, but may not work if site requires JavaScript)"""
        try:
            # RNS may require JavaScript, so this is a fallback
            # In practice, you may need to use Playwright
            return None
        except Exception as e:
            return CreationDateResult(
                cuit=cuit,
                error=True,
                error_message=f"RNS requests error: {str(e)}"
            )
    
    def lookup_igj(self, cuit: str) -> Optional[CreationDateResult]:
        """
        Lookup creation date from IGJ (Inspección General de Justicia) for CABA companies
        
        Args:
            cuit: CUIT number
            
        Returns:
            CreationDateResult or None
        """
        try:
            self._rate_limit()
            formatted_cuit = self._format_cuit(cuit)
            
            # IGJ search URL
            igj_url = "https://www.argentina.gob.ar/justicia/tramites-y-servicios/sociedades"
            
            if self.use_playwright:
                return self._lookup_igj_playwright(formatted_cuit)
            else:
                return None  # IGJ typically requires JavaScript
                
        except Exception as e:
            return CreationDateResult(
                cuit=cuit,
                error=True,
                error_message=f"IGJ lookup error: {str(e)}"
            )
    
    def _lookup_igj_playwright(self, cuit: str) -> Optional[CreationDateResult]:
        """Lookup IGJ using Playwright"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate to IGJ search
                igj_url = "https://www.argentina.gob.ar/justicia/tramites-y-servicios/sociedades"
                page.goto(igj_url, wait_until="networkidle", timeout=30000)
                
                # Similar pattern to RNS - search for CUIT and extract creation date
                # Implementation depends on actual IGJ site structure
                page.wait_for_timeout(3000)
                
                content = page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Look for date patterns
                date_pattern = r'(\d{2}[/-]\d{2}[/-]\d{4})'
                dates = re.findall(date_pattern, content)
                
                if dates:
                    creation_date = None
                    for date_str in dates:
                        parsed = self._parse_date(date_str)
                        if parsed:
                            if not creation_date or parsed < creation_date:
                                creation_date = parsed
                    
                    if creation_date:
                        browser.close()
                        return CreationDateResult(
                            cuit=cuit,
                            creation_date=creation_date,
                            source='igj'
                        )
                
                browser.close()
                return None
                
        except Exception as e:
            return CreationDateResult(
                cuit=cuit,
                error=True,
                error_message=f"IGJ Playwright error: {str(e)}"
            )
    
    def lookup_cuit(self, cuit: str, try_all_sources: bool = True) -> CreationDateResult:
        """
        Lookup creation date for a CUIT, trying multiple sources
        
        Args:
            cuit: CUIT number
            try_all_sources: If True, try all available sources
            
        Returns:
            CreationDateResult with creation date if found
        """
        formatted_cuit = self._format_cuit(cuit)
        result = CreationDateResult(cuit=formatted_cuit)
        
        # First, try to get company name from AFIP if available (for context)
        if self.afip_service:
            try:
                afip_info = self.afip_service.lookup_cuit(formatted_cuit)
                if afip_info and not afip_info.error:
                    result.razon_social = afip_info.razon_social
            except Exception:
                pass  # Continue even if AFIP fails
        
        # Try RNS first (most comprehensive)
        if try_all_sources:
            rns_result = self.lookup_rns(formatted_cuit)
            if rns_result and rns_result.creation_date:
                result.creation_date = rns_result.creation_date
                result.source = 'rns'
                if rns_result.razon_social:
                    result.razon_social = rns_result.razon_social
                return result
        
        # Try IGJ (for CABA companies)
        if try_all_sources:
            igj_result = self.lookup_igj(formatted_cuit)
            if igj_result and igj_result.creation_date:
                result.creation_date = igj_result.creation_date
                result.source = 'igj'
                return result
        
        # If no date found, mark as error
        if not result.creation_date:
            result.error = True
            result.error_message = "Creation date not found in any source"
        
        return result
    
    def bulk_lookup(self, cuits: List[str]) -> Dict[str, CreationDateResult]:
        """
        Perform bulk lookup for multiple CUITs
        
        Args:
            cuits: List of CUIT numbers
            
        Returns:
            Dictionary mapping CUIT to CreationDateResult
        """
        results = {}
        total = len(cuits)
        
        print(f"Starting bulk creation date lookup for {total} CUITs...")
        
        for i, cuit in enumerate(cuits, 1):
            print(f"Processing {i}/{total}: {cuit}")
            
            try:
                result = self.lookup_cuit(cuit)
                results[cuit] = result
                
                if result.creation_date:
                    print(f"  ✓ Found: {result.creation_date} (source: {result.source})")
                else:
                    print(f"  ✗ Not found: {result.error_message}")
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                results[cuit] = CreationDateResult(
                    cuit=cuit,
                    error=True,
                    error_message=str(e)
                )
            
            # Progress update every 10 items
            if i % 10 == 0:
                print(f"Completed {i}/{total} lookups...")
        
        successful = sum(1 for r in results.values() if r.creation_date)
        print(f"\nBulk lookup completed. Found {successful} out of {total} creation dates.")
        
        return results
    
    def export_to_csv(self, results: Dict[str, CreationDateResult], filename: str = None):
        """
        Export results to CSV
        
        Args:
            results: Dictionary of lookup results
            filename: Output filename (optional)
        """
        import csv
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cuit_creation_dates_{timestamp}.csv"
        
        os.makedirs('../outputs', exist_ok=True)
        filepath = os.path.join('../outputs', filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'cuit', 'razon_social', 'creation_date', 'source', 'error', 'error_message'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for cuit, result in results.items():
                writer.writerow({
                    'cuit': result.cuit,
                    'razon_social': result.razon_social or '',
                    'creation_date': result.creation_date or '',
                    'source': result.source or '',
                    'error': result.error,
                    'error_message': result.error_message or ''
                })
        
        print(f"Results exported to: {filepath}")
        return filepath


def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Lookup creation dates for Argentine CUITs'
    )
    parser.add_argument(
        'cuits',
        nargs='+',
        help='CUIT numbers to lookup (space-separated)'
    )
    parser.add_argument(
        '--file',
        help='File containing CUITs (one per line)'
    )
    parser.add_argument(
        '--no-playwright',
        action='store_true',
        help='Disable Playwright (use requests only)'
    )
    parser.add_argument(
        '--no-afip',
        action='store_true',
        help='Disable AFIP service'
    )
    parser.add_argument(
        '--output',
        help='Output CSV filename'
    )
    
    args = parser.parse_args()
    
    # Collect CUITs
    cuits = list(args.cuits) if args.cuits else []
    
    if args.file:
        with open(args.file, 'r') as f:
            file_cuits = [line.strip() for line in f if line.strip()]
            cuits.extend(file_cuits)
    
    if not cuits:
        print("Error: No CUITs provided. Use --file or provide CUITs as arguments.")
        return
    
    # Initialize service
    service = CUITCreationDateLookup(
        use_playwright=not args.no_playwright,
        use_afip=not args.no_afip
    )
    
    # Perform lookup
    if len(cuits) == 1:
        result = service.lookup_cuit(cuits[0])
        if result.creation_date:
            print(f"\n✓ Found creation date: {result.creation_date} (source: {result.source})")
            if result.razon_social:
                print(f"  Company: {result.razon_social}")
        else:
            print(f"\n✗ Creation date not found: {result.error_message}")
    else:
        results = service.bulk_lookup(cuits)
        service.export_to_csv(results, args.output)


if __name__ == "__main__":
    main()

