"""Shared request previews and HTML reports for Python and notebook use."""

import base64
import html
import json
from pathlib import Path

from return_evidence import API_URL, image_path, parse_answers


def display_request(payload):
    """Omit only image bytes from the printed request; send the original payload."""
    # Redact a copy so the actual request still contains the image bytes.
    preview = json.loads(json.dumps(payload))
    for message in preview["input"]:
        if isinstance(message["content"], list):
            for part in message["content"]:
                if part["type"] == "input_image":
                    part["image_url"] = "[inline image bytes omitted from display]"
    return preview


def validate_report_path(destination, directory):
    """Keep report output from overwriting the bundled reference data."""
    destination = Path(destination)
    if destination.suffix.lower() != ".html":
        raise ValueError("Report output must end in .html")
    directory = Path(directory)
    protected = {directory / "return_cases.json", directory / "return_expectations.json",
                 directory / "images" / "provenance.json",
                 directory / "images" / "architecture-provenance.json"}
    if destination.with_suffix(".json").resolve() in {p.resolve() for p in protected}:
        raise ValueError("Report output would overwrite bundled JSON data")


def total_tokens(rows):
    """Sum valid reported token counts without discarding unusable responses."""
    tokens = 0
    for row in rows:
        response = row["response"]
        usage = response.get("usage") if isinstance(response, dict) else None
        count = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(count) is int and count >= 0:
            tokens += count
    return tokens


def write_report(rows, destination, directory):
    validate_report_path(destination, directory)
    # Escape customer and model content before inserting it into the HTML report.
    escape = html.escape

    def pretty(value):
        return escape(json.dumps(value, indent=2))

    sections = []
    for row in rows:
        case = row["case"]
        pictures = []
        for turn in case["conversation"]:
            if turn.get("image"):
                # Embed photos so the report can open without an image server.
                image = image_path(directory, turn["image"])
                data = base64.b64encode(image.read_bytes()).decode("ascii")
                pictures.append(
                    f'<figure><img src="data:image/png;base64,{data}" '
                    f'alt="{escape(turn["image"])}">'
                    f'<figcaption>{escape(turn["image"])}</figcaption></figure>'
                )
        if "request" in row:
            request_section = (
                f'<h3>API request</h3><p>POST {escape(API_URL)}</p>'
                '<p>Image bytes omitted; credentials are not included.</p>'
                f'<pre>{pretty(row["request"])}</pre>'
            )
        else:
            request_section = '<p>Request preview was not recorded in this older run.</p>'
        sections.append(
            f'<article><h2>{escape(case["id"])}: {escape(case["title"])}</h2>'
            f'<div class="photos">{"".join(pictures)}</div>'
            f'<h3>Customer conversation and order</h3><pre>{pretty(case)}</pre>'
            f'{request_section}'
            f'<h3>Actual Decisions API response</h3><pre>{pretty(row["response"])}</pre>'
            f'<h3>Application handoff record</h3><pre>{pretty(row["handoff"])}</pre>'
            f'<p>Expected: {escape(row["grade"]["expected"])} | '
            f'Actual: {escape(row["grade"]["actual"])} | '
            f'{"PASS" if row["grade"]["passed"] else "FAIL"} | {row["latency_ms"]} ms</p></article>'
        )
    # Summarize the same saved responses; grading makes no extra model calls.
    passed = sum(row["grade"]["passed"] for row in rows)
    tokens = total_tokens(rows)
    unusable = sum(parse_answers(row["response"]) is None for row in rows)
    missed = sum(row["grade"]["missed_escalation"] for row in rows)
    unnecessary = sum(row["grade"]["unnecessary_escalation"] for row in rows)
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Product return evidence results</title><style>'
        'body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:0 20px;color:#17252e}'
        'article{border-top:1px solid #ccd5da;padding:20px 0}.photos{display:flex;flex-wrap:wrap;gap:16px}'
        'figure{margin:0}img{width:280px;max-width:100%;border-radius:8px}'
        'pre{background:#f1f5f7;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere}'
        '</style><h1>Product return evidence results</h1>'
        '<p>Real Decisions responses. Fictional cases and synthetic illustrative photos. '
        'Handoff records are local recommendations, not submitted tickets or approvals.</p>'
        f'<p>Completed {len(rows)}/10 requests. '
        f'{passed}/{len(rows)} expected outcomes matched. Missed escalations: {missed}. '
        f'Unnecessary escalations: {unnecessary}. Total tokens: {tokens}.</p>'
        f'<p>Unusable API answers sent for specialist review: {unusable}.</p>'
        '<p>This small demonstration does not establish production accuracy. '
        'Cases 9 and 10 are two snapshots of the same conversation.</p>'
        + "".join(sections) + '</html>'
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    destination.with_suffix(".json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
