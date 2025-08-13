#!/usr/bin/env python3
"""
HubSpot Hybrid Identifier Implementation
Shows how to implement a company identification system using both CUIT and normalized names
"""

import re
from typing import Dict, List, Optional, Tuple
from hubspot_api import get_client
from hubspot_api.models import Company

class CompanyIdentifierManager:
    """Manages company identification using hybrid CUIT/Name approach"""
    
    def __init__(self):
        self.client = get_client()
        
    def normalize_company_name(self, name: str) -> str:
        """Normalize company name for consistent matching"""
        if not name:
            return ""
        
        # Remove ID prefixes (like "94778 - ")
        name = re.sub(r'^\d+\s*-\s*', '', name)
        
        # Standardize legal suffixes
        replacements = {
            'S.A.': 'SA',
            'S.R.L.': 'SRL',
            'S R L': 'SRL',
            'S. A.': 'SA',
            'S. R. L.': 'SRL',
            '& ASOC': 'Y ASOCIADOS',
            '& Asociados': 'Y ASOCIADOS',
            ' - ': ' ',  # Remove dashes
            '  ': ' '    # Remove double spaces
        }
        
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        # Remove extra spaces and convert to uppercase
        normalized = ' '.join(name.upper().split())
        
        # Remove special characters but keep Spanish letters
        normalized = re.sub(r'[^\w\sÑÁÉÍÓÚñáéíóú]', '', normalized)
        
        return normalized.strip()
    
    def clean_cuit(self, cuit: Optional[str]) -> Optional[str]:
        """Clean and validate CUIT format"""
        if not cuit:
            return None
            
        # Remove all non-numeric characters
        cleaned = re.sub(r'[^0-9]', '', str(cuit))
        
        # Valid CUIT should be 11 digits
        if len(cleaned) == 11:
            return cleaned
        
        return None
    
    def find_company_by_identifier(self, 
                                   cuit: Optional[str] = None, 
                                   name: Optional[str] = None) -> List[Dict]:
        """
        Find companies using hybrid identifier approach
        Returns list of potential matches with confidence scores
        """
        matches = []
        
        # Try CUIT first (most reliable)
        if cuit:
            cleaned_cuit = self.clean_cuit(cuit)
            if cleaned_cuit:
                # Search by CUIT
                companies = Company.search(
                    filters=[{
                        'propertyName': 'cuit',
                        'operator': 'EQ',
                        'value': cleaned_cuit
                    }]
                )
                
                for company in companies:
                    matches.append({
                        'company': company,
                        'match_type': 'CUIT_EXACT',
                        'confidence': 100,
                        'reason': f'Exact CUIT match: {cleaned_cuit}'
                    })
        
        # Then try normalized name
        if name and len(matches) == 0:
            normalized_name = self.normalize_company_name(name)
            
            # Search by normalized name (custom property)
            companies = Company.search(
                filters=[{
                    'propertyName': 'normalized_company_name',
                    'operator': 'EQ',
                    'value': normalized_name
                }]
            )
            
            for company in companies:
                matches.append({
                    'company': company,
                    'match_type': 'NAME_NORMALIZED',
                    'confidence': 90,
                    'reason': f'Normalized name match: {normalized_name}'
                })
            
            # If no normalized name matches, try fuzzy search on regular name
            if len(matches) == 0:
                companies = Company.search(
                    filters=[{
                        'propertyName': 'name',
                        'operator': 'CONTAINS_TOKEN',
                        'value': name.split()[0] if name.split() else name
                    }],
                    limit=10
                )
                
                for company in companies:
                    company_name = company.get('properties', {}).get('name', '')
                    if self.normalize_company_name(company_name) == normalized_name:
                        matches.append({
                            'company': company,
                            'match_type': 'NAME_FUZZY',
                            'confidence': 80,
                            'reason': f'Fuzzy name match: {company_name}'
                        })
        
        return sorted(matches, key=lambda x: x['confidence'], reverse=True)
    
    def create_or_update_company(self, company_data: Dict) -> Tuple[Dict, str]:
        """
        Create or update company using hybrid identifier approach
        Returns: (company, action) where action is 'created', 'updated', or 'duplicate_found'
        """
        name = company_data.get('name', '')
        cuit = company_data.get('cuit', '')
        
        # Find existing companies
        matches = self.find_company_by_identifier(cuit=cuit, name=name)
        
        if matches:
            # Found existing company
            best_match = matches[0]
            company = best_match['company']
            
            if best_match['confidence'] >= 90:
                # High confidence match - update
                update_data = {}
                
                # Update CUIT if missing
                if cuit and not company.get('properties', {}).get('cuit'):
                    update_data['cuit'] = self.clean_cuit(cuit)
                
                # Update normalized name
                update_data['normalized_company_name'] = self.normalize_company_name(name)
                
                if update_data:
                    Company.update(company['id'], update_data)
                    return company, 'updated'
                else:
                    return company, 'duplicate_found'
            else:
                # Low confidence - flag for review
                print(f"⚠️  Potential duplicate found with {best_match['confidence']}% confidence")
                print(f"   Reason: {best_match['reason']}")
                # In production, this would create a task for manual review
        
        # No match found - create new company
        create_data = {
            'name': name,
            'normalized_company_name': self.normalize_company_name(name)
        }
        
        if cuit:
            create_data['cuit'] = self.clean_cuit(cuit)
        
        new_company = Company.create(create_data)
        return new_company, 'created'
    
    def deduplicate_companies(self) -> Dict[str, List]:
        """Find potential duplicate companies"""
        duplicates = {}
        
        # Get all companies
        all_companies = Company.get_all(properties=['name', 'cuit', 'normalized_company_name'])
        
        # Group by normalized name
        by_normalized_name = {}
        for company in all_companies:
            props = company.get('properties', {})
            normalized = props.get('normalized_company_name') or self.normalize_company_name(props.get('name', ''))
            
            if normalized:
                if normalized not in by_normalized_name:
                    by_normalized_name[normalized] = []
                by_normalized_name[normalized].append(company)
        
        # Find groups with multiple companies
        for normalized_name, companies in by_normalized_name.items():
            if len(companies) > 1:
                duplicates[normalized_name] = companies
        
        return duplicates

