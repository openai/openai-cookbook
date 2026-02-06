#!/usr/bin/env python3
"""
Intercom conversation tags report (single script for fetch, process, and samples).

Modes:
  1. Fetch by date range: fetches from API, aggregates tags, writes CSV (progressive), prints report.
     Optional --output-samples writes tag -> sample conversation IDs JSON for validation.
  2. Process existing CSV: --from-csv PATH reads a report CSV and prints summary (no API call).
     Use --grouped and --markdown for grouped view and markdown tables.

Usage:
  python intercom_tags_report.py --last-week
  python intercom_tags_report.py --last-two-weeks --output-csv
  python intercom_tags_report.py --start-date 2025-01-21 --end-date 2025-01-28 --output-csv
  python intercom_tags_report.py --last-week --output-csv --output-samples --top-tags 5 --samples-per-tag 2
  python intercom_tags_report.py --from-csv tools/outputs/intercom_tags_report_20260115_20260128.csv --top 30 --markdown
  python intercom_tags_report.py --from-csv --grouped  (uses latest CSV in tools/outputs)
"""

import os
import sys
import argparse
import csv
import json
import time
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# Allow running from repo root: add script dir to path before importing local module
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from dotenv import load_dotenv

# Load .env from repo root when script is under tools/scripts/intercom/
_repo_root = os.path.abspath(os.path.join(_script_dir, "..", "..", ".."))
_dotenv_path = os.path.join(_repo_root, ".env")
if os.path.isfile(_dotenv_path):
    load_dotenv(_dotenv_path)
else:
    load_dotenv()

warnings.filterwarnings("ignore", message=".*OpenSSL.*LibreSSL.*")

from intercom_analytics import IntercomAnalytics, INTERCOM_ACCESS_TOKEN

try:
    import requests
except ImportError:
    requests = None

# Limits to avoid query timeouts and runaway runs (from observed Intercom API behavior)
REQUEST_TIMEOUT = 90        # seconds per HTTP request (Intercom can be slow under load)
PAGE_SLEEP = 0.5           # seconds between pages (rate-limit friendly)
# Script fetches all pages by default (no page/timeout cap); optional --max-pages and --timeout cap the run.


def get_last_week_dates():
    """Return (start_date, end_date) as YYYY-MM-DD for the last 7 days."""
    end = datetime.today().date()
    start = end - timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def get_last_two_weeks_dates():
    """Return (start_date, end_date) as YYYY-MM-DD for the last 14 days."""
    end = datetime.today().date()
    start = end - timedelta(days=13)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def load_tags_csv(path, sep=";"):
    """Load tag;count CSV. Returns list of (tag, count) sorted by count descending."""
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=sep)
        for row in reader:
            tag = (row.get("tag") or "").strip()
            try:
                count = int(row.get("count") or 0)
            except ValueError:
                count = 0
            if tag:
                rows.append((tag, count))
    rows.sort(key=lambda x: -x[1])
    return rows


def group_tags_by_prefix(rows, prefixes=("CS -", "Mod ", "Mod Cli", "Mod Cont", "Mod Tes", "Mod Inv", "Mod Cfg", "Mod Pro", "FC -", "MC-", "Cs -", "eSueldos", "CE -", "Consultas", "Chat-", "Colppy", "Bug", "Sugerencia")):
    """Group tag rows by first matching prefix. Returns dict prefix -> [(tag, count), ...]."""
    grouped = defaultdict(list)
    other = []
    for tag, count in rows:
        matched = False
        for p in prefixes:
            if tag.startswith(p) or tag.startswith(p.replace(" ", "")):
                grouped[p].append((tag, count))
                matched = True
                break
        if not matched:
            other.append((tag, count))
    if other:
        grouped["Otros"] = other
    return dict(grouped)


def find_latest_report_csv(output_dir):
    """Return path to most recent intercom_tags_report_*.csv in output_dir, or None."""
    if not os.path.isdir(output_dir):
        return None
    candidates = [f for f in os.listdir(output_dir) if f.startswith("intercom_tags_report_") and f.endswith(".csv")]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return os.path.join(output_dir, candidates[0])


