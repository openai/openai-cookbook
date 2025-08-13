#!/usr/bin/env python3
"""
Parametrizable Google Ads report generator (ICP, campaigns, keywords).

Inputs (env or CLI):
- GOOGLE_ADS_DEVELOPER_TOKEN
- GOOGLE_ADS_LOGIN_CUSTOMER_ID (no dashes)
- GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET / GOOGLE_ADS_REFRESH_TOKEN (if oauth)
- GOOGLE_ADS_CUSTOMER_ID (target client, no dashes)
- --start_date YYYY-MM-DD
- --end_date YYYY-MM-DD
- --output_path /abs/path.csv (optional)

Outputs:
- Prints a concise Markdown summary with AR number formatting
- Optional CSV export with metadata footer
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from typing import List, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def format_money_ars_micros(cost_micros: int) -> str:
    pesos = cost_micros / 1_000_000
    return f"${pesos:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_number_ar(n: float | int) -> str:
    if isinstance(n, int):
        return f"{n:,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def build_client() -> GoogleAdsClient:
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")

    if not dev_token or not login_id or not client_id or not client_secret or not refresh_token:
        print("Missing required Google Ads env vars.")
        sys.exit(1)

    cfg = {
        "developer_token": dev_token,
        "use_proto_plus": True,
        "login_customer_id": login_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    return GoogleAdsClient.load_from_dict(cfg)


def run_query(client: GoogleAdsClient, customer_id: str, query: str) -> List:
    service = client.get_service("GoogleAdsService")
    return list(service.search(customer_id=customer_id, query=query))


def compute_rates(clicks: int, impressions: int, cost_micros: int, conversions: float) -> Tuple[str, str, str, str]:
    ctr = f"{(clicks / impressions * 100):.2f}%" if impressions else "0,00%"
    cpc = format_money_ars_micros(int(cost_micros / clicks)) if clicks else "$0,00"
    cpa = format_money_ars_micros(int(cost_micros / conversions)) if conversions else "—"
    roas = "0,00x"  # conversions_value is currency-less in our GAQL; skip ratio calc here
    return ctr, cpc, cpa, roas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start_date", required=True)
    parser.add_argument("--end_date", required=True)
    parser.add_argument("--customer_id", default=os.environ.get("GOOGLE_ADS_CUSTOMER_ID"))
    parser.add_argument("--login_customer_id", default=os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    parser.add_argument("--output_path", default="")
    args = parser.parse_args()

    try:
        datetime.strptime(args.start_date, "%Y-%m-%d")
        datetime.strptime(args.end_date, "%Y-%m-%d")
    except ValueError:
        print("Dates must be YYYY-MM-DD")
        sys.exit(1)

    if not args.customer_id or not args.login_customer_id:
        print("customer_id and login_customer_id are required")
        sys.exit(1)

    client = build_client()

    # ICP level
    icp_q = f"""
    SELECT customer.id, customer.descriptive_name,
           metrics.impressions, metrics.clicks, metrics.cost_micros,
           metrics.conversions, metrics.conversions_value
    FROM customer
    WHERE segments.date >= '{args.start_date}' AND segments.date <= '{args.end_date}'
    """

    # Campaigns
    camp_q = f"""
    SELECT campaign.id, campaign.name,
           metrics.impressions, metrics.clicks, metrics.cost_micros,
           metrics.conversions, metrics.conversions_value
    FROM campaign
    WHERE segments.date >= '{args.start_date}' AND segments.date <= '{args.end_date}'
    ORDER BY metrics.cost_micros DESC LIMIT 200
    """

    # Keywords
    kw_q = f"""
    SELECT ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
           ad_group.name, campaign.name,
           metrics.impressions, metrics.clicks, metrics.cost_micros,
           metrics.conversions, metrics.conversions_value
    FROM keyword_view
    WHERE segments.date >= '{args.start_date}' AND segments.date <= '{args.end_date}'
    ORDER BY metrics.cost_micros DESC LIMIT 200
    """

    try:
        icp_rows = run_query(client, args.customer_id, icp_q)
        camp_rows = run_query(client, args.customer_id, camp_q)
        kw_rows = run_query(client, args.customer_id, kw_q)
    except GoogleAdsException as ex:
        print("Google Ads API error:", ex.error.code().name)
        for e in ex.failure.errors:
            print(" -", e.message)
        sys.exit(1)

    # Aggregate ICP
    if not icp_rows:
        print("No data for the selected period.")
        return
    m = icp_rows[0].metrics
    icp = {
        "impr": int(m.impressions),
        "clicks": int(m.clicks),
        "cost": int(m.cost_micros),
        "conv": float(m.conversions),
        "conv_value": float(m.conversions_value or 0),
    }
    ctr, cpc, cpa, roas = compute_rates(icp["clicks"], icp["impr"], icp["cost"], icp["conv"])

    print(f"Date range: {args.start_date} to {args.end_date}")
    print("ICP overview")
    print(f"- Impressions: {format_number_ar(icp['impr'])}")
    print(f"- Clicks: {format_number_ar(icp['clicks'])}")
    print(f"- Cost: {format_money_ars_micros(icp['cost'])}")
    print(f"- Conversions: {format_number_ar(icp['conv'])}")
    print(f"- Conversion value: {format_number_ar(icp['conv_value'])}")
    print(f"- CTR: {ctr}")
    print(f"- CPC: {cpc}")
    print(f"- CPA: {cpa}")
    print(f"- ROAS: {roas}")

    # Optionally export CSV
    if args.output_path:
        with open(args.output_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Level", "Campaign", "Ad Group", "Keyword", "Impr.", "Clicks", "Cost_micros", "Conv.", "Conv. value"])
            # Campaigns
            for r in camp_rows:
                w.writerow([
                    "campaign",
                    r.campaign.name,
                    "",
                    "",
                    int(r.metrics.impressions),
                    int(r.metrics.clicks),
                    int(r.metrics.cost_micros),
                    float(r.metrics.conversions),
                    float(r.metrics.conversions_value or 0),
                ])
            # Keywords
            for r in kw_rows:
                w.writerow([
                    "keyword",
                    r.campaign.name,
                    r.ad_group.name,
                    r.ad_group_criterion.keyword.text,
                    int(r.metrics.impressions),
                    int(r.metrics.clicks),
                    int(r.metrics.cost_micros),
                    float(r.metrics.conversions),
                    float(r.metrics.conversions_value or 0),
                ])
            # Metadata footer
            w.writerow([])
            w.writerow(["metadata", f"date_range={args.start_date}:{args.end_date}", "source=Google Ads API", f"customer_id={args.customer_id}", f"login_customer_id={args.login_customer_id}"])


if __name__ == "__main__":
    main()


