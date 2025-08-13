#!/usr/bin/env python3
"""
CUIT Online Web Scraper
Searches for CUIT information on cuitonline.com and extracts the results

Requirements:
- requests
- beautifulsoup4
- selenium (for JavaScript-heavy pages)
- playwright (alternative to Selenium, more modern)
"""

import os
import re
import time
import json
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

# Basic scraping with requests + BeautifulSoup
import requests
from bs4 import BeautifulSoup

# Advanced scraping with Selenium (for JavaScript rendering)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium not installed. Install with: pip install selenium")

# Alternative: Playwright (more modern)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not installed. Install with: pip install playwright && playwright install")


@dataclass
class CUITResult:
    """Represents a CUIT search result"""
    cuit: str
    name: str
    tipo_persona: str  # Física/Jurídica
    estado: str  # ACTIVO/INACTIVO
    direccion: Optional[str] = None
    localidad: Optional[str] = None
    provincia: Optional[str] = None
    condicion_impositiva: Optional[str] = None
    actividades: Optional[List[str]] = None
    search_url: Optional[str] = None
    detail_url: Optional[str] = None


class CUITOnlineScraper:
    """Web scraper for cuitonline.com"""
    
    def __init__(self, method: str = "requests", headless: bool = True):
        """
        Initialize the scraper
        
        Args:
            method: Scraping method - "requests", "selenium", or "playwright"
            headless: Run browser in headless mode (for selenium/playwright)
        """
        self.base_url = "https://www.cuitonline.com"
        self.method = method
        self.headless = headless
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 2.0  # seconds between requests
    
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def search_by_name(self, name: str) -> List[CUITResult]:
        """
        Search for CUIT by name
        
        Args:
            name: Name to search (e.g., "verdier piazza")
            
        Returns:
            List of CUIT results
        """
        if self.method == "requests":
            return self._search_with_requests(name)
        elif self.method == "selenium" and SELENIUM_AVAILABLE:
            return self._search_with_selenium(name)
        elif self.method == "playwright" and PLAYWRIGHT_AVAILABLE:
            return self._search_with_playwright(name)
        else:
            raise ValueError(f"Method '{self.method}' not available or not installed")
    
    def _search_with_requests(self, name: str) -> List[CUITResult]:
        """Search using requests + BeautifulSoup"""
        self._rate_limit()
        
        # URL encode the search term
        search_term = quote(name)
        search_url = f"{self.base_url}/search/{search_term}"
        
        self.logger.info(f"Searching: {search_url}")
        
        try:
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract results - this needs to be adapted based on actual HTML structure
            results = []
            
            # Look for result containers (adjust selectors based on actual HTML)
            result_containers = soup.find_all('div', class_='resultado') or \
                               soup.find_all('article', class_='search-result') or \
                               soup.find_all('div', class_='cuit-result')
            
            for container in result_containers:
                result = self._parse_result_container(container, search_url)
                if result:
                    results.append(result)
            
            # If no results found with generic selectors, try to find by pattern
            if not results:
                # Look for CUIT pattern in the page
                cuit_pattern = r'\b(\d{2}-\d{8}-\d{1}|\d{11})\b'
                cuits_found = re.findall(cuit_pattern, response.text)
                
                for cuit in cuits_found:
                    # Try to find associated name
                    results.append(CUITResult(
                        cuit=cuit,
                        name=name,
                        tipo_persona="Unknown",
                        estado="Unknown",
                        search_url=search_url
                    ))
            
            self.logger.info(f"Found {len(results)} results")
            return results
            
        except requests.RequestException as e:
            self.logger.error(f"Request error: {e}")
            return []
    
    def _search_with_selenium(self, name: str) -> List[CUITResult]:
        """Search using Selenium for JavaScript-heavy pages"""
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium not installed")
        
        self._rate_limit()
        
        # Setup Chrome options
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            search_url = f"{self.base_url}/search/{quote(name)}"
            self.logger.info(f"Selenium searching: {search_url}")
            
            driver.get(search_url)
            
            # Wait for results to load
            wait = WebDriverWait(driver, 10)
            
            # Handle potential ad blocker detection
            try:
                # Check if ad blocker message appears
                ad_blocker_msg = driver.find_elements(By.XPATH, "//*[contains(text(), 'Bloqueador de Anuncios')]")
                if ad_blocker_msg:
                    self.logger.warning("Ad blocker detection found")
            except:
                pass
            
            # Wait for results
            results = []
            
            # Try different selectors for results
            selectors = [
                "//div[@class='resultado']",
                "//article[contains(@class, 'search-result')]",
                "//div[contains(@class, 'cuit-result')]",
                "//a[contains(@href, '/detalle/')]"
            ]
            
            for selector in selectors:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    for element in elements:
                        result = self._parse_selenium_element(element, search_url)
                        if result:
                            results.append(result)
                    break
            
            # Extract CUITs from page if no structured results
            if not results:
                page_text = driver.page_source
                cuit_pattern = r'\b(\d{2}-\d{8}-\d{1}|\d{11})\b'
                cuits_found = re.findall(cuit_pattern, page_text)
                
                for cuit in set(cuits_found):
                    results.append(CUITResult(
                        cuit=cuit,
                        name=name,
                        tipo_persona="Unknown",
                        estado="Unknown",
                        search_url=search_url
                    ))
            
            return results
            
        except Exception as e:
            self.logger.error(f"Selenium error: {e}")
            return []
        finally:
            driver.quit()
    
    def _search_with_playwright(self, name: str) -> List[CUITResult]:
        """Search using Playwright (modern alternative to Selenium)"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed")
        
        self._rate_limit()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            
            try:
                search_url = f"{self.base_url}/search/{quote(name)}"
                self.logger.info(f"Playwright searching: {search_url}")
                
                page.goto(search_url, wait_until='networkidle')
                
                # Handle ad blocker detection
                if page.locator("text=Bloqueador de Anuncios").count() > 0:
                    self.logger.warning("Ad blocker detection found")
                
                results = []
                
                # Try to find result elements
                result_selectors = [
                    ".resultado",
                    ".search-result",
                    ".cuit-result",
                    "a[href*='/detalle/']"
                ]
                
                for selector in result_selectors:
                    elements = page.locator(selector)
                    count = elements.count()
                    
                    if count > 0:
                        for i in range(count):
                            element = elements.nth(i)
                            text = element.text_content()
                            href = element.get_attribute('href') if element.get_attribute('href') else None
                            
                            # Extract CUIT from text or href
                            cuit_match = re.search(r'\b(\d{2}-\d{8}-\d{1}|\d{11})\b', text or '')
                            if cuit_match:
                                results.append(CUITResult(
                                    cuit=cuit_match.group(1),
                                    name=name,
                                    tipo_persona="Unknown",
                                    estado="Unknown",
                                    search_url=search_url,
                                    detail_url=f"{self.base_url}{href}" if href else None
                                ))
                        break
                
                # Fallback: extract CUITs from page
                if not results:
                    page_content = page.content()
                    cuit_pattern = r'\b(\d{2}-\d{8}-\d{1}|\d{11})\b'
                    cuits_found = re.findall(cuit_pattern, page_content)
                    
                    for cuit in set(cuits_found):
                        results.append(CUITResult(
                            cuit=cuit,
                            name=name,
                            tipo_persona="Unknown",
                            estado="Unknown",
                            search_url=search_url
                        ))
                
                return results
                
            except Exception as e:
                self.logger.error(f"Playwright error: {e}")
                return []
            finally:
                browser.close()
    
    def _parse_result_container(self, container, search_url: str) -> Optional[CUITResult]:
        """Parse a result container from BeautifulSoup"""
        try:
            # Extract CUIT - adapt based on actual HTML
            cuit_elem = container.find(string=re.compile(r'\d{2}-\d{8}-\d{1}|\d{11}'))
            if not cuit_elem:
                return None
            
            cuit = re.search(r'(\d{2}-\d{8}-\d{1}|\d{11})', str(cuit_elem)).group(1)
            
            # Extract name
            name_elem = container.find(['h2', 'h3', 'h4', 'a'])
            name = name_elem.get_text(strip=True) if name_elem else "Unknown"
            
            # Extract other details
            tipo_elem = container.find(string=re.compile(r'Persona (Física|Jurídica)'))
            tipo = "Persona " + tipo_elem.split()[-1] if tipo_elem else "Unknown"
            
            # Get detail URL if available
            link_elem = container.find('a', href=True)
            detail_url = f"{self.base_url}{link_elem['href']}" if link_elem else None
            
            return CUITResult(
                cuit=cuit,
                name=name,
                tipo_persona=tipo,
                estado="Unknown",
                search_url=search_url,
                detail_url=detail_url
            )
            
        except Exception as e:
            self.logger.debug(f"Error parsing container: {e}")
            return None
    
    def _parse_selenium_element(self, element, search_url: str) -> Optional[CUITResult]:
        """Parse a result element from Selenium"""
        try:
            text = element.text
            
            # Extract CUIT
            cuit_match = re.search(r'(\d{2}-\d{8}-\d{1}|\d{11})', text)
            if not cuit_match:
                return None
            
            cuit = cuit_match.group(1)
            
            # Try to get href
            try:
                href = element.get_attribute('href')
                detail_url = href if href else None
            except:
                detail_url = None
            
            return CUITResult(
                cuit=cuit,
                name=text.split('\n')[0] if '\n' in text else "Unknown",
                tipo_persona="Unknown",
                estado="Unknown",
                search_url=search_url,
                detail_url=detail_url
            )
            
        except Exception as e:
            self.logger.debug(f"Error parsing element: {e}")
            return None
    
    def get_cuit_details(self, detail_url: str) -> Optional[CUITResult]:
        """Get detailed information from a CUIT detail page"""
        self._rate_limit()
        
        try:
            response = self.session.get(detail_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract detailed information
            cuit = self._extract_text_by_pattern(soup, r'CUIT:\s*(\d{2}-\d{8}-\d{1})')
            name = self._extract_text_by_pattern(soup, r'Razón Social:\s*(.+)')
            
            # Extract other fields based on common patterns
            result = CUITResult(
                cuit=cuit or "Unknown",
                name=name or "Unknown",
                tipo_persona=self._extract_text_by_pattern(soup, r'Tipo:\s*(Persona \w+)') or "Unknown",
                estado=self._extract_text_by_pattern(soup, r'Estado:\s*(\w+)') or "Unknown",
                direccion=self._extract_text_by_pattern(soup, r'Dirección:\s*(.+)'),
                localidad=self._extract_text_by_pattern(soup, r'Localidad:\s*(.+)'),
                provincia=self._extract_text_by_pattern(soup, r'Provincia:\s*(.+)'),
                condicion_impositiva=self._extract_text_by_pattern(soup, r'Condición:\s*(.+)'),
                detail_url=detail_url
            )
            
            # Extract activities
            activities = []
            activity_section = soup.find(string=re.compile(r'Actividad'))
            if activity_section:
                activity_list = activity_section.find_next('ul')
                if activity_list:
                    activities = [li.get_text(strip=True) for li in activity_list.find_all('li')]
            
            result.actividades = activities if activities else None
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting details: {e}")
            return None
    
    def _extract_text_by_pattern(self, soup, pattern: str) -> Optional[str]:
        """Extract text using regex pattern"""
        match = soup.find(string=re.compile(pattern))
        if match:
            result = re.search(pattern, match)
            if result and len(result.groups()) > 0:
                return result.group(1).strip()
        return None
    
    def export_results(self, results: List[CUITResult], filename: str = None):
        """Export results to JSON and CSV"""
        if not results:
            self.logger.warning("No results to export")
            return
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cuit_search_results_{timestamp}"
        
        # Create outputs directory
        os.makedirs('outputs', exist_ok=True)
        
        # Export to JSON
        json_file = f"outputs/{filename}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json_data = [
                {
                    'cuit': r.cuit,
                    'name': r.name,
                    'tipo_persona': r.tipo_persona,
                    'estado': r.estado,
                    'direccion': r.direccion,
                    'localidad': r.localidad,
                    'provincia': r.provincia,
                    'condicion_impositiva': r.condicion_impositiva,
                    'actividades': r.actividades,
                    'search_url': r.search_url,
                    'detail_url': r.detail_url
                }
                for r in results
            ]
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        # Export to CSV
        import csv
        csv_file = f"outputs/{filename}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'CUIT', 'Nombre', 'Tipo Persona', 'Estado',
                'Dirección', 'Localidad', 'Provincia',
                'Condición Impositiva', 'URL Detalle'
            ])
            
            for r in results:
                writer.writerow([
                    r.cuit, r.name, r.tipo_persona, r.estado,
                    r.direccion, r.localidad, r.provincia,
                    r.condicion_impositiva, r.detail_url
                ])
        
        self.logger.info(f"Results exported to:\n- {json_file}\n- {csv_file}")


def main():
    """Example usage and testing"""
    
    # Example 1: Basic search with requests
    print("=== Example 1: Basic Search with Requests ===")
    scraper = CUITOnlineScraper(method="requests")
    results = scraper.search_by_name("verdier piazza")
    
    for result in results:
        print(f"CUIT: {result.cuit}")
        print(f"Name: {result.name}")
        print(f"Type: {result.tipo_persona}")
        print(f"Status: {result.estado}")
        print("-" * 40)
    
    # Export results
    if results:
        scraper.export_results(results, "verdier_piazza_search")
    
    # Example 2: Using Selenium (if installed)
    if SELENIUM_AVAILABLE:
        print("\n=== Example 2: Search with Selenium ===")
        scraper_selenium = CUITOnlineScraper(method="selenium", headless=True)
        results_selenium = scraper_selenium.search_by_name("gomez martin")
        
        if results_selenium:
            scraper_selenium.export_results(results_selenium, "gomez_martin_search")
    
    # Example 3: Using Playwright (if installed)
    if PLAYWRIGHT_AVAILABLE:
        print("\n=== Example 3: Search with Playwright ===")
        scraper_playwright = CUITOnlineScraper(method="playwright", headless=True)
        results_playwright = scraper_playwright.search_by_name("empresa ejemplo")
        
        if results_playwright:
            scraper_playwright.export_results(results_playwright, "empresa_ejemplo_search")
    
    # Example 4: Get detailed information
    if results and results[0].detail_url:
        print("\n=== Example 4: Get Detailed Information ===")
        details = scraper.get_cuit_details(results[0].detail_url)
        if details:
            print(f"Detailed info for {details.cuit}:")
            print(f"- Address: {details.direccion}")
            print(f"- City: {details.localidad}")
            print(f"- Province: {details.provincia}")
            print(f"- Tax Status: {details.condicion_impositiva}")


if __name__ == "__main__":
    main()