def print_summary_from_csv(rows, csv_path, top_n=25, markdown=False):
    """Print summary of tag rows (from CSV) to stdout."""
    total_occurrences = sum(c for _, c in rows)
    unique_tags = len(rows)
    print(f"Source: {csv_path}")
    print(f"Unique tags: {unique_tags} | Total tag occurrences: {total_occurrences}")
    print()
    if markdown:
        print("| Tag | Count |")
        print("|-----|-------|")
        for tag, count in rows[:top_n]:
            print(f"| {tag} | {count} |")
    else:
        print(f"Top {top_n} tags:")
        for tag, count in rows[:top_n]:
            print(f"  {count:5d}  {tag}")
    print()


def print_grouped_from_csv(grouped, top_per_group=10, markdown=False):
    """Print grouped tag view to stdout."""
    for prefix in sorted(grouped.keys(), key=lambda k: -sum(c for _, c in grouped[k])):
        items = grouped[prefix]
        total = sum(c for _, c in items)
        print(f"--- {prefix} ({len(items)} tags, total count {total}) ---")
        if markdown:
            for tag, count in items[:top_per_group]:
                print(f"  | {tag} | {count} |")
        else:
            for tag, count in items[:top_per_group]:
                print(f"  {count:5d}  {tag}")
        if len(items) > top_per_group:
            print(f"  ... and {len(items) - top_per_group} more")
        print()


def aggregate_tags_from_dataframe(df):
    """
    Aggregate tag counts from conversations DataFrame.

    Expects df to have a 'tags' column where each value is a list of tag names
    (or empty list). Returns Counter of tag_name -> count.
    """
    all_tags = []
    if "tags" not in df.columns or df.empty:
        return Counter()
    for tags_list in df["tags"].dropna():
        if isinstance(tags_list, list):
            all_tags.extend(str(t).strip() for t in tags_list if t)
        elif tags_list:
            all_tags.append(str(tags_list).strip())
    return Counter(all_tags)


def _fetch_conversations_paginated(
    start_date,
    end_date,
    limit,
    token,
    verbose=True,
    max_pages=None,
    timeout_secs=None,
    request_timeout=None,
    on_page_fetched=None,
):
    """
    Fetch conversations from Intercom API, following pages until limit or no more.

    Uses same endpoint and param pattern as intercom_analytics. Returns list of
    conversation dicts. When limit > 150, multiple requests are made using
    starting_after from the response.

    If on_page_fetched(all_convs) is provided, it is called after each page with
    the cumulative list so far (e.g. to write progressive CSV output).

    Stops when: collected >= limit (if set), no next page, max_pages (if set), or
    timeout_secs (if set). When limit/max_pages/timeout_secs are None, fetches until no more pages.
    request_timeout is the HTTP timeout per request.
    """
    if not requests or not token:
        return None
    req_timeout = request_timeout if request_timeout is not None else REQUEST_TIMEOUT
    url = "https://api.intercom.io/conversations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    per_page = min(limit, 150) if limit is not None else 150
    params = {
        "created_after": int(start_date.timestamp()),
        "created_before": int(end_date.timestamp()),
        "per_page": per_page,
    }
    all_convs = []
    starting_after = None
    page = 1
    start_time = time.time()
    try:
        while limit is None or len(all_convs) < limit:
            if max_pages is not None and page > max_pages:
                if verbose:
                    print(f"  Stopping: max pages ({max_pages}) reached.")
                break
            if timeout_secs is not None and (time.time() - start_time) > timeout_secs:
                if verbose:
                    print(
                        f"  Stopping: total timeout ({timeout_secs}s) reached; returning partial results."
                    )
                break
            if starting_after is not None:
                params["starting_after"] = starting_after
            resp = requests.get(
                url, headers=headers, params=params, timeout=req_timeout
            )
            resp.raise_for_status()
            data = resp.json()
            convs = data.get("conversations") or data.get("data") or []
            if isinstance(convs, dict) and "conversations" in convs:
                convs = convs["conversations"]
            if not isinstance(convs, list):
                convs = []
            all_convs.extend(convs)
            if verbose:
                print(
                    f"  Page {page}: {len(convs)} conversations (total so far: {len(all_convs)})"
                )
            if on_page_fetched:
                try:
                    effective = all_convs[:limit] if limit is not None else all_convs
                    on_page_fetched(effective)
                except Exception as e:
                    print(f"  on_page_fetched failed: {e}", file=sys.stderr)
            if len(convs) < per_page:
                break
            pages = data.get("pages") or {}
            next_info = pages.get("next") if isinstance(pages, dict) else None
            if not next_info or not next_info.get("starting_after"):
                break
            starting_after = next_info["starting_after"]
            page += 1
            time.sleep(PAGE_SLEEP)
        return all_convs[:limit] if limit is not None else all_convs
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        return all_convs if all_convs else None


