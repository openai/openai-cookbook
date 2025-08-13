#!/usr/bin/env python3
"""
AFIP CUIT Lookup Service
Uses TusFacturas.app API to query official AFIP/ARCA data for CUIT information.

Requirements:
- TusFacturas.app account with ARCA link (not available in DEV plan)
- Valid API credentials (apikey, usertoken, apitoken)

API Documentation: https://developers.tusfacturas.app/consultas-varias-a-servicios-afip-arca/api-factura-electronica-afip-clientes-consultar-cuit-en-constancia-de-inscripcion
"""

import os
import requests
import json
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AFIPActivity:
    """Represents an AFIP economic activity"""
    descripcion: str
    id: str
    nomenclador: str
    periodo: str


@dataclass
class AFIPCompanyInfo:
    """Represents company information from AFIP"""
    razon_social: str
    condicion_impositiva: str
    direccion: str
    localidad: str
    codigopostal: str
    estado: str
    provincia: str
    actividades: List[AFIPActivity]
    cuit: str
    error: bool = False
    errores: List[str] = None


class AFIPCUITLookupService:
    """Service to lookup CUIT information from official AFIP data via TusFacturas.app API"""
    
    def __init__(self, apikey: str = None, usertoken: str = None, apitoken: str = None):
        """
        Initialize the AFIP lookup service
        
        Args:
            apikey: TusFacturas.app API key
            usertoken: TusFacturas.app user token  
            apitoken: TusFacturas.app API token
        """
        self.apikey = apikey or os.getenv('TUSFACTURAS_API_KEY')
        self.usertoken = usertoken or os.getenv('TUSFACTURAS_USER_TOKEN')
        self.apitoken = apitoken or os.getenv('TUSFACTURAS_API_TOKEN')
        
        if not all([self.apikey, self.usertoken, self.apitoken]):
            raise ValueError("Missing TusFacturas.app credentials. Set environment variables or pass them directly.")
        
        self.base_url = "https://www.tusfacturas.app/app/api/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Colppy-CUIT-Lookup/1.0'
        })
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests
    
    def _rate_limit(self):
        """Implement rate limiting to avoid overwhelming the API"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _format_cuit(self, cuit: str) -> str:
        """
        Format CUIT to numeric format required by API (no dashes or dots)
        
        Args:
            cuit: CUIT in any format (e.g., "30-71229384-1" or "30712293841")
            
        Returns:
            str: Formatted CUIT (e.g., "30712293841")
        """
        return ''.join(filter(str.isdigit, cuit))
    
    def lookup_cuit(self, cuit: str) -> Optional[AFIPCompanyInfo]:
        """
        Look up CUIT information from AFIP
        
        Args:
            cuit: CUIT number in any format
            
        Returns:
            AFIPCompanyInfo object or None if not found
        """
        try:
            self._rate_limit()
            
            formatted_cuit = self._format_cuit(cuit)
            
            if len(formatted_cuit) != 11:
                print(f"Invalid CUIT format: {cuit} (should be 11 digits)")
                return None
            
            payload = {
                "usertoken": self.usertoken,
                "apikey": self.apikey,
                "apitoken": self.apitoken,
                "cliente": {
                    "documento_nro": formatted_cuit,
                    "documento_tipo": "CUIT"
                }
            }
            
            print(f"Looking up CUIT: {formatted_cuit}")
            
            response = self.session.post(
                f"{self.base_url}/clientes/afip-info",
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"API request failed with status {response.status_code}: {response.text}")
                return None
            
            data = response.json()
            
            if data.get('error') == 'S':
                print(f"AFIP returned error for CUIT {formatted_cuit}: {data.get('errores', [])}")
                return AFIPCompanyInfo(
                    razon_social="",
                    condicion_impositiva="",
                    direccion="",
                    localidad="",
                    codigopostal="",
                    estado="",
                    provincia="",
                    actividades=[],
                    cuit=formatted_cuit,
                    error=True,
                    errores=data.get('errores', [])
                )
            
            # Parse activities
            activities = []
            for activity_data in data.get('actividad', []):
                activities.append(AFIPActivity(
                    descripcion=activity_data.get('descripcion', ''),
                    id=activity_data.get('id', ''),
                    nomenclador=activity_data.get('nomenclador', ''),
                    periodo=activity_data.get('periodo', '')
                ))
            
            return AFIPCompanyInfo(
                razon_social=data.get('razon_social', ''),
                condicion_impositiva=data.get('condicion_impositiva', ''),
                direccion=data.get('direccion', ''),
                localidad=data.get('localidad', ''),
                codigopostal=data.get('codigopostal', ''),
                estado=data.get('estado', ''),
                provincia=data.get('provincia', ''),
                actividades=activities,
                cuit=formatted_cuit,
                error=False,
                errores=data.get('errores', [])
            )
            
        except requests.RequestException as e:
            print(f"Network error looking up CUIT {cuit}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON response for CUIT {cuit}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error looking up CUIT {cuit}: {e}")
            return None
    
    def bulk_lookup(self, cuits: List[str]) -> Dict[str, AFIPCompanyInfo]:
        """
        Perform bulk CUIT lookups
        
        Args:
            cuits: List of CUIT numbers
            
        Returns:
            Dictionary mapping CUIT to AFIPCompanyInfo
        """
        results = {}
        total = len(cuits)
        
        print(f"Starting bulk CUIT lookup for {total} CUITs...")
        
        for i, cuit in enumerate(cuits, 1):
            print(f"Processing {i}/{total}: {cuit}")
            
            info = self.lookup_cuit(cuit)
            if info:
                results[cuit] = info
            
            # Progress update every 10 items
            if i % 10 == 0:
                print(f"Completed {i}/{total} lookups...")
        
        print(f"Bulk lookup completed. Successfully retrieved {len(results)} out of {total} CUITs.")
        return results
    
    def export_results_to_csv(self, results: Dict[str, AFIPCompanyInfo], filename: str = None):
        """
        Export lookup results to CSV file
        
        Args:
            results: Dictionary of CUIT lookup results
            filename: Output filename (optional, defaults to timestamped name)
        """
        import csv
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"afip_cuit_lookup_results_{timestamp}.csv"
        
        os.makedirs('outputs', exist_ok=True)
        filepath = os.path.join('outputs', filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'cuit', 'razon_social', 'condicion_impositiva', 'estado',
                'direccion', 'localidad', 'codigopostal', 'provincia',
                'actividades_count', 'principales_actividades', 'error', 'errores'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for cuit, info in results.items():
                # Format activities for CSV
                main_activities = "; ".join([
                    f"{act.descripcion} ({act.id})" for act in info.actividades[:3]
                ])
                
                writer.writerow({
                    'cuit': info.cuit,
                    'razon_social': info.razon_social,
                    'condicion_impositiva': info.condicion_impositiva,
                    'estado': info.estado,
                    'direccion': info.direccion,
                    'localidad': info.localidad,
                    'codigopostal': info.codigopostal,
                    'provincia': info.provincia,
                    'actividades_count': len(info.actividades),
                    'principales_actividades': main_activities,
                    'error': info.error,
                    'errores': "; ".join(info.errores) if info.errores else ""
                })
        
        print(f"Results exported to: {filepath}")
        return filepath


def main():
    """Example usage and testing"""
    try:
        # Initialize the service
        service = AFIPCUITLookupService()
        
        # Test single lookup
        test_cuit = "30712293841"  # Example CUIT
        print(f"Testing single CUIT lookup: {test_cuit}")
        
        result = service.lookup_cuit(test_cuit)
        if result:
            print(f"Found: {result.razon_social}")
            print(f"Status: {result.estado}")
            print(f"Tax condition: {result.condicion_impositiva}")
            print(f"Activities: {len(result.actividades)}")
        else:
            print("CUIT not found or error occurred")
        
        # Example of bulk lookup (uncomment to test)
        # test_cuits = ["30712293841", "20123456789", "30987654321"]
        # bulk_results = service.bulk_lookup(test_cuits)
        # service.export_results_to_csv(bulk_results)
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure to set your TusFacturas.app credentials:")
        print("export TUSFACTURAS_API_KEY='your_api_key'")
        print("export TUSFACTURAS_USER_TOKEN='your_user_token'")
        print("export TUSFACTURAS_API_TOKEN='your_api_token'")


if __name__ == "__main__":
    main()