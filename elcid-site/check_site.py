#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.images = []
        self.scripts = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            if a["id"] in self.ids:
                raise ValueError(f"duplicate id: {a['id']}")
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "img" and a.get("src"):
            self.images.append(a["src"])
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "link" and a.get("rel") == "stylesheet" and a.get("href"):
            self.styles.append(a["href"])


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


html = (ROOT / "index.html").read_text(encoding="utf-8")
css = (ROOT / "styles.css").read_text(encoding="utf-8")
js = (ROOT / "site.js").read_text(encoding="utf-8")
p = Audit()
p.feed(html)

if "AUMARA_Explore" in html or "08_AUMARA_Domes" in html:
    fail("AUMARA primary image assets leaked into EL CID page")
if "noindex,nofollow" not in html:
    fail("review page must remain noindex")
if "cf.bstatic.com" in html or "cf.bstatic.com" in css:
    fail("Booking CDN image hotlink remains")
if "official-logo" not in html or "official-logo" not in css:
    fail("official EL CID logo missing")
if "Wabi-Sabi" in html or "Wabi-Sabi" in js or "Wabi‑Sabi" in html or "Wabi‑Sabi" in js:
    fail("retired restaurant working name remains")
if "reservas@elcidspain.com" in html or "reservas@elcidspain.com" in js:
    fail("broken domain mailbox remains in guest-facing review page")
if "elcidspain@gmail.com" not in html:
    fail("operational email fallback missing")

for required in ("stay", "restaurant", "place", "events", "contact"):
    if required not in p.ids:
        fail(f"missing section #{required}")
for required in ("bookingDrawer", "bookingBackdrop", "bookingNudge", "whatsappBooking"):
    if required not in p.ids:
        fail(f"missing conversion element #{required}")

for path in p.links + p.scripts + p.styles:
    if path.startswith(("http://", "https://", "mailto:", "tel:", "#", "/")):
        continue
    if not (ROOT / path).exists():
        fail(f"missing local target {path}")

for href in p.links:
    if href.startswith("#") and href != "#" and href[1:] not in p.ids:
        fail(f"broken anchor {href}")

if not any("booking.com/hotel/es/el-cid-country-club" in x for x in p.links):
    fail("missing EL CID Booking CTA")
if any("beds24" in x.lower() for x in p.links):
    fail("unverified EL CID Beds24 CTA present")
if "wa.me/" not in js:
    fail("WhatsApp review CTA missing")
if "34622914323" not in js or "34622914323" not in html:
    fail("verified review WhatsApp number is not explicit")
if "data-open-booking" not in html or "booking-drawer" not in css:
    fail("booking drawer trigger or styling missing")

studio_assets = (
    "1sNBC9u1rsO0CiOksJ93RqkzWeZF7tLBF",
    "1G3pNSIQbQR8oLtgpyC9qXkXxAHG7V-AH",
    "1fZjB7E5wNfaurAu0AWlfaHjuEx6BuKVn",
    "1MjonXzcIpvqPn4jNnyPjYUBiPFj8it_o",
)
for asset_id in studio_assets:
    if asset_id not in html:
        fail(f"verified studio asset missing: {asset_id}")

keys = set(re.findall(r'data-i18n="([^"]+)"', html))
for key in keys:
    if not re.search(rf"\b{re.escape(key)}\s*:", js):
        fail(f"translation key absent: {key}")

# Product-routing guardrail: the repository root and preview root are EL CID;
# only /aumara and /aumara/ are allowed to resolve to AUMARA.
root_html = (REPO / "index.html").read_text(encoding="utf-8")
if "./elcid-site/" not in root_html:
    fail("repository root fallback does not point to EL CID")
if "aumara-site" in root_html.lower():
    fail("repository root fallback still points to AUMARA")

vercel = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
routes = {item.get("src"): item for item in vercel.get("routes", [])}
root_route = routes.get("^/$")
if not root_route or root_route.get("dest") != "/elcid-site/index.html":
    fail("preview root / does not resolve to EL CID")
aumara_route = routes.get("^/aumara/?$")
if not aumara_route or aumara_route.get("dest") != "/aumara-site/direct-v2.html":
    fail("/aumara/ does not resolve to the separate AUMARA page")
if not any(item.get("src") == "^/.*$" and item.get("status") == 404 for item in vercel.get("routes", [])):
    fail("preview routing does not block direct access to other repository files")

hosts = sorted({urlparse(x).netloc for x in p.links if x.startswith("http")})
print(
    f"ids={len(p.ids)} links={len(p.links)} images={len(p.images)} "
    f"scripts={len(p.scripts)} styles={len(p.styles)}"
)
print("external_hosts=" + ",".join(hosts))
print("conversion=booking drawer + Booking.com + verified WhatsApp")
print("studio=verified kitchen + living area + bedroom + bathroom")
print("email=operational Gmail fallback; broken domain mailbox excluded")
print("routes=/->EL CID, /aumara/->AUMARA")
print("EL CID v2 static site checks: PASS")