def _tags_from_conversation_dicts(convs):
    """Extract tag counts and stats from list of raw API conversation dicts."""
    all_tags = []
    with_tags = 0
    for c in convs or []:
        tags = []
        t = c.get("tags")
        if isinstance(t, dict):
            tag_list = t.get("tags") or []
        elif isinstance(t, list):
            tag_list = t
        else:
            tag_list = []
        for tag in tag_list:
            if isinstance(tag, dict) and tag.get("name"):
                tags.append(str(tag["name"]).strip())
            elif isinstance(tag, str) and tag not in ("type", "tags"):
                tags.append(tag.strip())
        if tags:
            with_tags += 1
        all_tags.extend(tags)
    return Counter(all_tags), with_tags, len(convs or [])


def tag_to_conversation_ids(convs):
    """
    Build a mapping tag_name -> [conversation_id, ...] from raw API conversation dicts.
    Conversation id is taken from each conv (id or conversation_id); returned as string for API use.
    """
    from collections import defaultdict
    tag_to_ids = defaultdict(list)
    for c in convs or []:
        conv_id = c.get("id") or c.get("conversation_id")
        if conv_id is None:
            continue
        conv_id = str(conv_id)
        t = c.get("tags")
        if isinstance(t, dict):
            tag_list = t.get("tags") or []
        elif isinstance(t, list):
            tag_list = t
        else:
            tag_list = []
        for tag in tag_list:
            name = None
            if isinstance(tag, dict) and tag.get("name"):
                name = str(tag["name"]).strip()
            elif isinstance(tag, str) and tag not in ("type", "tags"):
                name = tag.strip()
            if name and conv_id not in tag_to_ids[name]:
                tag_to_ids[name].append(conv_id)
    return dict(tag_to_ids)


