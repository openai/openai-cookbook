#!/usr/bin/env python3
"""
Enhanced CUIT Migration with AFIP Data Enrichment
Extends the existing migration script with official AFIP data validation and enrichment
"""

import sys
import os
import json
from typing import Dict, Optional, List
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing migration functions
from complete_july_2025_cuit_migration import (
    is_valid_cuit, clean_cuit, load_colppy_empresas, 
    get_hubspot_deals_data, process_cuit_mapping
)

# Import AFIP service
try:
    from scripts.afip_cuit_lookup import AFIPCUITLookupService, AFIPCompanyInfo
    AFIP_AVAILABLE = True
except ImportError:
    print("Warning: AFIP service not available. Install dependencies or configure credentials.")
    AFIP_AVAILABLE = False


class EnhancedCUITMigration:
    """Enhanced CUIT migration with AFIP data enrichment"""
    
    def __init__(self, enable_afip: bool = True):
        self.enable_afip = enable_afip and AFIP_AVAILABLE
        self.afip_service = None
        
        if self.enable_afip:
            try:
                self.afip_service = AFIPCUITLookupService()
                print("✅ AFIP service initialized successfully")
            except Exception as e:
                print(f"⚠️  AFIP service initialization failed: {e}")
                print("   Continuing without AFIP enrichment...")
                self.enable_afip = False
    
    def validate_cuit_with_afip(self, cuit: str) -> Dict:
        """
        Validate CUIT with official AFIP data
        
        Args:
            cuit: CUIT number to validate
            
        Returns:
            Dict with validation results and AFIP data
        """
        result = {
            'cuit': cuit,
            'is_valid_format': is_valid_cuit(cuit),
            'afip_validated': False,
            'afip_data': None,
            'afip_errors': [],
            'validation_status': 'format_only'
        }
        
        if not result['is_valid_format']:
            result['validation_status'] = 'invalid_format'
            return result
        
        if not self.enable_afip:
            result['validation_status'] = 'format_valid_no_afip'
            return result
        
        try:
            afip_info = self.afip_service.lookup_cuit(cuit)
            
            if afip_info and not afip_info.error:
                result['afip_validated'] = True
                result['afip_data'] = afip_info
                result['validation_status'] = 'afip_validated'
            elif afip_info and afip_info.error:
                result['afip_errors'] = afip_info.errores
                result['validation_status'] = 'afip_error'
            else:
                result['validation_status'] = 'afip_not_found'
                
        except Exception as e:
            result['afip_errors'] = [str(e)]
            result['validation_status'] = 'afip_lookup_failed'
        
        return result
    
    def enrich_company_data(self, company_data: Dict, afip_info: AFIPCompanyInfo) -> Dict:
        """
        Enrich company data with AFIP information
        
        Args:
            company_data: Existing company data
            afip_info: AFIP company information
            
        Returns:
            Enhanced company data
        """
        enriched = company_data.copy()
        
        # Add AFIP official data
        enriched['afip_razon_social'] = afip_info.razon_social
        enriched['afip_condicion_impositiva'] = afip_info.condicion_impositiva
        enriched['afip_estado'] = afip_info.estado
        enriched['afip_direccion'] = afip_info.direccion
        enriched['afip_localidad'] = afip_info.localidad
        enriched['afip_provincia'] = afip_info.provincia
        enriched['afip_codigo_postal'] = afip_info.codigopostal
        
        # Add economic activities
        if afip_info.actividades:
            enriched['afip_actividad_principal'] = afip_info.actividades[0].descripcion
            enriched['afip_codigo_actividad'] = afip_info.actividades[0].id
            enriched['afip_total_actividades'] = len(afip_info.actividades)
        
        # Flag potential name mismatches
        if company_data.get('name') and afip_info.razon_social:
            company_name = company_data['name'].upper().strip()
            afip_name = afip_info.razon_social.upper().strip()
            
            # Simple similarity check
            if company_name != afip_name:
                enriched['name_mismatch'] = True
                enriched['name_similarity_score'] = self._calculate_name_similarity(
                    company_name, afip_name
                )
        
        # Add validation timestamp
        enriched['afip_validation_date'] = datetime.now().isoformat()
        
        return enriched
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate simple name similarity score"""
        # Simple Jaccard similarity using words
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def process_enhanced_migration(self) -> Dict:
        """
        Run the enhanced migration with AFIP validation
        
        Returns:
            Migration results with AFIP data
        """
        print("Starting Enhanced CUIT Migration with AFIP Validation")
        print("=" * 60)
        
        # Load data using existing functions
        print("Loading Colppy empresas...")
        empresas = load_colppy_empresas()
        print(f"Loaded {len(empresas)} empresas from Colppy")
        
        print("Loading HubSpot deals...")
        deals_data = get_hubspot_deals_data()
        print(f"Loaded {len(deals_data)} deals from HubSpot")
        
        # Process CUIT mapping using existing logic
        print("Processing CUIT mappings...")
        mapping_results = process_cuit_mapping(empresas, deals_data)
        
        # Enhance with AFIP validation
        print("Enhancing with AFIP validation...")
        enhanced_results = self._enhance_with_afip(mapping_results)
        
        return enhanced_results
    
    def _enhance_with_afip(self, mapping_results: Dict) -> Dict:
        """Enhance mapping results with AFIP data"""
        
        enhanced = {
            'migration_summary': mapping_results.copy(),
            'afip_validation_summary': {
                'total_cuits_validated': 0,
                'afip_valid': 0,
                'afip_errors': 0,
                'afip_not_found': 0,
                'format_invalid': 0,
                'name_mismatches': 0
            },
            'company_details': [],
            'validation_errors': [],
            'recommendations': []
        }
        
        # Get unique CUITs to validate
        unique_cuits = set()
        
        # Collect CUITs from successful mappings
        for update in mapping_results.get('updates_to_apply', []):
            if update.get('cuit') and is_valid_cuit(update['cuit']):
                unique_cuits.add(clean_cuit(update['cuit']))
        
        print(f"Validating {len(unique_cuits)} unique CUITs with AFIP...")
        
        # Process each CUIT
        for i, cuit in enumerate(unique_cuits, 1):
            print(f"Validating {i}/{len(unique_cuits)}: {cuit}")
            
            validation_result = self.validate_cuit_with_afip(cuit)
            enhanced['afip_validation_summary']['total_cuits_validated'] += 1
            
            # Update counters
            status = validation_result['validation_status']
            if status == 'afip_validated':
                enhanced['afip_validation_summary']['afip_valid'] += 1
            elif status in ['afip_error', 'afip_lookup_failed']:
                enhanced['afip_validation_summary']['afip_errors'] += 1
            elif status == 'afip_not_found':
                enhanced['afip_validation_summary']['afip_not_found'] += 1
            elif status == 'invalid_format':
                enhanced['afip_validation_summary']['format_invalid'] += 1
            
            # Store detailed results
            if validation_result['afip_validated']:
                # Find corresponding company data
                company_data = self._find_company_data_for_cuit(
                    cuit, mapping_results.get('updates_to_apply', [])
                )
                
                if company_data:
                    enriched_company = self.enrich_company_data(
                        company_data, validation_result['afip_data']
                    )
                    enhanced['company_details'].append(enriched_company)
                    
                    # Check for name mismatches
                    if enriched_company.get('name_mismatch'):
                        enhanced['afip_validation_summary']['name_mismatches'] += 1
            
            # Store validation errors
            if validation_result['afip_errors']:
                enhanced['validation_errors'].append({
                    'cuit': cuit,
                    'errors': validation_result['afip_errors'],
                    'status': status
                })
        
        # Generate recommendations
        enhanced['recommendations'] = self._generate_recommendations(enhanced)
        
        return enhanced
    
    def _find_company_data_for_cuit(self, cuit: str, updates: List[Dict]) -> Optional[Dict]:
        """Find company data for a given CUIT"""
        for update in updates:
            if clean_cuit(update.get('cuit', '')) == cuit:
                return update
        return None
    
    def _generate_recommendations(self, enhanced_results: Dict) -> List[str]:
        """Generate recommendations based on validation results"""
        recommendations = []
        summary = enhanced_results['afip_validation_summary']
        
        if summary['afip_errors'] > 0:
            recommendations.append(
                f"🔍 {summary['afip_errors']} CUITs have AFIP errors. "
                "Review these companies for potential issues with their AFIP status."
            )
        
        if summary['afip_not_found'] > 0:
            recommendations.append(
                f"❓ {summary['afip_not_found']} CUITs not found in AFIP. "
                "Verify these CUITs are correct or check if companies are properly registered."
            )
        
        if summary['name_mismatches'] > 0:
            recommendations.append(
                f"📝 {summary['name_mismatches']} companies have name mismatches with AFIP. "
                "Consider updating company names to match official AFIP records."
            )
        
        if summary['afip_valid'] > 0:
            recommendations.append(
                f"✅ {summary['afip_valid']} CUITs successfully validated with AFIP. "
                "These companies have verified official data."
            )
        
        return recommendations
    
    def export_enhanced_results(self, results: Dict, filename: str = None):
        """Export enhanced results to files"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"enhanced_cuit_migration_{timestamp}"
        
        os.makedirs('outputs', exist_ok=True)
        
        # Export JSON report
        json_file = f"outputs/{filename}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # Export CSV for company details
        if results.get('company_details'):
            import csv
            csv_file = f"outputs/{filename}_companies.csv"
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'company_id', 'cuit', 'name', 'afip_razon_social',
                    'afip_condicion_impositiva', 'afip_estado',
                    'afip_actividad_principal', 'name_mismatch',
                    'name_similarity_score'
                ]
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for company in results['company_details']:
                    writer.writerow({
                        'company_id': company.get('company_id'),
                        'cuit': company.get('cuit'),
                        'name': company.get('name'),
                        'afip_razon_social': company.get('afip_razon_social'),
                        'afip_condicion_impositiva': company.get('afip_condicion_impositiva'),
                        'afip_estado': company.get('afip_estado'),
                        'afip_actividad_principal': company.get('afip_actividad_principal'),
                        'name_mismatch': company.get('name_mismatch', False),
                        'name_similarity_score': company.get('name_similarity_score', 1.0)
                    })
        
        print(f"Enhanced results exported to:")
        print(f"- JSON: {json_file}")
        if results.get('company_details'):
            print(f"- CSV: {csv_file}")


def main():
    """Main execution function"""
    try:
        # Initialize enhanced migration
        migration = EnhancedCUITMigration(enable_afip=True)
        
        # Run the enhanced migration
        results = migration.process_enhanced_migration()
        
        # Print summary
        print("\n" + "=" * 60)
        print("ENHANCED MIGRATION SUMMARY")
        print("=" * 60)
        
        afip_summary = results['afip_validation_summary']
        print(f"Total CUITs validated: {afip_summary['total_cuits_validated']}")
        print(f"AFIP valid: {afip_summary['afip_valid']}")
        print(f"AFIP errors: {afip_summary['afip_errors']}")
        print(f"Not found in AFIP: {afip_summary['afip_not_found']}")
        print(f"Name mismatches: {afip_summary['name_mismatches']}")
        
        print("\nRecommendations:")
        for rec in results['recommendations']:
            print(f"  {rec}")
        
        # Export results
        migration.export_enhanced_results(results)
        
        print("\n✅ Enhanced migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Enhanced migration failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()