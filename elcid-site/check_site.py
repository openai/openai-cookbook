#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.meta: dict[str, str] = {}
        self.title_seen = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.stylesheets.append(values["href"] or "")
        if tag == "meta" and values.get("name"):
            self.meta[values["name"] or ""] = values.get("content") or ""
        if tag == "title":
            self.title_seen = True


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    parser = SiteParser()
    parser.feed(html)
    errors: list[str] = []

    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate ids: {duplicates}")

    known_ids = set(parser.ids)
    for href in parser.hrefs:
        if href.startswith("#") and href != "#" and href[1:] not in known_ids:
            errors.append(f"broken internal anchor: {href}")

    for required in ("description", "robots"):
        if not parser.meta.get(required):
            errors.append(f"missing meta {required}")

    if not parser.title_seen:
        errors.append("missing title")
    if "http-equiv=\"refresh\"" in html.lower() or "window.location.replace('/aumara/')" in html:
        errors.append("root still redirects to AUMARA")
    if "AUMARA_Explore_" in html or "AUMARA_Domes_" in html:
        errors.append("AUMARA image asset used in EL CID page")
    if "booking.com/hotel/es/el-cid-country-club" not in html:
        errors.append("hotel availability CTA missing")

    for filename in ("styles.css", "site.js", "legal.html", "privacy.html", "cookies.html"):
        if not (ROOT / filename).exists():
            errors.append(f"missing required file: {filename}")

    if "TODO" in html or "Lorem ipsum" in html:
        errors.append("placeholder content remains")

    print(f"ids={len(parser.ids)} links={len(parser.hrefs)}")
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("EL CID static site checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
