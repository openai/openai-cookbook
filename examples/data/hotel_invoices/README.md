# Hotel invoice sample data

`extracted_invoice_json/` is the single directory for raw invoice extractions.
The extraction, sample-display, and transformation cells in
[`Data_extraction_transformation.ipynb`](../../Data_extraction_transformation.ipynb)
share this path. Keep alternate runs outside this sample-data directory.

## Consolidation and version selection

The repository previously contained another directory named
`extracted_invoice_json `, with a trailing space that prevented Windows checkout.
The two directories contained the same 31 filenames, but every corresponding JSON
file differed. They were both introduced in
[commit `ffdd529`](https://github.com/openai/openai-cookbook/commit/ffdd52937d0c82d4fe3e85314ad88439c4a0e3ce)
on July 9, 2024, and neither set was updated afterward before consolidation.
Git therefore provides no evidence that either extraction run is newer.

The existing no-space dataset is retained because the notebook already reads and
writes it. No values are merged from the other run. The other run remains
[available in Git history](https://github.com/openai/openai-cookbook/tree/ffdd52937d0c82d4fe3e85314ad88439c4a0e3ce/examples/data/hotel_invoices/extracted_invoice_json%20).
The notebook now loads its displayed sample from the retained file.

## JSON compatibility

Both runs contain valid JSON, but they are not interchangeable snapshots or a
stable schema. Differences include:

| Example | Retained no-space dataset | Former trailing-space dataset |
| --- | --- | --- |
| `premierinn_GABCI19014325_extracted.json`, first page, `Invoice Information.Kundereferenz` | `null` | `2` |
| `20190119_002_extracted.json`, first page, `Charges[0].Belastung` | `"110.00"` (string) | `110.0` (number) |
| `20190119_002_extracted.json`, first-page keys | Includes `Payment Information` | Includes `Finanzamt` and `Kreditkarten Details` instead |

Raw files contain an array of page objects with invoice-specific keys, languages,
and value types. Files in `transformed_invoice_json/` instead contain normalized
objects for database ingestion. Apply the notebook's transformation step before
assuming the normalized field names or types; JSON parsing alone does not verify
the accuracy of extracted invoice values.

If a local workflow used the former trailing-space path or
`extracted_invoice_json_alternate/`, update it to `extracted_invoice_json/` and
check any assumptions about keys, types, or particular values. Preserve any
run-specific data your workflow needs outside this sample-data directory.

## Offline regression checks

From the repository root, run:

```bash
python -m unittest discover -s .github/scripts -p 'test_invoice_data.py' -v
```

These checks enforce one extraction directory, match raw JSON files to the source
PDFs, validate page-array structure, and exercise the notebook's extraction,
display, and transformation cells with mocked API and PDF-conversion calls.
The checks do not require an API key or make network requests.
