"""Tests for invoice data and notebook behavior."""

import io
import json
import os
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPOSITORY_ROOT / "examples/data/hotel_invoices"
EXTRACTIONS = DATA_ROOT / "extracted_invoice_json"
NOTEBOOK = REPOSITORY_ROOT / "examples/Data_extraction_transformation.ipynb"


class InvoiceDataTests(unittest.TestCase):
    def test_extractions_cover_source_invoices(self):
        expected = {
            path.stem + "_extracted.json"
            for path in (DATA_ROOT / "receipts_2019_de_hotel").glob("*.pdf")
        }
        actual = {path.name for path in EXTRACTIONS.glob("*.json")}
        self.assertTrue(expected, "The invoice fixtures must not be empty")
        self.assertEqual(actual, expected)

    def test_extractions_are_arrays_of_page_objects(self):
        for path in EXTRACTIONS.glob("*.json"):
            with self.subTest(invoice=path.name):
                pages = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(pages, list)
                self.assertTrue(pages)
                for page in pages:
                    self.assertIsInstance(page, dict)

    def test_recorded_sample_matches_dataset(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        samples = [
            cell
            for cell in notebook["cells"]
            if "sample_invoice_path =" in "".join(cell["source"])
        ]
        self.assertEqual(len(samples), 1)
        output = "".join(
            "".join(item["text"])
            for item in samples[0]["outputs"]
            if item.get("name") == "stdout"
        )
        sample = EXTRACTIONS / "premierinn_GABCI19014325_extracted.json"
        self.assertEqual(
            json.loads(output), json.loads(sample.read_text(encoding="utf-8"))
        )

    def test_notebook_extract_display_transform_offline(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        code = [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code"
        ]

        def cell_source(marker):
            matches = [source for source in code if marker in source]
            self.assertEqual(len(matches), 1, marker)
            return matches[0]

        sample_name = "premierinn_GABCI19014325_extracted.json"
        multipage_name = "hampton-25789_extracted.json"
        invoices = {
            name: json.loads((EXTRACTIONS / name).read_text(encoding="utf-8"))
            for name in [sample_name, multipage_name]
        }
        self.assertGreater(len(invoices[multipage_name]), 1)

        def mock_pdf_conversion(path):
            name = Path(path).stem + "_extracted.json"
            return [json.dumps(page) for page in invoices[name]]

        create_response = Mock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"normalized": true}')
                    )
                ]
            )
        )
        extract_response = Mock(side_effect=lambda encoded_page: encoded_page)
        namespace = {
            "os": os,
            "json": json,
            "client": SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=create_response)
                )
            ),
            "pdf_to_base64_images": mock_pdf_conversion,
            "extract_invoice_data": extract_response,
        }

        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            data = Path("data/hotel_invoices")
            receipts = data / "receipts_2019_de_hotel"
            receipts.mkdir(parents=True)
            for name in invoices:
                (receipts / name.replace("_extracted.json", ".pdf")).touch()
            schema = (DATA_ROOT / "invoice_schema.json").read_text(encoding="utf-8")
            (data / "invoice_schema.json").write_text(schema, encoding="utf-8")

            exec(cell_source("def main_extract("), namespace)
            output = io.StringIO()
            with redirect_stdout(output):
                exec(cell_source("sample_invoice_path ="), namespace)
            self.assertEqual(json.loads(output.getvalue()), invoices[sample_name])
            exec(cell_source("def main_transform("), namespace)

            for name, pages in invoices.items():
                with self.subTest(invoice=name):
                    raw = data / "extracted_invoice_json" / name
                    self.assertEqual(
                        json.loads(raw.read_text(encoding="utf-8")), pages
                    )
                    transformed = (
                        data / "transformed_invoice_json" / ("transformed_" + name)
                    )
                    self.assertEqual(
                        json.loads(transformed.read_text(encoding="utf-8")),
                        {"normalized": True},
                    )
            self.assertEqual(
                extract_response.call_count, sum(map(len, invoices.values()))
            )
            self.assertEqual(create_response.call_count, len(invoices))


if __name__ == "__main__":
    unittest.main()
