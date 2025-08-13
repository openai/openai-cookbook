# Colppy Analytics Codebase – Repository Structure

This repository is organized for clarity, maintainability, and data-driven analytics across Mixpanel, HubSpot, and Intercom platforms.

## Directory Structure

- **scripts/**
  - **mixpanel/**
    - `mixpanel_api.py` – Core Mixpanel JQL API wrapper. Handles authentication and provides methods to run JQL queries and fetch data from Mixpanel.
    - `get_company_stats.py` – Retrieves comprehensive statistics for a given company, including event counts, user activity, daily event trends, and top user activities, using Mixpanel JQL queries.
    - `get_company_stats_simple.py` – Fetches and exports simple event counts for a company over a date range. Outputs a CSV with event names, counts, and percentages.
    - `hubspot_mixpanel_integration.py` – Integrates HubSpot and Mixpanel by fetching closed-won deals from HubSpot and extracting associated company IDs for further Mixpanel analysis.
    - `find_user_companies.py` – Identifies all companies associated with a given user (by email) in Mixpanel, using events, user profiles, and group membership.
    - `batch_closed_won_mixpanel_stats.py` – Automates batch extraction of Mixpanel event stats for all companies with closed-won deals (from a HubSpot export), handling API rate limits and exporting results.
    - `export_company_details.py` – Exports detailed information for a company, including properties, event counts, and user lists, to CSV and JSON files.
    - `export_active_companies_2025.py` – Extracts and exports a list of all companies active in 2025 (based on login events) to a CSV file.
    - Data exports: CSV/JSON files for companies and events
    - **mixpanel html/** – HTML assets (not scripts)
  - **hubspot/**
    - `fetch_hubspot_deals_with_company.py` – Fetches all HubSpot deals closed in May 2025, including associated company IDs and owner mapping, and exports the results to a CSV file.
    - `fetch_hubspot_contacts_may_2025.py` – (Template/utility) Outlines how to fetch HubSpot contacts created in a date range, and provides functions for analyzing, visualizing, and reporting on contact data. Assumes data is fetched externally and focuses on analysis and visualization.
    - `fetch_hubspot_leads_may_2025.py` – Fetches all HubSpot contacts (leads) created in May 2025 using the API, paginates through results, and saves raw data for further analysis. Includes owner mapping and utility functions for time calculations.
    - `analyze_cycle_times.py` – Analyzes lead cycle times from a CSV export, converting days to minutes, and provides group-by analysis (e.g., by lead source, conversion status) for key funnel metrics.
    - `analyze_deal_cycle_times.py` – Performs detailed analysis of deal cycle times, likely with more advanced or granular metrics than analyze_cycle_times.py.
    - `export_cycle_times.py` – Exports processed cycle time metrics to a CSV or other format for reporting.
    - Data: CSVs and owner lists
  - **intercom/**
    - `intercom_analytics.py` – Comprehensive analytics suite for Intercom data. Connects to the Intercom API, fetches team members, teams, and conversations, and provides advanced analysis (e.g., clustering, response times, satisfaction metrics, team performance, and visualizations).
    - `fast-export-intercom.js` – Node.js script for high-performance export of Intercom conversations. Uses concurrency and batching to efficiently download and write conversation data to CSV, with robust error handling and progress reporting.
    - `analyze.js` – Provides additional or custom analytics on exported Intercom data, possibly for specific business questions or reporting.
    - `index.js` – Entry point or utility script for Intercom data processing, possibly orchestrating exports or analysis.
    - `run_intercom_analysis.py` – Runs a predefined set of analytics or reports on Intercom data, likely leveraging intercom_analytics.py.
    - **common/** – (currently empty or not present)
  - **outputs/** – (legacy or script-specific outputs)

- **outputs/**
  - **csv_data/**
    - **mixpanel/**
      - `active_companies_2025.csv`, `Colppy_User_Level_Production_lexicon_data_2025_05_18_16_05_17.csv`
      - **company_events/** – Per-company event CSVs
    - **hubspot/** – Deals, leads, contacts, etc.
    - **intercom/** – Conversation exports
  - **visualizations/**
    - **hubspot/**, **intercom/**, **mixpanel/** – Chart/graph outputs

- **notebooks/**
  - `intercom_analysis.ipynb`, `example_analysis.ipynb`
  - **jupyter/**
    - `hubspot_leads_analysis.ipynb`

- **docs/**
  - `README_NEW_STRUCTURE.md` (this file)
  - `README_MIXPANEL_API.md`, `README_HUBSPOT_CONFIGURATION.md`, `README_INTERCOM.md`
  - **references/**
    - `mixpanel_jql_queries.txt`, `insights_sueldos_colppy.txt`
  - `conf.py`

- **tests/** – Test scripts
- **conversation_exports/**, **hubspot_reports/**, **mixpanel_reports/** – Archival or legacy data
- **.venv/**, **venv/** – Python virtual environments
- **.vscode/**, **node_modules/** – IDE and Node.js dependencies
- **README.md**, **requirements.txt**, **.pre-commit-config.yaml**, **package.json**, **package-lock.json**, **.cursorrules** – Project config and metadata

---

## Key Principles
- **API- and data-driven:** All analytics and exports use official APIs or direct data exports. No web scraping or Playwright scripts remain.
- **Outputs:** All data and visualizations are organized by platform and type for easy access and reproducibility.
- **Jupyter Notebooks:** Used for exploratory analysis, prototyping, and reproducible research.
- **Documentation:** Centralized in `docs/` with detailed API usage, configuration, and workflow guides.

## Environment Setup

This project uses Python 3.9+ and requires dependencies listed in `requirements.txt`.

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

All scripts maintain their original functionality but are now better organized. When running scripts, use the correct paths for input and output files. Refer to the documentation in `docs/` for details on each workflow and integration.

