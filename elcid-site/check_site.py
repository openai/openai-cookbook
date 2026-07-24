#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import re,sys
ROOT=Path(__file__).resolve().parent
class Audit(HTMLParser):
    def __init__(self):super().__init__();self.ids=set();self.links=[];self.images=[];self.scripts=[];self.styles=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if "id" in a:
            if a["id"] in self.ids:raise ValueError(f"duplicate id: {a['id']}")
            self.ids.add(a["id"])
        if tag=="a" and a.get("href"):self.links.append(a["href"])
        if tag=="img" and a.get("src"):self.images.append(a["src"])
        if tag=="script" and a.get("src"):self.scripts.append(a["src"])
        if tag=="link" and a.get("rel")=="stylesheet" and a.get("href"):self.styles.append(a["href"])
def fail(msg):print("FAIL:",msg);sys.exit(1)
html=(ROOT/"index.html").read_text(encoding="utf-8");css=(ROOT/"styles.css").read_text(encoding="utf-8");p=Audit();p.feed(html)
if "AUMARA_Explore" in html or "08_AUMARA_Domes" in html:fail("AUMARA image assets leaked into EL CID page")
if "noindex,nofollow" not in html:fail("review page must remain noindex")
if "cf.bstatic.com" in html or "cf.bstatic.com" in css:fail("Booking CDN image hotlink remains")
if "official-logo" not in html or "official-logo" not in css:fail("official EL CID logo missing")
for required in ("stay","food","place","events","contact"):
    if required not in p.ids:fail(f"missing section #{required}")
for path in p.links+p.scripts+p.styles:
    if path.startswith(("http://","https://","mailto:","tel:","#","/")):continue
    if not (ROOT/path).exists():fail(f"missing local target {path}")
for href in p.links:
    if href.startswith("#") and href[1:] not in p.ids:fail(f"broken anchor {href}")
if not any("booking.com/hotel/es/el-cid-country-club" in x for x in p.links):fail("missing EL CID Booking CTA")
if any("beds24" in x.lower() for x in p.links):fail("unverified Beds24 CTA present")
js=(ROOT/"site.js").read_text(encoding="utf-8")
keys=set(re.findall(r'data-i18n="([^"]+)"',html))
for key in keys:
    if not re.search(rf'\b{re.escape(key)}\s*:',js):fail(f"translation key absent: {key}")
hosts=sorted({urlparse(x).netloc for x in p.links if x.startswith("http")})
print(f"ids={len(p.ids)} links={len(p.links)} images={len(p.images)} scripts={len(p.scripts)} styles={len(p.styles)}")
print("external_hosts="+",".join(hosts))
print("EL CID static site checks: PASS")
