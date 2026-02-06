#!/usr/bin/env python3
"""
Fetch Intercom conversations by ID, extract message content, and label them with a
taxonomy. Two labelling methods:

  - semantic (default): ML/semantic analysis via a zero-shot classification model
    (Hugging Face). The conversation text is classified into taxonomy categories using
    a multilingual/Spanish model; labels are assigned by model scores (no keyword
    search). Requires: pip install transformers torch.
  - keyword: deterministic rules only (keyword substring match on text + Intercom
    tag mapping). No extra dependencies.

Input: conversation IDs from the tag-samples JSON (output of intercom_tags_report.py
  --output-samples), from a full IDs file (intercom_tags_report.py --output-ids), or from
  a list of IDs. Output: summary table + optional CSV/JSON.

Usage:
  python intercom_conversation_taxonomy.py --from-samples tools/outputs/intercom_tag_samples_*.json --max-convs 20
  python intercom_conversation_taxonomy.py --from-ids-file tools/outputs/intercom_conversation_ids_20260127_20260128.json --output-csv out.csv
  python intercom_conversation_taxonomy.py --ids 215472737079652,215472795323288
  python intercom_conversation_taxonomy.py --from-ids-file path/to/ids.json --output-csv out.csv --output-json out.json
"""

import os
import sys
import re
import argparse
import json
import csv
import time
from collections import defaultdict
from html import unescape

# Same path setup as intercom_tags_report.py
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from dotenv import load_dotenv
_repo_root = os.path.abspath(os.path.join(_script_dir, "..", "..", ".."))
_dotenv_path = os.path.join(_repo_root, ".env")
if os.path.isfile(_dotenv_path):
    load_dotenv(_dotenv_path)
else:
    load_dotenv()

try:
    import requests
except ImportError:
    requests = None

# Token from env (same as tags report)
INTERCOM_ACCESS_TOKEN = os.getenv("INTERCOM_ACCESS_TOKEN")
REQUEST_TIMEOUT = 60

# Taxonomy category names (used by both keyword and semantic methods).
# Keyword method: category -> keywords for substring match (lowercased).
# Semantic method: these names are used as candidate_labels for zero-shot classification.
TAXONOMY_KEYWORDS = {
    "Facturación": [
        "factura", "facturación", "comprobante", "descarga", "afip", "fiscal",
        "nota de crédito", "nc ", "talonario", "cae", "caí",
    ],
    "Bug/Error": [
        "error", "bug", "no funciona", "falla", "excepción", "crash", "no puedo",
        "no me deja", "problema con", "no carga", "tengo un error",
    ],
    "Ventas/Comercial": [
        "ventas", "plan", "precio", "cotización", "demo", "contrato", "suscrib",
        "consulta para ventas", "quiero comprar", "cambio de plan",
    ],
    "Follow-up/Resolución": [
        "resolviste", "resolución", "pregunta", "seguimiento", "cerrado", "resuelto",
        "workflow", "¿resolviste", "resolviste tu pregunta",
    ],
    "Soporte técnico / Acceso": [
        "acceso", "usuario", "contraseña", "login", "integración", "api",
        "conecta tu banco", "sincroniz", "importación", "export",
    ],
    "Cobranza/Billing": [
        "cobro", "pago", "tarjeta", "baja", "cancelación", "factura colppy",
        "medio de pago", "devolución", "downsell", "bonificacion",
    ],
    "eSueldos/Nóminas": [
        "sueldos", "esueldos", "legajo", "liquidación", "nómina", "nomina",
        "concepto", "escalas",
    ],
    "Onboarding/Capacitación": [
        "onboarding", "capacitación", "tutorial", "cómo", "como usar",
        "primera vez", "configuración inicial",
    ],
}

# Semantic labelling: min score to accept a label (zero-shot pipeline).
SEMANTIC_SCORE_THRESHOLD = 0.2
# Max characters to send to the model (avoid token limit).
SEMANTIC_MAX_TEXT_LEN = 2000
# Zero-shot model: Spanish-optimized (Recognai) or multilingual fallback.
SEMANTIC_MODEL = "Recognai/zeroshot_selectra_small"
SEMANTIC_HYPOTHESIS_TEMPLATE = "Este ejemplo es {}."


