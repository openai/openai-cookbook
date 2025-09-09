#!/usr/bin/env python3
import sys
import os
import yaml
from datetime import datetime, date as date_cls, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

REPO_URL = "https://github.com/openai/openai-cookbook"
RAW_SITE_URL = "https://cookbook.openai.com/"  # Public site homepage

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REGISTRY_PATH = os.path.join(ROOT, "registry.yaml")
AUTHORS_PATH = os.path.join(ROOT, "authors.yaml")
FEED_PATH = os.path.join(ROOT, "feed.xml")


def read_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_date(value):
    """Return a timezone-aware datetime (UTC) for a variety of inputs."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, date_cls):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    # Fallback to now if parsing failed
    return datetime.now(timezone.utc)


def to_rfc2822(value):
    return format_datetime(normalize_date(value))


def author_display(authors_cfg, author_key):
    rec = authors_cfg.get(author_key)
    if isinstance(rec, dict) and rec.get("name"):
        return rec["name"]
    return author_key


def item_link_for_path(path):
    # We don't control the external site routing here. Link to the GitHub source for reliability.
    return f"{REPO_URL}/blob/main/{path}"


def main():
    registry = read_yaml(REGISTRY_PATH)
    authors_cfg = {}
    try:
        authors_cfg = read_yaml(AUTHORS_PATH) or {}
    except FileNotFoundError:
        authors_cfg = {}

    # Normalize and sort newest first by date
    items = []
    for entry in registry:
        title = entry.get("title") or "Untitled"
        path = entry.get("path") or ""
        date_value = entry.get("date") or "1970-01-01"
        tags = entry.get("tags") or []
        authors = entry.get("authors") or []
        link = item_link_for_path(path)
        # Minimal description: tags + path reference
        desc_bits = []
        if tags:
            desc_bits.append("Tags: " + ", ".join(tags))
        if path:
            desc_bits.append(f"Source: {path}")
        description = " | ".join(desc_bits) if desc_bits else ""
        items.append({
            "title": title,
            "link": link,
            "date": normalize_date(date_value),
            "pubDate": to_rfc2822(date_value),
            "authors": [author_display(authors_cfg, a) for a in authors],
            "description": description,
        })

    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:50]  # keep feed reasonably small

    now_rfc2822 = format_datetime(datetime.now(timezone.utc))

    feed_title = "OpenAI Cookbook – New Content"
    feed_link = RAW_SITE_URL
    feed_desc = "New and updated guides, examples, and articles from the OpenAI Cookbook repository."

    # Build RSS 2.0 XML
    out = []
    out.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    out.append("<rss version=\"2.0\">")
    out.append("  <channel>")
    out.append(f"    <title>{escape(feed_title)}</title>")
    out.append(f"    <link>{escape(feed_link)}</link>")
    out.append(f"    <description>{escape(feed_desc)}</description>")
    out.append(f"    <lastBuildDate>{now_rfc2822}</lastBuildDate>")
    out.append("    <generator>openai-cookbook rss generator</generator>")

    for it in items:
        out.append("    <item>")
        out.append(f"      <title>{escape(it['title'])}</title>")
        out.append(f"      <link>{escape(it['link'])}</link>")
        out.append(f"      <guid isPermaLink=\"true\">{escape(it['link'])}</guid>")
        out.append(f"      <pubDate>{it['pubDate']}</pubDate>")
        if it["description"]:
            out.append(f"      <description>{escape(it['description'])}</description>")
        for a in it["authors"]:
            out.append(f"      <author>{escape(a)}</author>")
        out.append("    </item>")

    out.append("  </channel>")
    out.append("</rss>")

    xml = "\n".join(out) + "\n"
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"Wrote {FEED_PATH}")


if __name__ == "__main__":
    try:
        import yaml  # noqa: F401
    except Exception:
        print("PyYAML not installed. Please install pyyaml.", file=sys.stderr)
        sys.exit(2)
    main()
