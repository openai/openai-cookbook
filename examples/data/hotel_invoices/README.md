# Hotel invoice sample data

Sample data for
[`Data_extraction_transformation.ipynb`](../../Data_extraction_transformation.ipynb):

- `receipts_2019_de_hotel/`: source PDF invoices.
- `extracted_invoice_json/`: raw extractions, with one JSON object per page in an
  array for each invoice.
- `invoice_schema.json`: the target field names and formats for transformation.
- `transformed_invoice_json/`: normalized JSON objects for database ingestion.

## JSON formats

Raw extractions can use different keys, languages, and value types across
invoices and extraction runs. For example:

| File | Field on the first page | Value and type |
| --- | --- | --- |
| `premierinn_GABCI19014325_extracted.json` | `Invoice Information.Kundereferenz` | `null` |
| `20190119_002_extracted.json` | `Charges[0].Belastung` | `"110.00"` (string) |

Handle missing fields, `null` values, and numbers encoded as strings when reading
raw extractions. Use the notebook's transformation step to map these arrays to
the normalized field names and types expected by the database-loading step.
