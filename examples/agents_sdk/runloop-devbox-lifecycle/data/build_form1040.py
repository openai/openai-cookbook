"""Build a deterministic 2024 Form 1040-style JSON package from parsed W-2 data."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import cast

STANDARD_DEDUCTIONS = {
    "single": 14600.0,
    "married_filing_jointly": 29200.0,
    "married_filing_separately": 14600.0,
    "head_of_household": 21900.0,
}

FILING_STATUS_FLAGS = {
    "single": {
        "single": True,
        "marriedFilingJointly": False,
        "marriedFilingSeparately": False,
        "headOfHousehold": False,
        "qualifyingWidow": False,
    },
    "married_filing_jointly": {
        "single": False,
        "marriedFilingJointly": True,
        "marriedFilingSeparately": False,
        "headOfHousehold": False,
        "qualifyingWidow": False,
    },
    "married_filing_separately": {
        "single": False,
        "marriedFilingJointly": False,
        "marriedFilingSeparately": True,
        "headOfHousehold": False,
        "qualifyingWidow": False,
    },
    "head_of_household": {
        "single": False,
        "marriedFilingJointly": False,
        "marriedFilingSeparately": False,
        "headOfHousehold": True,
        "qualifyingWidow": False,
    },
}

TAX_BRACKETS = {
    "single": [
        (11600.0, 0.10),
        (47150.0, 0.12),
        (100525.0, 0.22),
        (191950.0, 0.24),
        (243725.0, 0.32),
        (609350.0, 0.35),
        (math.inf, 0.37),
    ],
    "married_filing_jointly": [
        (23200.0, 0.10),
        (94300.0, 0.12),
        (201050.0, 0.22),
        (383900.0, 0.24),
        (487450.0, 0.32),
        (731200.0, 0.35),
        (math.inf, 0.37),
    ],
    "married_filing_separately": [
        (11600.0, 0.10),
        (47150.0, 0.12),
        (100525.0, 0.22),
        (191950.0, 0.24),
        (243725.0, 0.32),
        (365600.0, 0.35),
        (math.inf, 0.37),
    ],
    "head_of_household": [
        (16550.0, 0.10),
        (63100.0, 0.12),
        (100500.0, 0.22),
        (191950.0, 0.24),
        (243700.0, 0.32),
        (609350.0, 0.35),
        (math.inf, 0.37),
    ],
}

CHILD_TAX_CREDIT_PHASEOUT_THRESHOLDS = {
    "single": 200000.0,
    "head_of_household": 200000.0,
    "married_filing_jointly": 400000.0,
    "married_filing_separately": 200000.0,
}

OTHER_INCOME_FIELDS = (
    "taxable_interest",
    "qualified_dividends",
    "ira_distributions",
    "pensions_annuities",
    "social_security_benefits",
    "capital_gain_loss",
    "schedule_d",
    "additional_income_schedule_1",
)

ADDITIONAL_PAYMENT_FIELDS = (
    "estimated_tax_payments",
    "earned_income_credit",
    "additional_child_tax_credit",
    "american_opportunity_credit",
    "refundable_credits",
)

FORM_DATA_OUTPUT_FILENAME = "f1040_form_data.json"


def _money(value: float) -> float:
    return round(float(value), 2)


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return cast(dict[str, object], payload)


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _nonnegative_integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")

    parsed: int
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field} must be a non-negative integer")
        parsed = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field} must be a non-negative integer")
        try:
            parsed = int(stripped, 10)
        except ValueError as exc:
            raise ValueError(f"{field} must be a non-negative integer") from exc
    else:
        raise ValueError(f"{field} must be a non-negative integer")

    if parsed < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return parsed


def _empty_agent_tax_adjustments() -> dict[str, object]:
    return {
        "other_income": {field: 0.0 for field in OTHER_INCOME_FIELDS},
        "additional_payments": {field: 0.0 for field in ADDITIONAL_PAYMENT_FIELDS},
        "documents": [],
    }


def _normalize_mapped_amounts(payload: object) -> dict[str, dict[str, float]]:
    normalized = {
        "other_income": {field: 0.0 for field in OTHER_INCOME_FIELDS},
        "additional_payments": {field: 0.0 for field in ADDITIONAL_PAYMENT_FIELDS},
    }
    if not isinstance(payload, dict):
        return normalized

    for group_name, field_names in (
        ("other_income", OTHER_INCOME_FIELDS),
        ("additional_payments", ADDITIONAL_PAYMENT_FIELDS),
    ):
        group_payload = payload.get(group_name)
        if not isinstance(group_payload, dict):
            continue
        for field_name in field_names:
            value = group_payload.get(field_name)
            if value is None:
                continue
            normalized[group_name][field_name] = _number(
                value,
                field=f"mappedAmounts.{group_name}.{field_name}",
            )

    return normalized


def _normalize_supplemental_documents(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, object]] = []
    for index, raw_document in enumerate(payload):
        if not isinstance(raw_document, dict):
            continue

        filename = raw_document.get("filename")
        if not isinstance(filename, str) or not filename:
            filename = f"supplemental-document-{index + 1}.pdf"

        document_type = raw_document.get("type")
        if not isinstance(document_type, str) or not document_type:
            document_type = "other_tax_document"

        notes_payload = raw_document.get("notes")
        notes = (
            [str(note) for note in notes_payload if isinstance(note, str)]
            if isinstance(notes_payload, list)
            else []
        )

        normalized.append(
            {
                "filename": filename,
                "type": document_type,
                "mappedAmounts": _normalize_mapped_amounts(raw_document.get("mappedAmounts")),
                "notes": notes,
            }
        )

    return normalized


def _normalize_agent_tax_adjustments(payload: object) -> dict[str, object]:
    normalized = _empty_agent_tax_adjustments()
    if not isinstance(payload, dict):
        return normalized

    explicit_totals_present = False
    for group_name, field_names in (
        ("other_income", OTHER_INCOME_FIELDS),
        ("additional_payments", ADDITIONAL_PAYMENT_FIELDS),
    ):
        group_payload = payload.get(group_name)
        if not isinstance(group_payload, dict):
            continue
        for field_name in field_names:
            if field_name not in group_payload:
                continue
            explicit_totals_present = True
            cast(dict[str, float], normalized[group_name])[field_name] = _number(
                group_payload[field_name],
                field=f"{group_name}.{field_name}",
            )

    documents = _normalize_supplemental_documents(payload.get("documents"))
    normalized["documents"] = documents

    if not explicit_totals_present:
        for document in documents:
            mapped_amounts = cast(dict[str, dict[str, float]], document["mappedAmounts"])
            for group_name in ("other_income", "additional_payments"):
                target_group = cast(dict[str, float], normalized[group_name])
                for field_name, value in mapped_amounts[group_name].items():
                    target_group[field_name] += value

    return normalized


def _merge_tax_inputs(
    task_config: dict[str, object],
    agent_tax_adjustments: object | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    merged_config = json.loads(json.dumps(task_config))
    if not isinstance(merged_config, dict):
        raise ValueError("task_config must serialize to a JSON object")

    adjustments = _normalize_agent_tax_adjustments(agent_tax_adjustments)

    other_income = merged_config.get("other_income")
    if not isinstance(other_income, dict):
        other_income = {}
        merged_config["other_income"] = other_income

    additional_payments = merged_config.get("additional_payments")
    if not isinstance(additional_payments, dict):
        additional_payments = {}
        merged_config["additional_payments"] = additional_payments

    for field_name in OTHER_INCOME_FIELDS:
        base_value = _number(other_income.get(field_name, 0.0), field=field_name)
        other_income[field_name] = _money(
            base_value + cast(dict[str, float], adjustments["other_income"])[field_name]
        )

    for field_name in ADDITIONAL_PAYMENT_FIELDS:
        base_value = _number(additional_payments.get(field_name, 0.0), field=field_name)
        additional_payments[field_name] = _money(
            base_value + cast(dict[str, float], adjustments["additional_payments"])[field_name]
        )

    return merged_config, cast(list[dict[str, object]], adjustments["documents"])


def _tax_computation(
    taxable_income: float, filing_status: str
) -> tuple[float, list[dict[str, object]]]:
    remaining = taxable_income
    lower_bound = 0.0
    total = 0.0
    steps: list[dict[str, object]] = []

    for upper_bound, rate in TAX_BRACKETS[filing_status]:
        if remaining <= 0:
            break
        bracket_span = upper_bound - lower_bound if math.isfinite(upper_bound) else remaining
        income_in_bracket = min(remaining, bracket_span)
        tax = income_in_bracket * rate
        total += tax
        upper_label = "and up" if not math.isfinite(upper_bound) else f"{upper_bound:,.2f}"
        steps.append(
            {
                "bracket": f"{lower_bound:,.2f}-{upper_label}",
                "rate": rate,
                "taxableAmount": _money(income_in_bracket),
                "tax": _money(tax),
            }
        )
        remaining -= income_in_bracket
        lower_bound = upper_bound

    return _money(total), steps


def _child_tax_credit(
    *,
    agi: float,
    filing_status: str,
    qualifying_children: int,
) -> float:
    base_credit = 2000.0 * qualifying_children
    threshold = CHILD_TAX_CREDIT_PHASEOUT_THRESHOLDS[filing_status]
    if agi <= threshold:
        return _money(base_credit)
    phaseout_units = math.ceil((agi - threshold) / 1000.0)
    reduced = max(0.0, base_credit - (phaseout_units * 50.0))
    return _money(reduced)


def _dependent_entries(
    config: dict[str, object], qualifying_children: int
) -> list[dict[str, object]]:
    dependents = config.get("dependents")
    normalized: list[dict[str, object]] = []
    if isinstance(dependents, list):
        for dependent in dependents:
            if isinstance(dependent, dict):
                normalized.append(
                    {
                        "name": dependent.get("name", ""),
                        "ssn": dependent.get("ssn", ""),
                        "relationship": dependent.get("relationship", ""),
                        "qualifiesForChildTaxCredit": bool(
                            dependent.get("qualifiesForChildTaxCredit", False)
                        ),
                        "qualifiesForOtherDependentCredit": bool(
                            dependent.get("qualifiesForOtherDependentCredit", False)
                        ),
                    }
                )

    if normalized:
        claimed_children = sum(
            1 for dependent in normalized if dependent["qualifiesForChildTaxCredit"]
        )
        if claimed_children != qualifying_children:
            raise ValueError(
                "dependents qualifying for child tax credit must match qualifying_children"
            )
        return normalized

    if qualifying_children == 0:
        return []

    return [
        {
            "name": f"Qualifying child {index}",
            "ssn": "",
            "relationship": "Child",
            "qualifiesForChildTaxCredit": True,
            "qualifiesForOtherDependentCredit": False,
        }
        for index in range(1, qualifying_children + 1)
    ]


def _config_source_document_filenames(task_config: dict[str, object]) -> list[str]:
    filenames: list[str] = []

    plural = task_config.get("source_document_filenames")
    if isinstance(plural, list):
        filenames.extend(str(value) for value in plural if isinstance(value, str) and value)

    singular = task_config.get("source_document_filename")
    if isinstance(singular, str) and singular and not filenames:
        filenames.append(singular)

    return filenames


def _normalize_w2_documents(
    w2_fields: dict[str, object] | list[dict[str, object]],
    task_config: dict[str, object],
) -> list[dict[str, object]]:
    raw_documents = w2_fields if isinstance(w2_fields, list) else [w2_fields]
    fallback_filenames = _config_source_document_filenames(task_config)
    normalized: list[dict[str, object]] = []

    for index, raw_document in enumerate(raw_documents):
        if not isinstance(raw_document, dict):
            raise ValueError("expected each parsed W-2 payload to be a JSON object")

        document = dict(raw_document)
        source_filename = document.get("source_document_filename")
        if not isinstance(source_filename, str) or not source_filename:
            if index < len(fallback_filenames):
                source_filename = fallback_filenames[index]
            elif len(fallback_filenames) == 1 and len(raw_documents) == 1:
                source_filename = fallback_filenames[0]
            else:
                source_filename = "sample_w2.pdf" if index == 0 else f"sample_w2_{index + 1}.pdf"

        document["source_document_filename"] = source_filename
        normalized.append(document)

    if not normalized:
        raise ValueError("expected at least one parsed W-2 payload")

    return normalized


def _validate_taxpayer_consistency(w2_documents: list[dict[str, object]]) -> None:
    first = w2_documents[0]
    expected_identity = (
        str(first["first_name"]),
        str(first["last_name"]),
        str(first["ssn"]),
    )

    for document in w2_documents[1:]:
        current_identity = (
            str(document["first_name"]),
            str(document["last_name"]),
            str(document["ssn"]),
        )
        if current_identity != expected_identity:
            raise ValueError("all W-2 documents must belong to the same taxpayer")


def _sum_w2_amounts(w2_documents: list[dict[str, object]], field: str) -> float:
    return sum(_number(document[field], field=field) for document in w2_documents)


def _document_entry(document: dict[str, object]) -> dict[str, object]:
    wages = _number(document["wages"], field="wages")
    federal_tax_withheld = _number(document["tax_withheld"], field="tax_withheld")

    return {
        "filename": document["source_document_filename"],
        "type": "w2",
        "extractedData": {
            "employee": {
                "name": document["taxpayer_name"],
                "ssn": document["ssn"],
                "address": document["address"],
                "city": document["city"],
                "state": document["state"],
                "zipCode": document["zip_code"],
            },
            "employer": {
                "name": document["employer_name"],
                "ein": document["employer_ein"],
                "address": document["employer_address"],
                "city": document["employer_city"],
                "state": document["employer_state"],
                "zipCode": document["employer_zip_code"],
            },
            "boxes": {
                "1": _money(wages),
                "2": _money(federal_tax_withheld),
                "3": _money(
                    _number(
                        document["social_security_wages"],
                        field="social_security_wages",
                    )
                ),
                "4": _money(
                    _number(
                        document["social_security_tax_withheld"],
                        field="social_security_tax_withheld",
                    )
                ),
                "5": _money(
                    _number(
                        document["medicare_wages"],
                        field="medicare_wages",
                    )
                ),
                "6": _money(
                    _number(
                        document["medicare_tax_withheld"],
                        field="medicare_tax_withheld",
                    )
                ),
            },
        },
    }


def _supplemental_document_entry(document: dict[str, object]) -> dict[str, object]:
    mapped_amounts = cast(dict[str, dict[str, float]], document["mappedAmounts"])
    notes = cast(list[str], document["notes"])

    return {
        "filename": document["filename"],
        "type": document["type"],
        "mappedAmounts": {
            "otherIncome": {
                field_name: _money(value)
                for field_name, value in mapped_amounts["other_income"].items()
                if abs(value) > 0
            },
            "additionalPayments": {
                field_name: _money(value)
                for field_name, value in mapped_amounts["additional_payments"].items()
                if abs(value) > 0
            },
        },
        "notes": notes,
    }


def _merge_detected_and_adjusted_documents(
    detected_documents: list[dict[str, object]],
    adjusted_documents: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_filename = {str(document["filename"]): dict(document) for document in detected_documents}

    for adjusted in adjusted_documents:
        filename = str(adjusted["filename"])
        merged = by_filename.get(
            filename, {"filename": filename, "type": adjusted["type"], "notes": []}
        )
        merged["type"] = adjusted["type"]
        merged["mappedAmounts"] = adjusted["mappedAmounts"]
        merged_notes = cast(list[str], merged.get("notes", []))
        for note in cast(list[str], adjusted["notes"]):
            if note not in merged_notes:
                merged_notes.append(note)
        merged["notes"] = merged_notes
        by_filename[filename] = merged

    ordered_filenames = [str(document["filename"]) for document in detected_documents]
    for adjusted in adjusted_documents:
        filename = str(adjusted["filename"])
        if filename not in ordered_filenames:
            ordered_filenames.append(filename)

    return [by_filename[filename] for filename in ordered_filenames]


def _form1040_filing_status(form1040: dict[str, object]) -> str:
    return next(
        (
            status
            for status, flags in FILING_STATUS_FLAGS.items()
            if cast(dict[str, bool], form1040["filingStatus"]) == flags
        ),
        "single",
    )


def _build_form1040_data(summary: dict[str, object]) -> dict[str, object]:
    form1040 = cast(dict[str, object], summary["form1040"])
    taxpayer = cast(dict[str, object], form1040["taxpayer"])
    income = cast(dict[str, object], form1040["income"])
    deductions = cast(dict[str, object], form1040["deductions"])
    tax = cast(dict[str, object], form1040["tax"])
    payments = cast(dict[str, object], form1040["payments"])
    refund_or_owed = cast(dict[str, object], form1040["refundOrOwed"])
    filing_status = _form1040_filing_status(form1040)

    refundable_credit_total = _money(
        _number(payments["earnedIncomeCredit"], field="earnedIncomeCredit")
        + _number(payments["additionalChildTaxCredit"], field="additionalChildTaxCredit")
        + _number(payments["americanOpportunityCredit"], field="americanOpportunityCredit")
        + _number(payments["refundableCredits"], field="refundableCredits")
    )

    return {
        "form": "1040",
        "taxYear": 2024,
        "filingStatus": filing_status,
        "taxpayer": {
            "firstName": taxpayer["firstName"],
            "lastName": taxpayer["lastName"],
            "ssn": taxpayer["ssn"],
            "address": taxpayer["address"],
            "city": taxpayer["city"],
            "state": taxpayer["state"],
            "zipCode": taxpayer["zipCode"],
        },
        "documentsProcessed": summary["documentsProcessed"],
        "lineItems": {
            "1a": _money(_number(income["wages"], field="wages")),
            "1z": _money(_number(income["wages"], field="wages")),
            "2b": _money(_number(income["taxableInterest"], field="taxableInterest")),
            "3a": _money(_number(income["qualifiedDividends"], field="qualifiedDividends")),
            "4b": _money(_number(income["iraDistributions"], field="iraDistributions")),
            "5b": _money(_number(income["pensionsAnnuities"], field="pensionsAnnuities")),
            "6b": _money(_number(income["socialSecurityBenefits"], field="socialSecurityBenefits")),
            "7": _money(_number(income["capitalGainLoss"], field="capitalGainLoss")),
            "8": _money(
                _number(income["additionalIncomeSchedule1"], field="additionalIncomeSchedule1")
            ),
            "9": _money(_number(income["adjustedGrossIncome"], field="adjustedGrossIncome")),
            "10": 0.0,
            "11": _money(_number(income["adjustedGrossIncome"], field="adjustedGrossIncome")),
            "12": _money(_number(deductions["standardDeduction"], field="standardDeduction")),
            "14": _money(_number(deductions["totalDeductions"], field="totalDeductions")),
            "15": _money(_number(form1040["taxableIncome"], field="taxableIncome")),
            "19": _money(_number(tax["nonrefundableCredits"], field="nonrefundableCredits")),
            "24": _money(_number(tax["totalTax"], field="totalTax")),
            "25a": _money(_number(payments["federalTaxWithheld"], field="federalTaxWithheld")),
            "25d": _money(_number(payments["federalTaxWithheld"], field="federalTaxWithheld")),
            "26": _money(_number(payments["estimatedTaxPayments"], field="estimatedTaxPayments")),
            "27": _money(_number(payments["earnedIncomeCredit"], field="earnedIncomeCredit")),
            "28": _money(
                _number(payments["additionalChildTaxCredit"], field="additionalChildTaxCredit")
            ),
            "29": _money(
                _number(payments["americanOpportunityCredit"], field="americanOpportunityCredit")
            ),
            "31": _money(_number(payments["refundableCredits"], field="refundableCredits")),
            "32": refundable_credit_total,
            "33": _money(_number(payments["totalPayments"], field="totalPayments")),
            "34": _money(_number(refund_or_owed["refund"], field="refund")),
            "35a": _money(_number(refund_or_owed["refund"], field="refund")),
            "37": _money(_number(refund_or_owed["amountOwed"], field="amountOwed")),
        },
        "summary": summary["summary"],
    }


def write_summary_artifacts(
    summary: dict[str, object],
    *,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_path.parent / FORM_DATA_OUTPUT_FILENAME).write_text(
        json.dumps(_build_form1040_data(summary), indent=2) + "\n",
        encoding="utf-8",
    )


def build_summary(
    w2_fields: dict[str, object] | list[dict[str, object]],
    task_config: dict[str, object],
    *,
    agent_tax_adjustments: object | None = None,
    detected_supplemental_documents: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    task_config, adjusted_documents = _merge_tax_inputs(task_config, agent_tax_adjustments)
    w2_documents = _normalize_w2_documents(w2_fields, task_config)
    _validate_taxpayer_consistency(w2_documents)
    primary_w2 = w2_documents[0]

    filing_status = str(task_config.get("filing_status", "single"))
    if filing_status not in STANDARD_DEDUCTIONS:
        raise ValueError(f"unsupported filing status: {filing_status}")

    other_income = task_config.get("other_income")
    if not isinstance(other_income, dict):
        other_income = {}
    additional_payments = task_config.get("additional_payments")
    if not isinstance(additional_payments, dict):
        additional_payments = {}

    wages = _sum_w2_amounts(w2_documents, "wages")
    taxable_interest = _number(other_income.get("taxable_interest", 0.0), field="taxable_interest")
    qualified_dividends = _number(
        other_income.get("qualified_dividends", 0.0), field="qualified_dividends"
    )
    ira_distributions = _number(
        other_income.get("ira_distributions", 0.0), field="ira_distributions"
    )
    pensions_annuities = _number(
        other_income.get("pensions_annuities", 0.0), field="pensions_annuities"
    )
    social_security_benefits = _number(
        other_income.get("social_security_benefits", 0.0),
        field="social_security_benefits",
    )
    capital_gain_loss = _number(
        other_income.get("capital_gain_loss", 0.0), field="capital_gain_loss"
    )
    schedule_d = _number(other_income.get("schedule_d", 0.0), field="schedule_d")
    additional_income_schedule_1 = _number(
        other_income.get("additional_income_schedule_1", 0.0),
        field="additional_income_schedule_1",
    )

    agi = wages + taxable_interest + qualified_dividends + ira_distributions
    agi += pensions_annuities + social_security_benefits + capital_gain_loss
    agi += schedule_d + additional_income_schedule_1

    standard_deduction = STANDARD_DEDUCTIONS[filing_status]
    taxable_income = max(0.0, agi - standard_deduction)
    tax_from_table, tax_computation = _tax_computation(taxable_income, filing_status)

    qualifying_children = _nonnegative_integer(
        task_config.get("qualifying_children", 0), field="qualifying_children"
    )
    child_tax_credit = _child_tax_credit(
        agi=agi,
        filing_status=filing_status,
        qualifying_children=qualifying_children,
    )
    total_tax = max(0.0, tax_from_table - child_tax_credit)

    federal_tax_withheld = _sum_w2_amounts(w2_documents, "tax_withheld")
    estimated_tax_payments = _number(
        additional_payments.get("estimated_tax_payments", 0.0),
        field="estimated_tax_payments",
    )
    earned_income_credit = _number(
        additional_payments.get("earned_income_credit", 0.0),
        field="earned_income_credit",
    )
    additional_child_tax_credit = _number(
        additional_payments.get("additional_child_tax_credit", 0.0),
        field="additional_child_tax_credit",
    )
    american_opportunity_credit = _number(
        additional_payments.get("american_opportunity_credit", 0.0),
        field="american_opportunity_credit",
    )
    refundable_credits = _number(
        additional_payments.get("refundable_credits", 0.0),
        field="refundable_credits",
    )
    total_payments = federal_tax_withheld + estimated_tax_payments + earned_income_credit
    total_payments += additional_child_tax_credit + american_opportunity_credit + refundable_credits

    refund = max(0.0, total_payments - total_tax)
    amount_owed = max(0.0, total_tax - total_payments)

    first_name = str(primary_w2["first_name"])
    last_name = str(primary_w2["last_name"])
    dependents = _dependent_entries(task_config, qualifying_children)

    supplemental_documents = _merge_detected_and_adjusted_documents(
        detected_supplemental_documents or [],
        adjusted_documents,
    )

    return {
        "success": True,
        "documentsProcessed": [_document_entry(document) for document in w2_documents]
        + [_supplemental_document_entry(document) for document in supplemental_documents],
        "form1040": {
            "taxpayer": {
                "firstName": first_name,
                "lastName": last_name,
                "ssn": primary_w2["ssn"],
                "address": primary_w2["address"],
                "city": primary_w2["city"],
                "state": primary_w2["state"],
                "zipCode": primary_w2["zip_code"],
            },
            "filingStatus": FILING_STATUS_FLAGS[filing_status],
            "dependents": dependents,
            "income": {
                "wages": _money(wages),
                "taxableInterest": _money(taxable_interest),
                "qualifiedDividends": _money(qualified_dividends),
                "iraDistributions": _money(ira_distributions),
                "pensionsAnnuities": _money(pensions_annuities),
                "socialSecurityBenefits": _money(social_security_benefits),
                "capitalGainLoss": _money(capital_gain_loss),
                "scheduleD": _money(schedule_d),
                "additionalIncomeSchedule1": _money(additional_income_schedule_1),
                "adjustedGrossIncome": _money(agi),
            },
            "deductions": {
                "standardDeduction": _money(standard_deduction),
                "totalDeductions": _money(standard_deduction),
            },
            "taxableIncome": _money(taxable_income),
            "tax": {
                "taxFromTaxTable": _money(tax_from_table),
                "nonrefundableCredits": _money(child_tax_credit),
                "totalTax": _money(total_tax),
                "taxComputation": tax_computation,
            },
            "payments": {
                "federalTaxWithheld": _money(federal_tax_withheld),
                "estimatedTaxPayments": _money(estimated_tax_payments),
                "earnedIncomeCredit": _money(earned_income_credit),
                "additionalChildTaxCredit": _money(additional_child_tax_credit),
                "americanOpportunityCredit": _money(american_opportunity_credit),
                "refundableCredits": _money(refundable_credits),
                "totalPayments": _money(total_payments),
            },
            "refundOrOwed": {
                "refund": _money(refund),
                "amountOwed": _money(amount_owed),
            },
        },
        "summary": {
            "wages": _money(wages),
            "agi": _money(agi),
            "taxableIncome": _money(taxable_income),
            "federalTax": _money(total_tax),
            "totalWithholdings": _money(total_payments),
            "refund": _money(refund),
            "amountOwed": _money(amount_owed),
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "Usage: python3 build_form1040.py <w2_fields.json> <task_config.json> <output_json>",
            file=sys.stderr,
        )
        return 2

    w2_path = Path(argv[1])
    config_path = Path(argv[2])
    output_path = Path(argv[3])

    summary = build_summary(_load_json(w2_path), _load_json(config_path))
    write_summary_artifacts(summary, output_path=output_path)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
