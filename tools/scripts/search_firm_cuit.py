#!/usr/bin/env python3
"""
General-purpose CUIT search script for any firm/company name
Can be used from command line or imported as a module
"""

import sys
import argparse
from cuitonline_scraper import CUITOnlineScraper
import json
from datetime import datetime


class FirmCUITSearcher:
    """Search for CUITs of any firm/company"""
    
    def __init__(self, method="playwright", headless=True):
        """
        Initialize the searcher
        
        Args:
            method: Scraping method - "requests", "selenium", or "playwright"
            headless: Run browser in headless mode
        """
        self.scraper = CUITOnlineScraper(method=method, headless=headless)
        self.all_results = []
        self.unique_cuits = set()
    
    def generate_search_variations(self, firm_name):
        """
        Generate search variations for a firm name
        
        Args:
            firm_name: The firm name to search
            
        Returns:
            List of search variations
        """
        variations = [firm_name]  # Always include the original
        
        # Common accounting firm patterns
        accounting_terms = ["Estudio", "Estudio Contable", "Contadores", "Auditores", "Consultores"]
        
        # Remove common suffixes and create variations
        common_suffixes = [
            " S.A.", " SA", " S.R.L.", " SRL", " S.C.", " SC",
            " & Asociados", " y Asociados", " & Asoc", " Asociados",
            " & Co", " y Cia", " y Cía", " Hnos", " e Hijos"
        ]
        
        # Clean name (remove suffixes)
        clean_name = firm_name
        for suffix in common_suffixes:
            if clean_name.endswith(suffix):
                clean_name = clean_name[:-len(suffix)].strip()
                variations.append(clean_name)
                break
        
        # Add variations with common prefixes if not already present
        for term in accounting_terms:
            if not firm_name.lower().startswith(term.lower()):
                variations.append(f"{term} {clean_name}")
        
        # Split by common separators and try parts
        separators = [" & ", " y ", ", ", " - "]
        for sep in separators:
            if sep in firm_name:
                parts = firm_name.split(sep)
                # Add individual parts
                variations.extend([part.strip() for part in parts])
                # Add first part only
                if len(parts) > 0:
                    variations.append(parts[0].strip())
        
        # If it has multiple words, try first few words and last few words
        words = firm_name.split()
        if len(words) > 2:
            variations.append(" ".join(words[:2]))  # First two words
            variations.append(" ".join(words[-2:]))  # Last two words
            variations.append(words[0])  # Just first word
            variations.append(words[-1])  # Just last word
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for v in variations:
            if v and v not in seen:
                seen.add(v)
                unique_variations.append(v)
        
        return unique_variations
    
    def search_firm(self, firm_name, max_variations=10):
        """
        Search for a firm by name
        
        Args:
            firm_name: The firm name to search
            max_variations: Maximum number of variations to try
            
        Returns:
            List of unique results found
        """
        print("=" * 70)
        print(f"Searching for: {firm_name}")
        print("=" * 70)
        
        # Generate search variations
        variations = self.generate_search_variations(firm_name)[:max_variations]
        
        print(f"\nGenerated {len(variations)} search variations:")
        for i, var in enumerate(variations, 1):
            print(f"{i}. {var}")
        
        # Reset results
        self.all_results = []
        self.unique_cuits = set()
        
        # Search each variation
        for variation in variations:
            print(f"\n🔍 Searching: {variation}")
            
            try:
                results = self.scraper.search_by_name(variation)
                
                if results:
                    print(f"✅ Found {len(results)} result(s)")
                    
                    # Add unique results
                    new_results = 0
                    for result in results:
                        if result.cuit not in self.unique_cuits:
                            self.unique_cuits.add(result.cuit)
                            self.all_results.append(result)
                            new_results += 1
                            
                            # Display result
                            print(f"    CUIT: {result.cuit} - {result.name}")
                    
                    if new_results < len(results):
                        print(f"    ({len(results) - new_results} duplicates filtered)")
                else:
                    print("❌ No results")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
        
        return self.all_results
    
    def display_summary(self):
        """Display summary of results"""
        print("\n" + "=" * 70)
        print("SEARCH SUMMARY")
        print("=" * 70)
        
        if self.all_results:
            print(f"\n✅ Total unique CUITs found: {len(self.all_results)}")
            
            # Group by company type (CUIT prefix)
            companies = [r for r in self.all_results if r.cuit.startswith('30') or r.cuit.startswith('33')]
            individuals = [r for r in self.all_results if r.cuit.startswith('20') or r.cuit.startswith('27') or r.cuit.startswith('23') or r.cuit.startswith('24')]
            
            print(f"\nBreakdown:")
            print(f"  - Companies (30/33-): {len(companies)}")
            print(f"  - Individuals (20/23/24/27-): {len(individuals)}")
            
            # Show all results
            print(f"\nAll results:")
            for i, result in enumerate(self.all_results, 1):
                cuit_type = "Company" if result.cuit[:2] in ['30', '33'] else "Individual"
                print(f"{i}. {result.cuit} - {result.name} ({cuit_type})")
        else:
            print("\n❌ No CUITs found")
            print("\nSuggestions:")
            print("1. Try searching with a simpler name (e.g., just the last name)")
            print("2. Check if the firm name is spelled correctly")
            print("3. The firm might not be registered on cuitonline.com")
            print("4. Try searching for individual partners instead")
    
    def export_results(self, firm_name):
        """Export results to files"""
        if not self.all_results:
            print("\nNo results to export")
            return
        
        # Create safe filename
        safe_name = "".join(c for c in firm_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')[:50]  # Limit length
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}"
        
        print(f"\n💾 Exporting results...")
        self.scraper.export_results(self.all_results, filename)
        print(f"✅ Results exported to:")
        print(f"   - outputs/{filename}.csv")
        print(f"   - outputs/{filename}.json")


def main():
    """Main function for command-line usage"""
    
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Search for CUIT information of any firm/company',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python search_firm_cuit.py "PwC Argentina"
  python search_firm_cuit.py "Deloitte & Touche"
  python search_firm_cuit.py "Estudio Contable Perez"
  python search_firm_cuit.py --method selenium "KPMG"
  python search_firm_cuit.py --variations 5 "Ernst & Young"
        """
    )
    
    parser.add_argument('firm_name', 
                       help='Name of the firm/company to search')
    
    parser.add_argument('--method', 
                       choices=['requests', 'selenium', 'playwright'],
                       default='playwright',
                       help='Scraping method to use (default: playwright)')
    
    parser.add_argument('--variations', 
                       type=int, 
                       default=10,
                       help='Maximum number of name variations to try (default: 10)')
    
    parser.add_argument('--no-headless', 
                       action='store_true',
                       help='Run browser with GUI (not headless)')
    
    parser.add_argument('--export', 
                       action='store_true',
                       default=True,
                       help='Export results to CSV and JSON (default: True)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create searcher
    searcher = FirmCUITSearcher(
        method=args.method,
        headless=not args.no_headless
    )
    
    # Search for the firm
    searcher.search_firm(args.firm_name, max_variations=args.variations)
    
    # Display summary
    searcher.display_summary()
    
    # Export results
    if args.export and searcher.all_results:
        searcher.export_results(args.firm_name)


if __name__ == "__main__":
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        print("Usage: python search_firm_cuit.py <firm_name>")
        print("Example: python search_firm_cuit.py \"PwC Argentina\"")
        print("\nFor more options: python search_firm_cuit.py --help")
        sys.exit(1)
    
    main()