def demonstrate_hybrid_approach():
    """Demonstrate the hybrid identification approach"""
    
    print("🔄 HUBSPOT HYBRID IDENTIFIER IMPLEMENTATION")
    print("=" * 70)
    
    manager = CompanyIdentifierManager()
    
    # Example companies to process
    test_companies = [
        {
            'name': '94778 - ALEJANDRO NICOLAS PEREZ',
            'cuit': '20357299277'
        },
        {
            'name': 'Ombú Consulting Services S.A.',
            'cuit': '30-60720870-7'
        },
        {
            'name': 'Estudio Contable García',
            'cuit': None  # Missing CUIT
        },
        {
            'name': 'OMBU CONSULTING SERVICES SA',  # Duplicate of #2
            'cuit': '30607208707'
        }
    ]
    
    print("\n📋 PROCESSING COMPANIES:")
    print("-" * 70)
    
    for i, company_data in enumerate(test_companies, 1):
        print(f"\n{i}. Processing: {company_data['name']}")
        print(f"   CUIT: {company_data.get('cuit', 'NOT PROVIDED')}")
        
        # Normalize name
        normalized = manager.normalize_company_name(company_data['name'])
        print(f"   Normalized: {normalized}")
        
        # Clean CUIT
        cleaned_cuit = manager.clean_cuit(company_data.get('cuit'))
        print(f"   Clean CUIT: {cleaned_cuit or 'N/A'}")
        
        # Find matches (simulation)
        print(f"   Action: Would search for existing matches...")
        
        if i == 4:  # Simulate finding duplicate
            print(f"   ⚠️  DUPLICATE DETECTED: Matches company #2")
            print(f"   Confidence: 95% (Same CUIT and normalized name)")

def show_custom_properties_needed():
    """Show HubSpot custom properties needed"""
    
    print("\n\n🛠️  HUBSPOT CUSTOM PROPERTIES NEEDED:")
    print("=" * 70)
    
    properties = [
        {
            'name': 'normalized_company_name',
            'label': 'Normalized Company Name',
            'type': 'string',
            'description': 'Auto-generated normalized version of company name for matching'
        },
        {
            'name': 'cuit_status',
            'label': 'CUIT Status',
            'type': 'enumeration',
            'options': ['Valid', 'Invalid', 'Missing', 'Pending Verification'],
            'description': 'Current status of the CUIT field'
        },
        {
            'name': 'duplicate_check_status',
            'label': 'Duplicate Check Status',
            'type': 'enumeration',
            'options': ['Unique', 'Potential Duplicate', 'Confirmed Duplicate', 'Merged'],
            'description': 'Status of duplicate checking for this company'
        },
        {
            'name': 'primary_identifier_type',
            'label': 'Primary Identifier Type',
            'type': 'enumeration',
            'options': ['CUIT', 'Name', 'Mixed'],
            'description': 'Which identifier is being used as primary'
        }
    ]
    
    for prop in properties:
        print(f"\n📌 Property: {prop['name']}")
        print(f"   Label: {prop['label']}")
        print(f"   Type: {prop['type']}")
        if 'options' in prop:
            print(f"   Options: {', '.join(prop['options'])}")
        print(f"   Purpose: {prop['description']}")

def main():
    """Run demonstrations"""
    
    demonstrate_hybrid_approach()
    show_custom_properties_needed()
    
    print("\n\n✅ IMPLEMENTATION BENEFITS:")
    print("=" * 70)
    print("1. Works with companies that have CUITs AND those that don't")
    print("2. Prevents most duplicates through normalization")
    print("3. Maintains data integrity with confidence scoring")
    print("4. Allows gradual CUIT enrichment over time")
    print("5. Compatible with existing Colppy integration")

if __name__ == "__main__":
    main()