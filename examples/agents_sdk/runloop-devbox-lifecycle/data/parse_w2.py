"""Extract 2024 W-2 fields from pdftotext output of ``sample_w2.pdf``."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CITY_STATE_ZIP_RE = re.compile(r"(?P<city>.+?),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$")
BOX_VALUES_RE = re.compile(
    r"8 Allocated tips\s+"
    r"(\d+(?:,\d{3})*\.\d{2})\s+"
    r"(\d+(?:,\d{3})*\.\d{2})\s+"
    r"(\d+(?:,\d{3})*\.\d{2})\s+"
    r"2 Federal income tax withheld\s+"
    r"(\d+(?:,\d{3})*\.\d{2})\s+"
    r"(\d+(?:,\d{3})*\.\d{2})\s+"
    r"(\d+(?:,\d{3})*\.\d{2})"
)


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").replace("’", "'")


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _split_city_state_zip(value: str) -> tuple[str, str, str]:
    match = CITY_STATE_ZIP_RE.match(value)
    if not match:
        raise ValueError(f"could not parse city/state/zip line: {value!r}")
    return match.group("city"), match.group("state"), match.group("zip")


def _find_block(lines: list[str], labels: tuple[str, ...]) -> tuple[str, str, str]:
    for index, line in enumerate(lines):
        if any(label in line for label in labels):
            values = lines[index + 1 : index + 4]
            if len(values) == 3:
                return values[0], values[1], values[2]
            break
    raise ValueError(f"block not found for labels: {labels!r}")


def _amount(value: str) -> float:
    return float(value.replace(",", ""))


def parse(path: str) -> dict[str, object]:
    text = _load_text(Path(path))
    lines = _clean_lines(text)

    employer_name, employer_address, employer_csz = _find_block(
        lines, ("Employer's name, address, and ZIP code",)
    )
    employee_name, employee_address, employee_csz = _find_block(
        lines,
        (
            "e/f Employee's name, address, and ZIP code",
            "Employee's name, address, and ZIP code",
        ),
    )

    employee_city, employee_state, employee_zip = _split_city_state_zip(employee_csz)
    employer_city, employer_state, employer_zip = _split_city_state_zip(employer_csz)

    ssn_match = re.search(r"XXX-XX-\d{4}|\d{3}-\d{2}-\d{4}", text)
    ein_match = re.search(r"\b\d{2}-\d{7}\b", text)
    if not ssn_match:
        raise ValueError("could not find SSN")
    if not ein_match:
        raise ValueError("could not find employer EIN")

    box_match = BOX_VALUES_RE.search(text)
    if not box_match:
        raise ValueError("could not parse W-2 box values from labeled block")

    names = employee_name.split()
    if len(names) < 2:
        raise ValueError(f"employee name must include first and last name: {employee_name!r}")

    return {
        "taxpayer_name": employee_name,
        "first_name": names[0],
        "last_name": " ".join(names[1:]),
        "ssn": ssn_match.group(0),
        "address": employee_address,
        "city": employee_city,
        "state": employee_state,
        "zip_code": employee_zip,
        "employer_name": employer_name,
        "employer_ein": ein_match.group(0),
        "employer_address": employer_address,
        "employer_city": employer_city,
        "employer_state": employer_state,
        "employer_zip_code": employer_zip,
        "wages": _amount(box_match.group(1)),
        "tax_withheld": _amount(box_match.group(4)),
        "social_security_wages": _amount(box_match.group(2)),
        "social_security_tax_withheld": _amount(box_match.group(5)),
        "medicare_wages": _amount(box_match.group(3)),
        "medicare_tax_withheld": _amount(box_match.group(6)),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: python3 {argv[0]} <pdftotext_output.txt>", file=sys.stderr)
        return 2
    try:
        print(json.dumps(parse(argv[1]), indent=2))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
