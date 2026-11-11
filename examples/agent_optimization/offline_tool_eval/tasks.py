"""Eval task fixtures: each task pins the exact tool sequence a correct agent makes."""
from __future__ import annotations

TASKS = [
    {
        "id": "find-invoice-total",
        "request": "Read invoice_042.json and recompute its total from subtotal + shipping.",
        "expected_calls": [
            {"tool": "read_file", "args": {"name": "invoice_042.json"}},
            {"tool": "check_total", "args": {"subtotal": 5340, "shipping": 180}},
        ],
    },
    {
        "id": "search-then-read",
        "request": "Find the invoice file, then read it.",
        "expected_calls": [
            {"tool": "search_files", "args": {"q": "invoice"}},
            {"tool": "read_file", "args": {"name": "invoice_042.json"}},
        ],
    },
    {
        "id": "calc-and-verify",
        "request": "Compute 5340+180 with calc, then verify with check_total.",
        "expected_calls": [
            {"tool": "calc", "args": {"expr": "5340+180"}},
            {"tool": "check_total", "args": {"subtotal": 5340, "shipping": 180}},
        ],
    },
    {
        "id": "notes-context",
        "request": "Read the vendor notes, then search for the invoice file.",
        "expected_calls": [
            {"tool": "read_file", "args": {"name": "notes.txt"}},
            {"tool": "search_files", "args": {"q": "invoice"}},
        ],
    },
]
