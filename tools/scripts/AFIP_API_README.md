# AFIP CUIT Lookup Service

This service provides official AFIP/ARCA data lookup for Argentine CUIT numbers using the [TusFacturas.app API](https://developers.tusfacturas.app/consultas-varias-a-servicios-afip-arca/api-factura-electronica-afip-clientes-consultar-cuit-en-constancia-de-inscripcion).

## Features

- **Official AFIP Data**: Direct access to AFIP/ARCA constancia de inscripción data
- **Comprehensive Information**: Company name, tax status, address, economic activities
- **Rate Limited**: Built-in rate limiting to respect API limits  
- **Bulk Operations**: Support for bulk CUIT lookups
- **HubSpot Integration**: Ready-to-use integration with HubSpot CRM
- **Export Capabilities**: CSV export functionality
- **Error Handling**: Robust error handling and logging

## Prerequisites

### 1. TusFacturas.app Account

You need a TusFacturas.app account with ARCA link:

- **Important**: This functionality is **NOT available** in the DEV plan
- You need a production account with ARCA linkage
- Your CUIT must be linked with ARCA/AFIP

### 2. API Credentials

Obtain the following credentials from your TusFacturas.app account:

- `apikey`: Your API key
- `usertoken`: Your user token  
- `apitoken`: Your API token

## Setup

### 1. Install Dependencies

```bash
pip install requests
```

### 2. Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
export TUSFACTURAS_API_KEY="your_api_key_here"
export TUSFACTURAS_USER_TOKEN="your_user_token_here"  
export TUSFACTURAS_API_TOKEN="your_api_token_here"

# Optional: HubSpot integration
export HUBSPOT_API_KEY="your_hubspot_key"
```

### 3. Test the Setup

```bash
cd tools/scripts
python afip_cuit_lookup.py
```

## Usage

### Basic CUIT Lookup

```python
from afip_cuit_lookup import AFIPCUITLookupService

# Initialize service
service = AFIPCUITLookupService()

# Look up a single CUIT
cuit = "30712293841"
result = service.lookup_cuit(cuit)

if result and not result.error:
    print(f"Company: {result.razon_social}")
    print(f"Tax Status: {result.condicion_impositiva}")
    print(f"Status: {result.estado}")
    print(f"Address: {result.direccion}, {result.localidad}")
    print(f"Activities: {len(result.actividades)}")
else:
    print("CUIT not found or error occurred")
```

### Bulk CUIT Lookup

```python
# Multiple CUITs
cuits = ["30712293841", "20123456789", "30987654321"]

# Perform bulk lookup
results = service.bulk_lookup(cuits)

# Export to CSV
service.export_results_to_csv(results, "my_cuit_results.csv")
```

### HubSpot Integration

```python
from afip_integration_example import AFIPHubSpotIntegration

# Initialize integration
integration = AFIPHubSpotIntegration()

# Update a single company
success = integration.update_company_with_afip_data(
    company_id="12345", 
    cuit="30712293841"
)

# Bulk update companies
companies_data = [
    {'company_id': '12345', 'cuit': '30712293841'},
    {'company_id': '12346', 'cuit': '20123456789'}
]

results = integration.bulk_update_companies(companies_data)
```

## API Response Structure

The AFIP API returns the following information:

```json
{
   "error": "N",
   "razon_social": "COMPANY NAME",
   "condicion_impositiva": "RESPONSABLE INSCRIPTO",
   "direccion": "Company Address 123",
   "localidad": "Buenos Aires",
   "codigopostal": "1001",
   "estado": "ACTIVO",
   "provincia": "CAPITAL FEDERAL",
   "actividad": [
        {
            "descripcion": "SERVICIOS DE CONSULTORES EN INFORMÁTICA",
            "id": "620100",
            "nomenclador": "883",
            "periodo": "201311"
        }
   ],
   "errores": []
}
```

### Tax Status Values (condicion_impositiva)

- `MONOTRIBUTO`: Small taxpayer regime
- `RESPONSABLE INSCRIPTO`: VAT registered taxpayer  
- `EXENTO`: Tax exempt

### Status Values (estado)

- `ACTIVO`: Active taxpayer
- Other statuses as defined by AFIP

## HubSpot Property Mapping

The integration maps AFIP data to HubSpot properties:

| AFIP Field | HubSpot Property | Description |
|------------|------------------|-------------|
| razon_social | name | Company name |
| condicion_impositiva | condicion_fiscal | Tax condition |
| direccion | address | Street address |
| localidad | city | City |
| provincia | state | Province/State |
| codigopostal | zip | Postal code |
| estado | afip_status | AFIP status |
| actividad[0] | actividad_principal | Main economic activity |
| actividad[0].id | codigo_actividad_principal | Activity code |
| cuit | cuit_numero | CUIT number |

## Error Handling

The service handles various error scenarios:

### AFIP Errors
- CUIT not found in AFIP database
- CUIT has pending requirements
- Blocked constancia due to missing fiscal domicile

### API Errors  
- Network connectivity issues
- Rate limiting (handled automatically)
- Invalid credentials
- Malformed responses

### Input Validation
- Invalid CUIT format (must be 11 digits)
- Missing credentials

## Rate Limiting

The service implements rate limiting:

- **Default**: 1 second between requests
- **Configurable**: Adjust `min_request_interval` in service initialization
- **Automatic**: Built-in delays between bulk operations

## Cost Considerations

Each API call counts as one request in your TusFacturas.app subscription:

- **Single lookup**: 1 request
- **Bulk lookup**: N requests (where N = number of CUITs)
- Monitor your usage through TusFacturas.app dashboard

## Integration with Existing Scripts

### With CUIT Migration Script

```python
# In your existing migration script
from scripts.afip_cuit_lookup import AFIPCUITLookupService

def enrich_company_with_afip_data(company_data):
    service = AFIPCUITLookupService()
    
    if company_data.get('cuit'):
        afip_info = service.lookup_cuit(company_data['cuit'])
        if afip_info and not afip_info.error:
            # Update company data with AFIP information
            company_data['official_name'] = afip_info.razon_social
            company_data['tax_status'] = afip_info.condicion_impositiva
            company_data['address'] = afip_info.direccion
            # ... more mappings
    
    return company_data
```

## Troubleshooting

### Common Issues

1. **"Missing credentials" error**
   - Ensure environment variables are set correctly
   - Check that credentials are valid

2. **"Not available in DEV plan" error**  
   - Upgrade to a production TusFacturas.app plan
   - Ensure ARCA linkage is configured

3. **"CUIT blocked" errors**
   - CUIT may have pending AFIP requirements
   - Contact the company to resolve AFIP issues

4. **Rate limiting issues**
   - Increase `min_request_interval` in service configuration
   - Reduce batch size for bulk operations

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

service = AFIPCUITLookupService()
```

## Security Considerations

- **Never commit credentials** to version control
- Use environment variables or secure credential storage
- **Rate limiting** prevents API abuse
- **Input validation** prevents injection attacks

## License & Legal

- Respect TusFacturas.app terms of service
- AFIP data usage subject to Argentine regulations
- Implement appropriate data protection measures
- Consider GDPR/privacy implications for personal data

## Support

For issues related to:

- **AFIP API functionality**: [TusFacturas.app Support](https://developers.tusfacturas.app/)
- **Script issues**: Create an issue in this repository
- **AFIP data accuracy**: Contact AFIP directly

## Examples

See `afip_integration_example.py` for comprehensive usage examples including:

- Single CUIT lookup
- Bulk operations  
- HubSpot integration
- Error handling patterns
- Company identification workflows