def run_tags_report(
    start_date,
    end_date,
    limit=None,
    output_dir=None,
    output_csv=False,
    max_pages=None,
    timeout_secs=None,
    output_samples_path=None,
    top_tags_for_samples=5,
    samples_per_tag=2,
    output_ids_path=None,
):
    """
    Fetch conversations for the date range, aggregate tags, and return report data.

    By default fetches all conversations (no limit, no page/timeout cap). Optional
    limit, max_pages, and timeout_secs cap the run. Returns (tag_counts,
    conversations_with_tags, total_conversations, df).
    """
    if not INTERCOM_ACCESS_TOKEN:
        raise ValueError(
            "INTERCOM_ACCESS_TOKEN not set. Set it in the environment or in .env at repo root."
        )
    out_dir = output_dir or os.path.join(_repo_root, "tools", "outputs")
    os.makedirs(out_dir, exist_ok=True)

    if requests:
        if limit is None:
            print(f"Fetching all conversations from {start_date} to {end_date}...")
        else:
            print(f"Fetching up to {limit} conversations from {start_date} to {end_date}...")
        safe_start = start_date.replace("-", "")
        safe_end = end_date.replace("-", "")
        csv_path = os.path.join(
            out_dir, f"intercom_tags_report_{safe_start}_{safe_end}.csv"
        )

        def write_progress_csv(all_convs_so_far):
            if not all_convs_so_far:
                return
            tag_counts_so_far, _, _ = _tags_from_conversation_dicts(all_convs_so_far)
            if not tag_counts_so_far:
                return
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("tag;count\n")
                for t, c in tag_counts_so_far.most_common():
                    f.write(f"{t};{c}\n")

        on_page = write_progress_csv if output_csv else None
        convs = _fetch_conversations_paginated(
            start_date,
            end_date,
            limit,
            INTERCOM_ACCESS_TOKEN,
            verbose=True,
            max_pages=max_pages,
            timeout_secs=timeout_secs,
            on_page_fetched=on_page,
        )
        if convs is None:
            return Counter(), 0, 0, None
        tag_counts, with_tags, total = _tags_from_conversation_dicts(convs)
        if output_ids_path and convs:
            ids = []
            for c in convs:
                cid = c.get("id") or c.get("conversation_id")
                if cid is not None:
                    ids.append(str(cid))
            if ids:
                os.makedirs(os.path.dirname(output_ids_path) or ".", exist_ok=True)
                with open(output_ids_path, "w", encoding="utf-8") as f:
                    json.dump(ids, f, indent=0, ensure_ascii=False)
                print(f"Conversation IDs ({len(ids)}) written to {output_ids_path}")
        if output_samples_path and convs:
            tag_to_ids = tag_to_conversation_ids(convs)
            sorted_tags = sorted(
                tag_to_ids.keys(),
                key=lambda t: len(tag_to_ids[t]),
                reverse=True,
            )
            top_tags = sorted_tags[:top_tags_for_samples]
            result = {tag: tag_to_ids[tag][:samples_per_tag] for tag in top_tags}
            os.makedirs(os.path.dirname(output_samples_path) or ".", exist_ok=True)
            with open(output_samples_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Sample conversation IDs written to {output_samples_path}")
        df = None
    else:
        analytics = IntercomAnalytics(INTERCOM_ACCESS_TOKEN, output_dir=out_dir)
        print(f"Fetching conversations from {start_date} to {end_date} (limit={limit})...")
        df = analytics.get_conversations(
            start_date=start_date, end_date=end_date, limit=limit
        )
        if df is None or df.empty:
            return Counter(), 0, 0, df
        total = len(df)
        tag_counts = aggregate_tags_from_dataframe(df)
        with_tags = len(df[df["tags"].apply(lambda x: bool(x) if isinstance(x, list) else False)])

    if output_csv and tag_counts:
        if not requests:
            safe_start = start_date.replace("-", "")
            safe_end = end_date.replace("-", "")
            csv_path = os.path.join(
                out_dir, f"intercom_tags_report_{safe_start}_{safe_end}.csv"
            )
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("tag;count\n")
                for t, c in tag_counts.most_common():
                    f.write(f"{t};{c}\n")
        print(f"Tag counts written to {csv_path}")

    return tag_counts, with_tags, total, df


def print_report(tag_counts, with_tags, total, start_date, end_date):
    """Print a formatted tag report to stdout."""
    print()
    print("=" * 60)
    print("INTERCOM CONVERSATION TAGS REPORT")
    print("=" * 60)
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Total conversations: {total}")
    print(f"  Conversations with at least one tag: {with_tags}")
    print()
    if not tag_counts:
        print("  No tags found in this set of conversations.")
        return
    print("  Tag counts (descending):")
    print("  " + "-" * 50)
    for tag, count in tag_counts.most_common(80):
        print(f"    {count:4d}  {tag}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Intercom conversation tags report (uses existing intercom_analytics logic)"
    )
    parser.add_argument(
        "--last-week",
        action="store_true",
        help="Use last 7 days as date range",
    )
    parser.add_argument(
        "--last-two-weeks",
        action="store_true",
        help="Use last 14 days as date range (finishes within default timeout)",
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="Start date (inclusive)",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="End date (inclusive)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max conversations to fetch (default: no limit, fetch all in date range)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Max API pages (~150 convs each). Default: no cap, fetch all pages.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECS",
        dest="timeout_secs",
        help="Total seconds before stopping (returns partial results). Default: no cap.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for CSV when --output-csv is set (default: tools/outputs)",
    )
    parser.add_argument(
        "--output-csv",
        action="store_true",
        help="Write tag counts to a CSV file in output-dir",
    )
    parser.add_argument(
        "--from-csv",
        nargs="?",
        const="",
        metavar="PATH",
        default=None,
        help="Process existing CSV (no fetch). PATH or omit to use latest in --output-dir. Use --grouped, --top, --markdown.",
    )
    parser.add_argument(
        "--grouped",
        action="store_true",
        help="With --from-csv: print tags grouped by prefix (CS -, Mod *, etc.)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        metavar="N",
        help="With --from-csv: show top N tags (default: 25)",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="With --from-csv: print tables in markdown",
    )
    parser.add_argument(
        "--top-per-group",
        type=int,
        default=10,
        help="With --from-csv --grouped: show top N per group (default: 10)",
    )
    parser.add_argument(
        "--output-samples",
        nargs="?",
        const="",
        metavar="PATH",
        default=None,
        help="With date range: also write tag -> sample conversation IDs JSON (for validation). PATH or omit for default name.",
    )
    parser.add_argument(
        "--top-tags",
        type=int,
        default=5,
        metavar="N",
        help="With --output-samples: number of top tags to sample (default: 5)",
    )
    parser.add_argument(
        "--samples-per-tag",
        type=int,
        default=2,
        metavar="K",
        help="With --output-samples: conversation IDs per tag (default: 2)",
    )
    parser.add_argument(
        "--output-ids",
        nargs="?",
        const="",
        metavar="PATH",
        default=None,
        help="With date range: write all fetched conversation IDs to a JSON array file (for taxonomy script). PATH or omit for default name.",
    )

    args = parser.parse_args()

    if args.from_csv is not None:
        out_dir = args.output_dir or os.path.join(_repo_root, "tools", "outputs")
        out_dir = os.path.abspath(out_dir)
        csv_path = args.from_csv if args.from_csv else find_latest_report_csv(out_dir)
        if not csv_path:
            print("No CSV path given and no intercom_tags_report_*.csv in output dir.", file=sys.stderr)
            return 1
        if csv_path and not os.path.isfile(csv_path):
            print(f"File not found: {csv_path}", file=sys.stderr)
            return 1
        if not csv_path:
            return 1
        if args.from_csv == "":
            print(f"Using latest report: {csv_path}\n")
        rows = load_tags_csv(csv_path)
        if not rows:
            print("No tag rows in CSV.", file=sys.stderr)
            return 1
        print_summary_from_csv(rows, csv_path, top_n=args.top, markdown=args.markdown)
        if args.grouped:
            grouped = group_tags_by_prefix(rows)
            print_grouped_from_csv(grouped, top_per_group=args.top_per_group, markdown=args.markdown)
        return 0

    if args.last_week:
        start_date, end_date = get_last_week_dates()
    elif args.last_two_weeks:
        start_date, end_date = get_last_two_weeks_dates()
    elif args.start_date and args.end_date:
        start_date, end_date = args.start_date, args.end_date
    else:
        parser.error(
            "Use --last-week, --last-two-weeks, or both --start-date and --end-date."
        )

    out_dir = args.output_dir or os.path.join(_repo_root, "tools", "outputs")
    out_dir = os.path.abspath(out_dir)
    safe_start = start_date.replace("-", "")
    safe_end = end_date.replace("-", "")
    samples_path = None
    if args.output_samples is not None:
        samples_path = args.output_samples if args.output_samples else os.path.join(out_dir, f"intercom_tag_samples_{safe_start}_{safe_end}.json")
    ids_path = None
    if args.output_ids is not None:
        ids_path = args.output_ids if args.output_ids else os.path.join(out_dir, f"intercom_conversation_ids_{safe_start}_{safe_end}.json")
    try:
        tag_counts, with_tags, total, _ = run_tags_report(
            start_date=start_date,
            end_date=end_date,
            limit=args.limit,
            output_dir=out_dir,
            output_csv=args.output_csv,
            max_pages=args.max_pages,
            timeout_secs=args.timeout_secs,
            output_samples_path=samples_path,
            top_tags_for_samples=args.top_tags,
            samples_per_tag=args.samples_per_tag,
            output_ids_path=ids_path,
        )
        print_report(tag_counts, with_tags, total, start_date, end_date)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