def _strip_html(html_str):
    """Remove HTML tags and decode entities; leave plain text."""
    if not html_str or not isinstance(html_str, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = re.sub(r"\s+", " ", text).strip()
    return unescape(text)


def _collect_ids_from_samples(samples_path, max_convs=None, skip=0):
    """
    Load tag -> [ids] JSON and return deduplicated list of conversation IDs,
    preserving order (first seen first). If skip > 0, skips the first `skip`
    IDs and returns up to `max_convs` after that (so collects skip + max_convs
    from the start, then returns ids[skip : skip + max_convs]).
    """
    with open(samples_path, encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    ids = []
    need = (skip + max_convs) if (max_convs is not None and skip > 0) else max_convs
    for tag_name, id_list in data.items():
        if not isinstance(id_list, list):
            continue
        for cid in id_list:
            cid = str(cid).strip()
            if cid and cid not in seen:
                seen.add(cid)
                ids.append(cid)
                if need and len(ids) >= need:
                    break
        if need and len(ids) >= need:
            break
    if skip > 0 and max_convs is not None:
        ids = ids[skip : skip + max_convs]
    elif max_convs is not None and len(ids) > max_convs:
        ids = ids[:max_convs]
    return ids


def _load_ids_from_file(ids_path):
    """
    Load conversation IDs from a file. Accepts:
    - JSON array of strings: ["id1", "id2", ...]
    - JSON object with "ids" key: {"ids": ["id1", "id2", ...]}
    - Text file with one ID per line.
    Returns list of non-empty string IDs.
    """
    with open(ids_path, encoding="utf-8") as f:
        raw = f.read().strip()
    ids = []
    if raw.startswith("["):
        data = json.loads(raw)
        if isinstance(data, list):
            ids = [str(x).strip() for x in data if x]
    elif raw.startswith("{"):
        data = json.loads(raw)
        if isinstance(data, dict) and "ids" in data:
            ids = [str(x).strip() for x in data["ids"] if x]
    else:
        for line in raw.splitlines():
            cid = line.strip()
            if cid and not cid.startswith("#"):
                ids.append(cid)
    return ids


def _fetch_conversation(conv_id, token, display_plaintext=True):
    """
    GET a single conversation by ID. Returns raw API dict or None on failure.
    """
    if not requests or not token:
        return None
    url = f"https://api.intercom.io/conversations/{conv_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {"display_as": "plaintext"} if display_plaintext else {}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Fetch failed for {conv_id}: {e}", file=sys.stderr)
        return None


def _tags_from_conversation(conv):
    """Extract list of tag names from conversation dict."""
    tags = []
    t = conv.get("tags")
    if isinstance(t, dict):
        tag_list = t.get("tags") or []
    elif isinstance(t, list):
        tag_list = t
    else:
        tag_list = []
    for tag in tag_list:
        if isinstance(tag, dict) and tag.get("name"):
            tags.append(str(tag["name"]).strip())
        elif isinstance(tag, str):
            tags.append(tag.strip())
    return tags


def _parts_from_conversation(conv):
    """
    Extract conversation parts: list of dicts with body (plain text), author_type, created_at.
    """
    out = []
    cp = conv.get("conversation_parts")
    if not isinstance(cp, dict):
        return out
    parts = cp.get("conversation_parts") or cp.get("data") or []
    if not isinstance(parts, list):
        return out
    for p in parts:
        if not isinstance(p, dict):
            continue
        body = p.get("body") or ""
        if body and not p.get("display_as") == "plaintext":
            body = _strip_html(body)
        author = p.get("author") or {}
        author_type = author.get("type", "unknown") if isinstance(author, dict) else "unknown"
        created = p.get("created_at")
        out.append({
            "body": (body or "").strip(),
            "author_type": author_type,
            "created_at": created,
        })
    return out


def _source_first_message(conv):
    """First message body from conversation source (initial contact)."""
    src = conv.get("source") or {}
    if isinstance(src, dict):
        body = src.get("body") or ""
        if body and src.get("display_as") != "plaintext":
            body = _strip_html(body)
        return (body or "").strip()
    return ""


def _get_semantic_classifier():
    """Lazy-load zero-shot classification pipeline (Spanish-optimized)."""
    try:
        from transformers import pipeline
    except ImportError as e:
        raise ImportError(
            "Semantic labelling requires transformers and torch. "
            "Install with: pip install transformers torch"
        ) from e
    return pipeline(
        "zero-shot-classification",
        model=SEMANTIC_MODEL,
        hypothesis_template=SEMANTIC_HYPOTHESIS_TEMPLATE,
    )


# Lazy-loaded classifier (set on first use of semantic method).
_semantic_classifier = None


def _assign_taxonomy_semantic(conv, parts, first_message):
    """
    Assign taxonomy labels using ML/semantic analysis (zero-shot classification).

    Conversation text (first message + part bodies) is truncated and passed to a
    zero-shot NLI model. Categories are the taxonomy category names; the model
    returns scores per category. Labels with score >= SEMANTIC_SCORE_THRESHOLD
    are returned (or at least the top-scoring label if none pass threshold).

    Returns sorted list of category names (labels).
    """
    global _semantic_classifier
    if _semantic_classifier is None:
        _semantic_classifier = _get_semantic_classifier()
    text_parts = [first_message] + [p.get("body") or "" for p in parts]
    combined = " ".join(text_parts).strip()
    if not combined:
        return []
    if len(combined) > SEMANTIC_MAX_TEXT_LEN:
        combined = combined[:SEMANTIC_MAX_TEXT_LEN] + "…"
    candidate_labels = list(TAXONOMY_KEYWORDS.keys())
    try:
        out = _semantic_classifier(
            combined,
            candidate_labels=candidate_labels,
            multi_label=True,
        )
    except Exception:
        out = _semantic_classifier(
            combined,
            candidate_labels=candidate_labels,
            multi_label=False,
        )
    label_list = out.get("labels") or []
    scores = out.get("scores") or []
    if not isinstance(scores, (list, tuple)):
        scores = [scores] if scores is not None else []
    if not isinstance(label_list, (list, tuple)):
        label_list = [label_list] if label_list else []
    labels = [
        lab for lab, s in zip(label_list, scores)
        if s >= SEMANTIC_SCORE_THRESHOLD
    ]
    if not labels and label_list:
        labels = [label_list[0]]
    return sorted(labels)


def _assign_taxonomy_keyword(conv, parts, first_message):
    """
    Assign taxonomy labels using deterministic rules only (keyword + tag mapping).

    1. Tag mapping: Intercom tags on the conversation are mapped to categories via
       tag_to_category and prefix rules (CS-, FC-, Mod-, factura, etc.).
    2. Keyword match: concatenated text (first_message + all part bodies) is lowercased
       and checked for substrings in TAXONOMY_KEYWORDS; any match adds that category.

    Returns sorted list of category names (labels).
    """
    labels = set()
    tags = _tags_from_conversation(conv)
    text_parts = [first_message] + [p.get("body") or "" for p in parts]
    combined = " ".join(text_parts).lower()

    tag_to_category = {
        "workflow-d5": "Follow-up/Resolución",
        "¿resolviste tu pregunta?": "Follow-up/Resolución",
        "w5-p1-no-resuelto": "Follow-up/Resolución",
        "w5-ya-resuelto": "Follow-up/Resolución",
        "consulta para ventas": "Ventas/Comercial",
        "chat-bot": "Soporte técnico / Acceso",
        "colppy plus soporte": "Soporte técnico / Acceso",
        "bug": "Bug/Error",
        "sugerencia de mejora": "Bug/Error",
    }
    for tag in tags:
        t_lower = tag.lower()
        if t_lower in tag_to_category:
            labels.add(tag_to_category[t_lower])
        if t_lower.startswith("cs ") or t_lower.startswith("fc "):
            labels.add("Cobranza/Billing")
        if "mod " in t_lower or "factura" in t_lower or "comprobante" in t_lower:
            labels.add("Facturación")

    for category, keywords in TAXONOMY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                labels.add(category)
                break

    return sorted(labels)


def run_taxonomy(
    conversation_ids,
    token,
    max_convs=20,
    output_csv_path=None,
    output_json_path=None,
    verbose=True,
    labelling_method="semantic",
    excerpt_len=120,
):
    """
    Fetch each conversation by ID, extract parts and tags, assign taxonomy labels,
    and return list of summary dicts. Optionally write CSV and/or JSON.

    labelling_method: "semantic" (default) = ML zero-shot classification;
      "keyword" = deterministic keyword + tag mapping.

    Returns: list of {
        "conversation_id", "tags", "taxonomy_labels", "first_snippet", "part_count",
        "n_user", "n_admin", "n_bot", "author_breakdown"
    }
    """
    ids = conversation_ids[:max_convs] if max_convs else conversation_ids
    assign_fn = _assign_taxonomy_semantic if labelling_method == "semantic" else _assign_taxonomy_keyword
    if labelling_method == "semantic":
        if verbose:
            print("  Labelling method: semantic (zero-shot ML)", file=sys.stderr)
        global _semantic_classifier
        _semantic_classifier = _get_semantic_classifier()
    elif verbose and labelling_method == "keyword":
        print("  Labelling method: keyword + tag mapping", file=sys.stderr)
    results = []
    for i, cid in enumerate(ids):
        if i > 0:
            time.sleep(0.3)
        if verbose:
            print(f"  Fetching {i + 1}/{len(ids)}: {cid}...", file=sys.stderr)
        conv = _fetch_conversation(cid, token)
        if not conv:
            continue
        tags = _tags_from_conversation(conv)
        parts = _parts_from_conversation(conv)
        first_message = _source_first_message(conv)
        taxonomy = assign_fn(conv, parts, first_message)
        # Author breakdown
        n_user = n_admin = n_bot = 0
        for p in parts:
            t = p.get("author_type", "")
            if t in ("user", "lead"):
                n_user += 1
            elif t == "admin":
                n_admin += 1
            elif t == "bot":
                n_bot += 1
        full_text = first_message + " " + " ".join(p.get("body") or "" for p in parts)
        full_stripped = full_text.strip()
        snippet = (full_stripped[:120] + "…") if len(full_stripped) > 120 else full_stripped
        excerpt = (full_stripped[:excerpt_len] + "…") if len(full_stripped) > excerpt_len else full_stripped
        results.append({
            "conversation_id": cid,
            "tags": tags,
            "taxonomy_labels": taxonomy,
            "first_snippet": snippet,
            "excerpt": excerpt,
            "part_count": len(parts) + (1 if first_message else 0),
            "n_user": n_user + (1 if first_message else 0),
            "n_admin": n_admin,
            "n_bot": n_bot,
            "author_breakdown": f"user={n_user + (1 if first_message else 0)} admin={n_admin} bot={n_bot}",
        })
    if output_csv_path:
        _write_csv(results, output_csv_path)
    if output_json_path:
        _write_json(results, output_json_path)
    return results


def _write_csv(results, path):
    """
    Write CSV for auditing: conversation content (excerpt) next to ML taxonomy
    and Intercom tags. Use quoted fields so excerpt text with ; or newlines is safe.
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "conversation_id",
            "intercom_tags",
            "taxonomy_ml",
            "conversation_excerpt",
            "part_count",
            "n_user",
            "n_admin",
            "n_bot",
            "corrected_label_notes",
        ])
        for r in results:
            w.writerow([
                r["conversation_id"],
                " | ".join(r["tags"][:15]),
                " | ".join(r["taxonomy_labels"]),
                (r.get("excerpt") or r.get("first_snippet") or ""),
                r["part_count"],
                r["n_user"],
                r["n_admin"],
                r["n_bot"],
                "",  # empty for you to fill: what the label should be or notes
            ])


def _write_json(results, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def _print_summary(results, show_excerpt_len=0):
    """
    show_excerpt_len: if > 0, print 'Conversation excerpt (what the ML saw):' with
    that many chars (uses stored excerpt if present and long enough).
    """
    print("\nConversation taxonomy summary")
    print("=" * 80)
    for r in results:
        print(f"\nConversation ID: {r['conversation_id']}")
        print(f"  Tags: {', '.join(r['tags'][:8])}{' …' if len(r['tags']) > 8 else ''}")
        print(f"  Taxonomy (ML): {', '.join(r['taxonomy_labels']) or '(none)'}")
        print(f"  Parts: {r['part_count']}  |  {r['author_breakdown']}")
        if show_excerpt_len and r.get("excerpt"):
            print(f"  Conversation excerpt (what the ML saw):")
            print(f"    {r['excerpt']}")
        else:
            print(f"  Snippet: {(r['first_snippet'] or '')[:100]}…")
    # Aggregate taxonomy counts
    agg = defaultdict(int)
    for r in results:
        for lab in r["taxonomy_labels"]:
            agg[lab] += 1
    print("\n" + "=" * 80)
    print("Taxonomy label counts (across sampled conversations):")
    for lab, count in sorted(agg.items(), key=lambda x: -x[1]):
        print(f"  {lab}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Intercom conversations by ID and label with taxonomy (from samples or ID list)."
    )
    parser.add_argument(
        "--from-samples",
        metavar="PATH",
        help="Path to intercom_tag_samples_*.json (tag -> conversation IDs)",
    )
    parser.add_argument(
        "--ids",
        metavar="ID1,ID2,...",
        help="Comma-separated conversation IDs (alternative to --from-samples)",
    )
    parser.add_argument(
        "--from-ids-file",
        metavar="PATH",
        help="Path to JSON/list file with all conversation IDs (e.g. intercom_conversation_ids_*.json from tags report --output-ids). Process all unless --max-convs set.",
    )
    parser.add_argument(
        "--max-convs",
        type=int,
        default=None,
        metavar="N",
        help="Max conversations to fetch (default: all when --from-ids-file, 20 when --from-samples)",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        metavar="N",
        help="When using --from-samples, skip the first N conversation IDs and process the next --max-convs (e.g. --skip 5 --max-convs 5 for IDs 6–10).",
    )
    parser.add_argument(
        "--output-csv",
        metavar="PATH",
        help="Write summary to CSV (delimiter ;)",
    )
    parser.add_argument(
        "--output-json",
        metavar="PATH",
        help="Write full summary to JSON",
    )
    parser.add_argument(
        "--labelling-method",
        choices=("semantic", "keyword"),
        default="semantic",
        help="How to assign taxonomy labels: semantic = ML zero-shot classification (default); keyword = deterministic keyword + tag mapping.",
    )
    parser.add_argument(
        "--excerpt-len",
        type=int,
        default=500,
        metavar="N",
        help="Length of conversation excerpt to store and show (default 500). Use 800–1000 to see more context for auditing.",
    )
    args = parser.parse_args()

    if not INTERCOM_ACCESS_TOKEN:
        print("INTERCOM_ACCESS_TOKEN not set. Set it in .env or environment.", file=sys.stderr)
        sys.exit(1)
    if not requests:
        print("requests library required. pip install requests", file=sys.stderr)
        sys.exit(1)

    ids = []
    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    elif args.from_ids_file:
        ids = _load_ids_from_file(args.from_ids_file)
        if args.max_convs is None:
            args.max_convs = len(ids)
    elif args.from_samples:
        max_convs_default = 20
        skip = getattr(args, "skip", 0) or 0
        ids = _collect_ids_from_samples(
            args.from_samples,
            max_convs=args.max_convs or max_convs_default,
            skip=skip,
        )
        if args.max_convs is None:
            args.max_convs = max_convs_default
    else:
        print("Provide --from-samples PATH, --from-ids-file PATH, or --ids ID1,ID2,...", file=sys.stderr)
        sys.exit(1)

    if not ids:
        print("No conversation IDs to fetch.", file=sys.stderr)
        sys.exit(0)

    # When using --from-ids-file or --ids, apply --skip here; when using --from-samples,
    # skip was already applied inside _collect_ids_from_samples.
    skip = getattr(args, "skip", 0) or 0
    max_convs = args.max_convs
    if skip > 0 and not args.from_samples:
        ids = ids[skip : (skip + max_convs) if max_convs else None]
    elif max_convs is not None and not args.from_samples:
        ids = ids[:max_convs]
    print(f"Processing {len(ids)} conversation(s)...", file=sys.stderr)
    results = run_taxonomy(
        ids,
        INTERCOM_ACCESS_TOKEN,
        max_convs=None,
        output_csv_path=args.output_csv,
        output_json_path=args.output_json,
        verbose=True,
        labelling_method=args.labelling_method,
        excerpt_len=args.excerpt_len,
    )
    _print_summary(results, show_excerpt_len=args.excerpt_len)
    if args.output_csv:
        print(f"\nCSV written to {args.output_csv}", file=sys.stderr)
    if args.output_json:
        print(f"JSON written to {args.output_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
