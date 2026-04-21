"""Refresh a Form 1040 JSON package from staged tax PDFs plus agent-supplied adjustments."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from build_form1040 import build_summary, write_summary_artifacts
from parse_w2 import parse


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _list_tax_document_pdfs(documents_dir: Path) -> list[Path]:
    if not documents_dir.is_dir():
        raise ValueError(f"tax document directory not found: {documents_dir}")

    pdfs = sorted(
        path for path in documents_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdfs:
        raise ValueError(f"no staged tax PDFs found in {documents_dir}")
    return pdfs


def _extract_pdf_text(pdf_path: Path, text_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf_path), str(text_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown pdftotext error"
        raise RuntimeError(f"pdftotext failed for {pdf_path.name}: {stderr}")
    return text_path.read_text(encoding="utf-8", errors="ignore")


def _detect_document_type(text: str, pdf_path: Path | None = None) -> str:
    normalized = text.lower()
    if (
        ("w-2" in normalized and "wage and tax statement" in normalized)
        or "form w-2" in normalized
        or (
            "employer's name, address, and zip code" in normalized
            and "federal income tax withheld" in normalized
        )
    ):
        return "w2"
    if "form 1099-int" in normalized:
        return "1099-int"
    if "form 1099-div" in normalized:
        return "1099-div"
    if "form 1099-nec" in normalized:
        return "1099-nec"
    if "form 1099-misc" in normalized:
        return "1099-misc"
    if "form 1099-r" in normalized:
        return "1099-r"
    if pdf_path is not None:
        filename = pdf_path.name.lower()
        if "w-2" in filename or "w2" in filename:
            return "w2"
    if "form 1099" in normalized:
        return "other_1099"
    return "other_tax_document"


def _default_supplemental_note(document_type: str) -> str:
    if document_type.startswith("1099") or document_type == "other_1099":
        return "Detected a non-W-2 tax form. Agent review may map amounts into the filing inputs."
    return "Detected a supplemental tax document that is not part of the deterministic W-2 parser."


def _load_agent_tax_adjustments(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"other_income": {}, "additional_payments": {}, "documents": []}
    return _load_json(path)


def _parse_staged_documents(
    documents_dir: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    parsed_w2_documents: list[dict[str, object]] = []
    supplemental_documents: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="runloop-w2-") as temp_dir:
        temp_root = Path(temp_dir)
        for pdf_path in _list_tax_document_pdfs(documents_dir):
            text_path = temp_root / f"{pdf_path.stem}.txt"
            text = _extract_pdf_text(pdf_path, text_path)
            document_type = _detect_document_type(text, pdf_path)
            if document_type == "w2":
                try:
                    parsed = parse(str(text_path))
                except Exception as exc:
                    raise ValueError(f"failed to parse W-2 PDF {pdf_path.name}: {exc}") from exc
                parsed["source_document_filename"] = pdf_path.name
                parsed_w2_documents.append(parsed)
                continue

            supplemental_documents.append(
                {
                    "filename": pdf_path.name,
                    "type": document_type,
                    "mappedAmounts": {"other_income": {}, "additional_payments": {}},
                    "notes": [_default_supplemental_note(document_type)],
                }
            )

    if not parsed_w2_documents:
        raise ValueError("at least one staged W-2 PDF is required to build the filing package")
    return parsed_w2_documents, supplemental_documents


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "Usage: python3 refresh_tax_return.py <documents_dir> <task_config.json> <output_json>",
            file=sys.stderr,
        )
        return 2

    documents_dir = Path(argv[1])
    config_path = Path(argv[2])
    output_path = Path(argv[3])
    adjustments_path = config_path.parent / "agent_tax_adjustments.json"

    parsed_w2s, supplemental_documents = _parse_staged_documents(documents_dir)
    summary = build_summary(
        parsed_w2s,
        _load_json(config_path),
        agent_tax_adjustments=_load_agent_tax_adjustments(adjustments_path),
        detected_supplemental_documents=supplemental_documents,
    )
    write_summary_artifacts(summary, output_path=output_path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
