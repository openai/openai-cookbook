#!/usr/bin/env python3
"""
Export current Google Ads campaign inventory to a timestamped JSON file.

Environment variables required:
- GOOGLE_ADS_DEVELOPER_TOKEN
- GOOGLE_ADS_CLIENT_ID
- GOOGLE_ADS_CLIENT_SECRET
- GOOGLE_ADS_REFRESH_TOKEN
- GOOGLE_ADS_LOGIN_CUSTOMER_ID (manager or self)
- GOOGLE_ADS_CUSTOMER_ID (target client account, no dashes)

Output:
- tools/outputs/google_ads_campaign_inventory_YYYYMMDD_HHMMSS.json

Notes:
- Keeps output small and structured for reliable future diffs.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List

from google.ads.googleads.client import GoogleAdsClient


def build_client() -> GoogleAdsClient:
    cfg = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
        "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
    }
    if not cfg["login_customer_id"]:
        # Fallback to customer as login if manager not set
        cfg["login_customer_id"] = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")
    return GoogleAdsClient.load_from_dict(cfg)


def fetch_campaigns(client: GoogleAdsClient, customer_id: str) -> List[Dict[str, Any]]:
    service = client.get_service("GoogleAdsService")
    query = """
    SELECT 
      campaign.resource_name,
      campaign.id,
      campaign.name,
      campaign.status,
      campaign.advertising_channel_type,
      campaign.advertising_channel_sub_type,
      campaign.bidding_strategy_type,
      campaign.campaign_budget,
      campaign.tracking_url_template,
      campaign.final_url_suffix,
      campaign.start_date,
      campaign.end_date
    FROM campaign
    ORDER BY campaign.id
    """
    rows = service.search(customer_id=customer_id, query=query)
    items: List[Dict[str, Any]] = []
    for r in rows:
        c = r.campaign
        items.append(
            {
                "resource_name": str(c.resource_name),
                "id": int(c.id),
                "name": str(c.name),
                "status": c.status.name if c.status else "UNKNOWN",
                "channel": c.advertising_channel_type.name
                if c.advertising_channel_type
                else "UNKNOWN",
                "subtype": c.advertising_channel_sub_type.name
                if c.advertising_channel_sub_type
                else "UNKNOWN",
                "bidding": c.bidding_strategy_type.name
                if c.bidding_strategy_type
                else "UNKNOWN",
                "budget_resource": str(c.campaign_budget),
                "tracking_url_template": str(getattr(c, "tracking_url_template", "")),
                "final_url_suffix": str(getattr(c, "final_url_suffix", "")),
                "start_date": str(getattr(c, "start_date", "")),
                "end_date": str(getattr(c, "end_date", "")),
            }
        )
    return items


def main() -> None:
    out_dir = pathlib.Path(__file__).resolve().parents[1] / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"google_ads_campaign_inventory_{stamp}.json"

    customer_id = os.environ["GOOGLE_ADS_CUSTOMER_ID"]
    client = build_client()

    items = fetch_campaigns(client, customer_id)
    payload = {
        "generated_at": stamp,
        "customer_id": customer_id,
        "campaigns": items,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Minimal on-screen summary
    print("Inventory saved:", str(out_path))
    print("Count:", len(items))
    for it in items[:20]:
        print("-", it["id"], "|", it["name"], "|", it["status"], "|", it["channel"])


if __name__ == "__main__":
    main()






