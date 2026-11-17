"""Render saved evidence and actual API results without external services."""

import html
import json

from review import image_part


def write_report(records, path):
    escape = html.escape
    cards = []
    for row in records:
        images = "".join(
            f'<figure><img src="{image_part(row[key])["image_url"]}" '
            f'alt="{escape(label)}"><figcaption>{label}</figcaption></figure>'
            for key, label in [("reference_image", "Approved reference"),
                               ("listing_image", "Listing photo"),
                               ("campaign_image", "Campaign asset")])
        answers = "".join(
            f'<tr><td>{escape(a["name"])}</td><td>{escape(a["choice"])}</td>'
            f'<td>{a["confidence"] if a["confidence"] is not None else "Unavailable"}</td></tr>'
            for a in row["answers"])
        request = escape(json.dumps(row["request"], indent=2))
        response = escape(json.dumps(row["response"], indent=2))
        cards.append(f'<article><h2>{escape(row["title"])}</h2><div class="images">'
                     f'{images}</div><table><tr><th>Check</th><th>Assessment</th>'
                     f'<th>Model confidence</th></tr>{answers}</table>'
                     f'<p>Suggested next step: <strong>{escape(row["next_step"])}</strong>'
                     f' · {row["latency_ms"]} ms</p><details><summary>Actual request '
                     f'(image bytes omitted)</summary><pre>{request}</pre></details>'
                     f'<details><summary>Actual API response</summary><pre>{response}</pre>'
                     f'</details></article>')
    path.write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Product content review</title><style>
body{font:16px/1.5 system-ui;margin:0;background:#f5f6f4;color:#172a29}
main{max-width:1150px;margin:auto;padding:30px}article{background:white;padding:24px;
border:1px solid #dce2dd;border-radius:12px;margin:24px 0}.images{display:grid;
grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}figure{margin:0}img{width:100%;
height:250px;object-fit:contain;background:#f6f6f3}figcaption{color:#52635d}
table{border-collapse:collapse;width:100%;margin-top:20px}td,th{text-align:left;
padding:8px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;
font-size:12px;background:#f3f5f3;padding:16px}details{margin-top:12px}summary{cursor:pointer}
@media(max-width:650px){.images{grid-template-columns:1fr}main{padding:12px}}
</style><main><h1>Review product content before publication</h1>
<p>Fictional products and generated images. Model assessments support an editor;
no listing is published automatically. Confidence is not proof of correctness.</p>
''' + "".join(cards) + "</main></html>", encoding="utf-8")
