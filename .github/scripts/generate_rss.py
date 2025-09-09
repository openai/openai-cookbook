#!/usr/bin/env python3
"""
Generate an RSS 2.0 feed (rss.xml) from registry.yaml and authors.yaml.

Feed is written to repo root as rss.xml. Items link to the source files on
GitHub; channel link points to cookbook.openai.com. Archived items are skipped.
"""

from __future__ import annotations

import os
import sys
import yaml
import hashlib
from datetime import datetime, timezone
from email.utils import format_datetime
import xml.etree.ElementTree as ET


REPO_HOMEPAGE = "https://github.com/openai/openai-cookbook"
SITE_HOMEPAGE = "https://cookbook.openai.com"
FEED_SELF_URL = (
    "https://raw.githubusercontent.com/openai/openai-cookbook/main/rss.xml"
)


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_date(date_str: str) -> datetime:
    # registry dates are in YYYY-MM-DD
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def build_feed(entries: list[dict], authors: dict) -> ET.ElementTree:
    # namespaces
    atom_ns = "http://www.w3.org/2005/Atom"
    dc_ns = "http://purl.org/dc/elements/1.1/"
    ET.register_namespace("atom", atom_ns)
    ET.register_namespace("dc", dc_ns)

    rss = ET.Element(
        "rss",
        attrib={
            "version": "2.0",
            "xmlns:atom": atom_ns,
            "xmlns:dc": dc_ns,
        },
    )
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "OpenAI Cookbook"
    ET.SubElement(channel, "link").text = SITE_HOMEPAGE
    ET.SubElement(channel, "description").text = (
        "New recipes, guides, and examples from the OpenAI Cookbook."
    )
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "ttl").text = "180"

    # self link
    ET.SubElement(
        channel,
        ET.QName(atom_ns, "link"),
        attrib={
            "href": FEED_SELF_URL,
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    # sort entries by date desc; skip archived
    prepared = []
    for e in entries:
        if e.get("archived", False):
            continue
        try:
            dt = parse_date(str(e["date"]))
        except Exception:
            # Skip invalid date entries
            continue
        prepared.append((dt, e))
    prepared.sort(key=lambda x: x[0], reverse=True)

    if prepared:
        last_dt = prepared[0][0]
    else:
        last_dt = datetime.now(timezone.utc)
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(last_dt)

    # limit items
    max_items = 100
    for dt, e in prepared[:max_items]:
        title = str(e.get("title", "Untitled"))
        path = str(e.get("path", "")).lstrip("./")
        tags = e.get("tags", []) or []
        author_ids = e.get("authors", []) or []

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title

        # Use GitHub blob URL for stable, accessible links
        gh_link = f"{REPO_HOMEPAGE}/blob/main/{path}"
        ET.SubElement(item, "link").text = gh_link

        # GUID as permaLink
        guid = ET.SubElement(item, "guid", attrib={"isPermaLink": "true"})
        guid.text = gh_link

        # Publication date
        ET.SubElement(item, "pubDate").text = format_datetime(dt)

        # Description: authors and tags
        author_names = [authors.get(aid, {}).get("name", aid) for aid in author_ids]
        desc_parts = []
        if tags:
            desc_parts.append("Tags: " + ", ".join(map(str, tags)))
        if author_names:
            desc_parts.append("Authors: " + ", ".join(author_names))
        description = " | ".join(desc_parts) if desc_parts else "New cookbook entry"
        ET.SubElement(item, "description").text = description

        # Categories from tags
        for t in tags:
            ET.SubElement(item, "category").text = str(t)

        # dc:creator for each author
        for name in author_names:
            ET.SubElement(item, ET.QName(dc_ns, "creator")).text = name

    return ET.ElementTree(rss)


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    registry_path = os.path.join(repo_root, "registry.yaml")
    authors_path = os.path.join(repo_root, "authors.yaml")
    out_path = os.path.join(repo_root, "rss.xml")

    if not os.path.exists(registry_path):
        print("registry.yaml not found", file=sys.stderr)
        sys.exit(1)

    registry = load_yaml(registry_path) or []
    authors = load_yaml(authors_path) or {}

    feed = build_feed(registry, authors)

    # Write with XML declaration and UTF-8 encoding
    feed.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote RSS feed with {len(registry)} entries (including skipped) -> {out_path}")


if __name__ == "__main__":
    main()

