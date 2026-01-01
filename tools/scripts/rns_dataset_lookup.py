#!/usr/bin/env python3
"""
RNS Dataset Lookup Service
Uses the official open data portal to lookup creation dates from downloaded RNS datasets.

This is the RECOMMENDED approach - much more reliable than web scraping!

Dataset URL: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
"""

import os
import csv
import zipfile
import pandas as pd
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
import requests
from pathlib import Path


@dataclass
class RNSCreationDateResult:
    """Result of RNS dataset lookup"""
    cuit: str
    creation_date: Optional[str] = None  # Format: YYYY-MM-DD
    razon_social: Optional[str] = None
    tipo_societario: Optional[str] = None
    domicilio_fiscal: Optional[str] = None
    domicilio_legal: Optional[str] = None
    provincia: Optional[str] = None
    found: bool = False
    source_file: Optional[str] = None


class RNSDatasetLookup:
    """
    Lookup service using downloaded RNS datasets from open data portal.
    
    Dataset URLs:
    - Main page: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades
    - Sample (1000 records): https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/6096331b-0511-4728-b01b-6c6b535f4c2b/download/registro-nacional-sociedades-muestreo.csv
    - Latest full dataset: Check the portal for most recent semester
    """
    
    def __init__(self, dataset_dir: str = None):
        """
        Initialize the lookup service
        
        Args:
            dataset_dir: Directory containing downloaded RNS CSV/ZIP files
                        If None, uses ./rns_datasets/ directory
        """
        if dataset_dir is None:
            dataset_dir = os.path.join(os.path.dirname(__file__), 'rns_datasets')
        
        self.dataset_dir = Path(dataset_dir)
        self.dataset_dir.mkdir(exist_ok=True)
        
        # In-memory cache of loaded data
        self.data_cache: Dict[str, pd.DataFrame] = {}
        
        # Column name mappings (may vary by dataset version)
        self.cuit_column = 'cuit'  # or 'cuit_cdi', 'cuit_cdi_numero'
        self.date_column = 'fecha_contrato_social'  # Will be set dynamically
        self.name_column = 'razon_social'  # or 'denominacion_social'
    
    def download_sample_dataset(self) -> str:
        """
        Download the sample dataset (1000 records) for testing
        
        Returns:
            Path to downloaded file
        """
        sample_url = "https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/6096331b-0511-4728-b01b-6c6b535f4c2b/download/registro-nacional-sociedades-muestreo.csv"
        
        output_path = self.dataset_dir / "rns_muestreo.csv"
        
        print(f"Downloading sample dataset from RNS open data portal...")
        response = requests.get(sample_url, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✓ Downloaded to: {output_path}")
        return str(output_path)
    
    def download_full_dataset(self, year: int = 2025, semester: int = 2) -> str:
        """
        Download a full semester dataset (much larger than sample)
        
        Args:
            year: Year of the dataset (default: 2025)
            semester: Semester (1 or 2, default: 2)
            
        Returns:
            Path to downloaded ZIP file
        """
        # URL pattern for full datasets
        # Note: These URLs may need to be updated based on actual portal structure
        # Check https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades for latest URLs
        
        dataset_urls = {
            (2025, 2): "https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/cf93b46f-ec0b-4956-bcaf-412cd4799eef/download/registro-nacional-sociedades-2025-semestre-2.zip",
            (2025, 1): "https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/f5abfee1-e5a6-4e04-bfff-dbecc1c9bba2/download/registro-nacional-sociedades-2025-semestre-1.zip",
            (2024, 2): "https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/a3f34d54-72fc-4848-802e-d3307310b1e9/download/registro-nacional-sociedades-2024-semestre-2.zip",
            (2024, 1): "https://datos.jus.gob.ar/dataset/ee83de85-4305-4c53-9a9f-fd3d15e42c36/resource/da9f7729-e704-4c08-ba36-fc7074cb839d/download/registro-nacional-sociedades-2024-semestre-1.zip",
        }
        
        key = (year, semester)
        if key not in dataset_urls:
            raise ValueError(f"Dataset URL not available for {year} semester {semester}. Available: {list(dataset_urls.keys())}")
        
        url = dataset_urls[key]
        output_path = self.dataset_dir / f"rns_{year}_semestre_{semester}.zip"
        
        print(f"Downloading full dataset: {year} semester {semester}...")
        print(f"This may take several minutes (file is large)...")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    if downloaded % (1024 * 1024) == 0:  # Print every MB
                        print(f"  Progress: {percent:.1f}% ({downloaded / (1024*1024):.1f} MB)")
        
        print(f"✓ Downloaded to: {output_path}")
        print(f"  File size: {downloaded / (1024*1024):.1f} MB")
        return str(output_path)
    
    def load_dataset(self, filepath: str) -> pd.DataFrame:
        """
        Load a dataset file (CSV or ZIP containing CSV)
        
        Args:
            filepath: Path to CSV or ZIP file
            
        Returns:
            DataFrame with RNS data
        """
        filepath = Path(filepath)
        
        # Check cache
        cache_key = str(filepath.absolute())
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        # Handle ZIP files
        if filepath.suffix == '.zip':
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                # Find CSV file in ZIP
                csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
                if not csv_files:
                    raise ValueError(f"No CSV file found in ZIP: {filepath}")
                
                # Use first CSV file (or can be customized to select specific file)
                target_file = csv_files[0]
                
                # Read CSV from ZIP with error handling
                with zip_ref.open(target_file) as csv_file:
                    try:
                        # Try with on_bad_lines (pandas >= 1.3) using C engine
                        df = pd.read_csv(
                            csv_file, 
                            encoding='utf-8', 
                            low_memory=False,
                            on_bad_lines='skip',
                            sep=',',
                            quotechar='"'
                        )
                    except (TypeError, ValueError):
                        # Fallback: use python engine (more forgiving but slower)
                        df = pd.read_csv(
                            csv_file, 
                            encoding='utf-8', 
                            engine='python',
                            sep=',',
                            quotechar='"',
                            error_bad_lines=False,
                            warn_bad_lines=False
                        )
        else:
            # Read CSV directly with error handling
            try:
                df = pd.read_csv(
                    filepath, 
                    encoding='utf-8', 
                    low_memory=False,
                    on_bad_lines='skip',
                    sep=',',
                    quotechar='"'
                )
            except (TypeError, ValueError):
                # Fallback: use python engine
                df = pd.read_csv(
                    filepath, 
                    encoding='utf-8', 
                    engine='python',
                    sep=',',
                    quotechar='"',
                    error_bad_lines=False,
                    warn_bad_lines=False
                )
        
        # Normalize column names (handle variations)
        df.columns = df.columns.str.lower().str.strip()
        
        # Try to find CUIT column
        cuit_cols = [col for col in df.columns if 'cuit' in col or 'cdi' in col]
        if cuit_cols:
            if self.cuit_column not in df.columns and cuit_cols:
                df[self.cuit_column] = df[cuit_cols[0]]
        
        # Try to find date column (handle variations like fecha_hora_contrato_social)
        date_cols = [col for col in df.columns if 'fecha' in col and 'contrato' in col]
        if date_cols:
            # Use the first matching date column
            actual_date_col = date_cols[0]
            if 'fecha_contrato_social' not in df.columns:
                df['fecha_contrato_social'] = df[actual_date_col]
            self.date_column = 'fecha_contrato_social'
        elif 'fecha_contrato_social' not in df.columns:
            # Fallback: look for any fecha column
            fecha_cols = [col for col in df.columns if 'fecha' in col]
            if fecha_cols:
                df['fecha_contrato_social'] = df[fecha_cols[0]]
                self.date_column = 'fecha_contrato_social'
        
        # Cache the loaded data
        self.data_cache[cache_key] = df
        
        return df
    
    def load_all_datasets(self) -> pd.DataFrame:
        """
        Load all datasets from the dataset directory
        
        Returns:
            Combined DataFrame with all RNS data
        """
        all_dataframes = []
        
        # Find all CSV and ZIP files
        csv_files = list(self.dataset_dir.glob('*.csv'))
        zip_files = list(self.dataset_dir.glob('*.zip'))
        
        print(f"Loading {len(csv_files)} CSV files and {len(zip_files)} ZIP files...")
        
        for filepath in csv_files + zip_files:
            try:
                print(f"  Loading: {filepath.name}")
                df = self.load_dataset(filepath)
                all_dataframes.append(df)
            except Exception as e:
                print(f"  ⚠️  Error loading {filepath.name}: {e}")
                continue
        
        if not all_dataframes:
            raise ValueError(f"No datasets found in {self.dataset_dir}. Download datasets first!")
        
        # Combine all dataframes
        combined = pd.concat(all_dataframes, ignore_index=True)
        
        # Remove duplicates (keep first occurrence)
        if self.cuit_column in combined.columns:
            combined = combined.drop_duplicates(subset=[self.cuit_column], keep='first')
        
        print(f"✓ Loaded {len(combined)} total records")
        return combined
    
    def lookup_cuit(self, cuit: str, use_all_datasets: bool = True) -> Optional[RNSCreationDateResult]:
        """
        Lookup creation date for a CUIT
        
        Args:
            cuit: CUIT number (11 digits)
            use_all_datasets: If True, search all loaded datasets
            
        Returns:
            RNSCreationDateResult or None
        """
        # Format CUIT
        formatted_cuit = ''.join(filter(str.isdigit, cuit))
        if len(formatted_cuit) != 11:
            return None
        
        # Load datasets if not already loaded
        if use_all_datasets:
            try:
                df = self.load_all_datasets()
            except Exception as e:
                print(f"Error loading datasets: {e}")
                return None
        else:
            # Try to use cached data or load sample
            sample_file = self.dataset_dir / "rns_muestreo.csv"
            if sample_file.exists():
                df = self.load_dataset(sample_file)
            else:
                return None
        
        # Search for CUIT
        if self.cuit_column not in df.columns:
            print(f"⚠️  CUIT column '{self.cuit_column}' not found in dataset")
            print(f"   Available columns: {list(df.columns)}")
            return None
        
        # Filter by CUIT (handle various formats)
        if self.cuit_column not in df.columns:
            print(f"⚠️  CUIT column '{self.cuit_column}' not found in dataset")
            print(f"   Available columns: {list(df.columns)}")
            return None
        
        # Convert CUIT column to string and normalize (remove dashes, dots, spaces)
        df_cuit_normalized = df[self.cuit_column].astype(str).str.replace(r'[-\s\.]', '', regex=True)
        matches = df[df_cuit_normalized == formatted_cuit]
        
        if matches.empty:
            return RNSCreationDateResult(cuit=formatted_cuit, found=False)
        
        # Get first match
        row = matches.iloc[0]
        
        # Extract creation date
        creation_date = None
        if self.date_column in row and pd.notna(row[self.date_column]):
            date_str = str(row[self.date_column])
            # Try to parse various date formats
            creation_date = self._parse_date(date_str)
        
        # Extract other fields
        razon_social = row.get(self.name_column, '') if self.name_column in row else None
        tipo_societario = row.get('tipo_societario', '') if 'tipo_societario' in row else None
        domicilio_fiscal = row.get('domicilio_fiscal', '') if 'domicilio_fiscal' in row else None
        domicilio_legal = row.get('domicilio_legal', '') if 'domicilio_legal' in row else None
        provincia = row.get('dom_legal_provincia', '') if 'dom_legal_provincia' in row else None
        
        return RNSCreationDateResult(
            cuit=formatted_cuit,
            creation_date=creation_date,
            razon_social=razon_social,
            tipo_societario=tipo_societario,
            domicilio_fiscal=domicilio_fiscal,
            domicilio_legal=domicilio_legal,
            provincia=provincia,
            found=True
        )
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse various date formats to YYYY-MM-DD"""
        if not date_str or pd.isna(date_str):
            return None
        
        date_str = str(date_str).strip()
        
        # Handle format like "1912-04-30-10:43" (YYYY-MM-DD-HH:MM)
        if '-' in date_str and len(date_str) > 10:
            # Extract just the date part (first 10 characters: YYYY-MM-DD)
            date_part = date_str[:10]
            if len(date_part) == 10 and date_part.count('-') == 2:
                try:
                    dt = datetime.strptime(date_part, '%Y-%m-%d')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass
        
        # Common formats
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y/%m/%d',
            '%d/%m/%y',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
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
    
    def bulk_lookup(self, cuits: List[str]) -> Dict[str, RNSCreationDateResult]:
        """
        Perform bulk lookup for multiple CUITs
        
        Args:
            cuits: List of CUIT numbers
            
        Returns:
            Dictionary mapping CUIT to RNSCreationDateResult
        """
        results = {}
        total = len(cuits)
        
        print(f"Starting bulk lookup for {total} CUITs...")
        
        # Load all datasets once
        try:
            df = self.load_all_datasets()
        except Exception as e:
            print(f"Error loading datasets: {e}")
            print("Try downloading datasets first using download_sample_dataset()")
            return {}
        
        for i, cuit in enumerate(cuits, 1):
            result = self.lookup_cuit(cuit, use_all_datasets=False)  # Already loaded
            results[cuit] = result
            
            if result and result.found:
                print(f"  {i}/{total}: {cuit} ✓ {result.creation_date or 'No date'}")
            else:
                print(f"  {i}/{total}: {cuit} ✗ Not found")
            
            if i % 100 == 0:
                print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")
        
        found = sum(1 for r in results.values() if r and r.found)
        print(f"\n✓ Completed: {found}/{total} CUITs found ({found/total*100:.1f}%)")
        
        return results


def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Lookup creation dates from RNS open data datasets'
    )
    parser.add_argument(
        '--download-sample',
        action='store_true',
        help='Download sample dataset (1000 records)'
    )
    parser.add_argument(
        '--cuit',
        help='Single CUIT to lookup'
    )
    parser.add_argument(
        '--file',
        help='CSV file with CUITs to lookup'
    )
    parser.add_argument(
        '--dataset-dir',
        help='Directory containing RNS datasets (default: ./rns_datasets/)'
    )
    
    args = parser.parse_args()
    
    lookup = RNSDatasetLookup(dataset_dir=args.dataset_dir)
    
    if args.download_sample:
        lookup.download_sample_dataset()
        print("\n✓ Sample dataset downloaded. You can now use --cuit or --file to lookup CUITs.")
        return
    
    if args.cuit:
        result = lookup.lookup_cuit(args.cuit)
        if result and result.found:
            print(f"\n✓ Found: {result.razon_social}")
            print(f"  Creation date: {result.creation_date}")
            print(f"  Type: {result.tipo_societario}")
        else:
            print(f"\n✗ CUIT not found in datasets")
            print("  Try downloading more datasets from: https://datos.jus.gob.ar/dataset/registro-nacional-de-sociedades")
    
    if args.file:
        import csv
        cuits = []
        with open(args.file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cuit = row.get('cuit', '').strip()
                if cuit:
                    cuits.append(cuit)
        
        results = lookup.bulk_lookup(cuits)
        
        # Export results
        output_file = f"rns_lookup_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'cuit', 'found', 'creation_date', 'razon_social', 'tipo_societario',
                'domicilio_fiscal', 'domicilio_legal', 'provincia'
            ])
            writer.writeheader()
            for cuit, result in results.items():
                writer.writerow({
                    'cuit': cuit,
                    'found': result.found if result else False,
                    'creation_date': result.creation_date if result else '',
                    'razon_social': result.razon_social if result else '',
                    'tipo_societario': result.tipo_societario if result else '',
                    'domicilio_fiscal': result.domicilio_fiscal if result else '',
                    'domicilio_legal': result.domicilio_legal if result else '',
                    'provincia': result.provincia if result else '',
                })
        
        print(f"\n✓ Results exported to: {output_file}")


if __name__ == "__main__":
    main()

