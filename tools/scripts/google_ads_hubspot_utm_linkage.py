#!/usr/bin/env python3
"""
Link HubSpot contacts' UTM campaign to Google Ads campaigns for a given date range.

Inputs (env or CLI; no hard-coded dates):
- HUBSPOT_PRIVATE_APP_TOKEN (or PRIVATE_APP_ACCESS_TOKEN)
- GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID, GOOGLE_ADS_CLIENT_ID,
  GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_CUSTOMER_ID
- --start_date YYYY-MM-DD
- --end_date YYYY-MM-DD
- --hs_utm_campaign_prop name of the HubSpot contact property holding UTM campaign (default: utm_campaign)
- --output_path /abs/path.csv (optional consolidated mapping export)

Outputs:
- Console summary of matches/unmatched
- Optional CSV with rows: contact_id, email, hs_utm_campaign, matched_campaign_id, matched_campaign_name
  and a metadata footer (date range, sources, record counts)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import requests
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from rich.console import Console
from rich.table import Table


def getenv_fallback(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def iso_utc(date_str: str, end_of_day: bool = False) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def build_ga_client() -> GoogleAdsClient:
    cfg = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
    }
    return GoogleAdsClient.load_from_dict(cfg)


def fetch_google_ads_campaigns(client: GoogleAdsClient, customer_id: str, start_date: str, end_date: str) -> Dict[str, Dict[str, str]]:
    q = f"""
    SELECT campaign.id, campaign.name,
           campaign.tracking_url_template,
           campaign.final_url_suffix,
           campaign.url_custom_parameters
    FROM campaign
    WHERE segments.date >= '{start_date}' AND segments.date <= '{end_date}'
    """
    svc = client.get_service("GoogleAdsService")
    rows = svc.search(customer_id=customer_id, query=q)
    cmap: Dict[str, Dict[str, str]] = {}
    for r in rows:
        cid = str(r.campaign.id)
        name = str(r.campaign.name)
        track = str(getattr(r.campaign, "tracking_url_template", "") or "")
        suffix = str(getattr(r.campaign, "final_url_suffix", "") or "")
        # url_custom_parameters is a repeated field; flatten to key=value pairs
        params = []
        try:
            for p in r.campaign.url_custom_parameters:
                params.append(f"{p.key}={p.value}")
        except Exception:
            pass
        cmap[cid] = {
            "id": cid,
            "name": name,
            "name_norm": normalize(name),
            "tracking": track,
            "suffix": suffix,
            "params": "&".join(params),
        }
    return cmap


def normalize(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s.lower()).strip("_")


def money_ars_from_micros(micros: int) -> str:
    pesos = micros / 1_000_000
    s = f"{pesos:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return "$" + s


def fetch_campaign_metrics(client: GoogleAdsClient, customer_id: str, start_date: str, end_date: str, campaign_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not campaign_ids:
        return {}
    svc = client.get_service("GoogleAdsService")
    metrics: Dict[str, Dict[str, int]] = {}
    # chunk the IN list to avoid GAQL size limits
    for i in range(0, len(campaign_ids), 100):
        chunk = campaign_ids[i : i + 100]
        in_list = ",".join(chunk)
        q = f"""
        SELECT campaign.id, campaign.name,
               metrics.cost_micros, metrics.clicks, metrics.impressions
        FROM campaign
        WHERE segments.date >= '{start_date}' AND segments.date <= '{end_date}'
          AND campaign.id IN ({in_list})
        """
        for r in svc.search(customer_id=customer_id, query=q):
            cid = str(r.campaign.id)
            metrics[cid] = {
                "name": str(r.campaign.name),
                "cost_micros": int(r.metrics.cost_micros or 0),
                "clicks": int(r.metrics.clicks or 0),
                "impr": int(r.metrics.impressions or 0),
            }
    return metrics


def fetch_hubspot_contacts(token: str, start_iso: str, end_iso: str, utm_prop: str) -> List[Dict[str, str]]:
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    contacts: List[Dict[str, str]] = []
    after = None
    while True:
        body = {
            "limit": 100,
            "properties": ["email", utm_prop],
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "createdate", "operator": "GTE", "value": start_iso},
                        {"propertyName": "createdate", "operator": "LTE", "value": end_iso},
                    ]
                }
            ],
        }
        if after:
            body["after"] = after
        resp = requests.post(url, headers=headers, json=body, timeout=40)
        if resp.status_code != 200:
            print("HubSpot error:", resp.status_code, resp.text)
            sys.exit(1)
        data = resp.json()
        for it in data.get("results", []):
            props = it.get("properties", {})
            utm_val = (props.get(utm_prop) or "").strip()
            if utm_val:
                contacts.append({
                    "id": it.get("id"),
                    "email": props.get("email", ""),
                    "utm_campaign": utm_val,
                })
        page = data.get("paging", {}).get("next", {})
        after = page.get("after")
        if not after:
            break
    return contacts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start_date", required=True)
    p.add_argument("--end_date", required=True)
    p.add_argument("--customer_id", default=os.environ.get("GOOGLE_ADS_CUSTOMER_ID"))
    p.add_argument("--login_customer_id", default=os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    p.add_argument("--hs_utm_campaign_prop", default=os.environ.get("HUBSPOT_UTM_CAMPAIGN_PROP", "utm_campaign"))
    p.add_argument("--output_path", default="")
    args = p.parse_args()

    # Env checks
    token = getenv_fallback("HUBSPOT_PRIVATE_APP_TOKEN", "PRIVATE_APP_ACCESS_TOKEN")
    for key in ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"]:
        if not os.environ.get(key):
            print(f"Missing env: {key}")
            sys.exit(1)
    if not token:
        print("Missing env: HUBSPOT_PRIVATE_APP_TOKEN or PRIVATE_APP_ACCESS_TOKEN")
        sys.exit(1)
    if not args.customer_id:
        print("Missing customer_id")
        sys.exit(1)

    # Dates
    try:
        start_iso = iso_utc(args.start_date)
        end_iso = iso_utc(args.end_date, end_of_day=True)
    except ValueError:
        print("Dates must be YYYY-MM-DD")
        sys.exit(1)

    # Fetch
    try:
        ga_client = build_ga_client()
        cmap = fetch_google_ads_campaigns(ga_client, args.customer_id, args.start_date, args.end_date)
    except GoogleAdsException as ex:
        print("Google Ads API error:", ex.error.code().name)
        for e in ex.failure.errors:
            print(" -", e.message)
        sys.exit(1)

    hs_contacts = fetch_hubspot_contacts(token, start_iso, end_iso, args.hs_utm_campaign_prop)

    # Join by normalized name
    matches: List[Tuple[str, str, str, str]] = []
    unmatched: List[Tuple[str, str, str]] = []
    # Build lookup structures
    name_index = {cinfo["name_norm"]: cid for cid, cinfo in cmap.items()}

    def campaign_contains_utm(cinfo: Dict[str, str], utm: str) -> bool:
        u = utm.lower()
        return (
            u in (cinfo["name"].lower())
            or (u in cinfo["tracking"].lower() if cinfo["tracking"] else False)
            or (u in cinfo["suffix"].lower() if cinfo["suffix"] else False)
            or (u in cinfo["params"].lower() if cinfo["params"] else False)
        )

    for c in hs_contacts:
        utm_raw = c["utm_campaign"].strip()
        utm_norm = normalize(utm_raw)
        cid = name_index.get(utm_norm)
        if not cid:
            # Try contains match over campaign tracking artifacts
            for k, info in cmap.items():
                if campaign_contains_utm(info, utm_raw) or campaign_contains_utm(info, utm_norm):
                    cid = k
                    break
        if cid:
            matches.append((c["id"], c["email"], utm_raw, cid))
        else:
            unmatched.append((c["id"], c["email"], utm_raw))

    # Print summary header
    console = Console()
    console.print(f"Date range: {args.start_date} to {args.end_date}")
    console.print(f"HubSpot contacts with {args.hs_utm_campaign_prop}: {len(hs_contacts)}")
    console.print(f"Matched to Google Ads campaigns: {len(matches)}")
    console.print(f"Unmatched: {len(unmatched)}")

    # Pretty CPA table (conversion = HubSpot contact)
    if matches:
        # aggregate contacts by campaign
        camp_counts: Dict[str, int] = {}
        for _, _, _, gid in matches:
            camp_counts[gid] = camp_counts.get(gid, 0) + 1

        metrics = fetch_campaign_metrics(ga_client, args.customer_id, args.start_date, args.end_date, list(camp_counts.keys()))

        table = Table(show_header=True, header_style="bold")
        table.add_column("Campaign", style="white", overflow="fold")
        table.add_column("Contacts", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("CPA", justify="right")
        table.add_column("Clicks", justify="right")
        table.add_column("Impr.", justify="right")

        tot_cost = 0
        tot_contacts = 0
        for cid, cnt in sorted(camp_counts.items(), key=lambda x: -x[1]):
            m = metrics.get(cid, {"name": cmap[cid]["name"], "cost_micros": 0, "clicks": 0, "impr": 0})
            cost = int(m.get("cost_micros", 0))
            cpa = money_ars_from_micros(int(cost / cnt)) if cnt else "—"
            table.add_row(
                m.get("name", cmap[cid]["name"]),
                f"{cnt}",
                money_ars_from_micros(cost),
                cpa,
                f"{m.get('clicks', 0):,}".replace(",", "."),
                f"{m.get('impr', 0):,}".replace(",", "."),
            )
            tot_cost += cost
            tot_contacts += cnt

        console.print("")
        console.print("Campaign CPA (conversion = HubSpot contact)")
        console.print(table)

        console.print("")
        console.print("Totals")
        console.print(f"- Cost: {money_ars_from_micros(tot_cost)}")
        console.print(f"- Contacts: {tot_contacts:,}".replace(",", "."))
        console.print(f"- Blended CPA: {money_ars_from_micros(int(tot_cost/tot_contacts)) if tot_contacts else '—'}")

    # Optional export
    if args.output_path:
        os.makedirs(os.path.dirname(args.output_path), exist_ok=True)
        with open(args.output_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["contact_id", "email", "hs_utm_campaign", "ga_campaign_id", "ga_campaign_name"])
            for cid, email, hs_utm, gid in matches:
                w.writerow([cid, email, hs_utm, gid, cmap[gid]["name"]])
            # metadata
            w.writerow([])
            w.writerow(["metadata", f"date_range={args.start_date}:{args.end_date}", "source=HubSpot+GoogleAds", f"records={len(matches)}", f"unmatched={len(unmatched)}"])


if __name__ == "__main__":
    main()


