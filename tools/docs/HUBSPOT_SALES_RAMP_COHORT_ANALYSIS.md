# Sales Team Ramping Cohort Analysis Documentation

**Last Updated:** 2025-12-31  
**Script:** `tools/scripts/hubspot/sales_ramp_cohort_analysis.py`  
**Purpose:** Analyze sales rep performance from their start date, showing deals closed over time as a cohort analysis

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Business Logic](#business-logic)
   - [Deal Attribution Rules](#deal-attribution-rules)
   - [Cohort Month Calculation](#cohort-month-calculation)
   - [Team-Based Attribution](#team-based-attribution)
4. [Configuration](#configuration)
   - [Hardcoded Start Dates](#hardcoded-start-dates)
   - [Excluded Reps](#excluded-reps)
5. [Data Sources](#data-sources)
6. [Output Files](#output-files)
7. [Usage](#usage)
8. [Methodology](#methodology)
9. [Visualizations](#visualizations)
10. [Technical Details](#technical-details)

---

## Overview

The Sales Team Ramping Cohort Analysis script analyzes sales representative performance from their first day at Colppy, tracking deals closed over time. Each rep's trajectory is plotted from Month 0 (their first month) onwards, allowing for direct comparison of ramping performance across all reps regardless of their actual start date.

### Purpose

- **Track Ramping Performance:** Compare how sales reps perform at the same relative stage (Month 1, Month 2, etc.)
- **Identify Top Performers:** See which reps are closing the most deals at each stage
- **Analyze Growth Trajectories:** Visualize how reps evolve from their start date
- **Support Hiring Decisions:** Understand expected performance at different tenure stages

### Key Metrics

- **Deals Closed per Cohort Month:** Number of deals closed in each month relative to start date
- **Cumulative Deals:** Running total of deals closed since start date
- **Peak Performance Months:** Identify when reps hit their stride

---

## Key Features

### ✅ Complete Deal Attribution

- **Owner Attribution:** All deals count for the deal owner
- **Collaborator Attribution:** Accountant Channel reps get credit when they're collaborators
- **Team-Aware Logic:** Different rules for Closers vs Accountant Channel reps

### ✅ Accurate Start Dates

- **Hardcoded Start Dates:** Uses actual first day in Colppy (from INGRESOS tables)
- **Not First Deal Date:** Avoids issues with reassigned deals
- **Manual Maintenance:** Easy to update when new employees join

### ✅ Dynamic Month Range

- **Auto-Detection:** Automatically determines maximum months based on longest-tenured rep
- **Full Coverage:** Includes all months from Month 0 to present
- **Zero-Filled:** Shows 0 for months with no deals (allows proper comparison)

### ✅ Comprehensive Visualizations

- **Line Chart:** Shows individual rep trajectories over time
- **Heatmap Grid:** Color-coded grid showing deals per rep per month
- **Start Date Labels:** Rep names include start dates for context

---

## Business Logic

### Deal Attribution Rules

#### For Closers Team (e.g., Rocio Luque, Estefania Sol Arregui)

- ✅ **Count as Owner:** Deals count when rep is the deal owner
- ❌ **Do NOT Count as Collaborator:** Closers never get credit for being collaborators

**Example:**
- Deal owner: Rocio Luque → **Rocio gets credit** ✅
- Deal owner: Karina, Collaborator: Rocio → **Rocio does NOT get credit** ❌

#### For Accountant Channel Team (e.g., Karina Lorena Russo, Jair Josue Calas, Tatiana Amaya)

- ✅ **Count as Owner:** Deals count when rep is the deal owner
- ✅ **Count as Collaborator:** Deals count when rep is a collaborator (even if not owner)

**Example:**
- Deal owner: Estefania, Collaborator: Karina → **Both Estefania AND Karina get credit** ✅
- Deal owner: Karina → **Karina gets credit** ✅

### Cohort Month Calculation

**Month 0 = First Month (Start Month)**

The cohort month represents how many months have passed since the rep's start date:

```
Month 0 = Start month (first month in Colppy)
Month 1 = Second month
Month 2 = Third month
...
```

**Formula:**
```
If close_year == start_year:
    cohort_month = close_month - start_month  # Month 0 for first month
Else if close_year > start_year:
    months_diff = (close_year - start_year) * 12
    cohort_month = close_month - start_month + months_diff
```

**Example:**
- Rocio started: April 2024 (month 4, year 2024)
- Deal closed: December 2025 (month 12, year 2025)
- Cohort Month = (2025 - 2024) × 12 + (12 - 4) = 12 + 8 = **Month 20**

### Team-Based Attribution

The script correctly identifies reps' teams using the HubSpot Owners API (`/crm/v3/owners/{ownerId}`) and applies the appropriate attribution logic:

1. **Team Detection:** Uses Owners API to get team information from `teams` array
2. **Collaborator Parsing:** Reads `hs_all_collaborator_owner_ids` property (semicolon-separated)
3. **Owner Exclusion:** Skips owner ID if it appears in collaborator list (HubSpot includes owner when there are other collaborators)
4. **Attribution:** Applies team-specific rules (Closers = owner only, Accountant Channel = owner OR collaborator)

---

## Configuration

### Hardcoded Start Dates

**⚠️ IMPORTANT:** Start dates are manually maintained in the script. Update `SALES_REP_START_DATES` dictionary when new employees join.

**Location:** `main()` function in `sales_ramp_cohort_analysis.py`

**Format:**
```python
SALES_REP_START_DATES = {
    # INGRESOS 2024
    'Karina Lorena Russo': (9, 2024),   # September 2024
    'Rocio Luque': (4, 2024),           # April 2024
    
    # INGRESOS 2025
    'Estefania Sol Arregui': (3, 2025),  # March 2025
    'Tatiana Amaya': (7, 2025),          # July 2025
    'Jair Josue Calas': (9, 2025),       # September 2025
}
```

**Key Points:**
- Uses **actual first day in Colppy** (from INGRESOS tables), NOT first deal date
- Format: `(month_number, year)` where month is 1-12
- Supports alternate spellings (e.g., "Estefanía" with accent)

**How to Update:**
1. Open `tools/scripts/hubspot/sales_ramp_cohort_analysis.py`
2. Locate `SALES_REP_START_DATES` dictionary in `main()` function
3. Add new entry: `'Full Name': (month, year)`
4. Save and run script

### Excluded Reps

The following reps are automatically excluded from analysis:

- **Sofia Celentano:** Explicitly excluded (out/archived)
- **Mariano Alvarez Bor:** Explicitly excluded (out/archived)

**Location:** `get_all_sales_reps()` function

---

## Data Sources

### HubSpot API Calls

1. **Owners API:** `GET /crm/v3/owners`
   - Fetches all active owners
   - Filters by team membership (Closers, Accountant Channel)
   - Gets team information for attribution logic

2. **Deals Search API:** `POST /crm/v3/objects/deals/search`
   - Fetches closed won deals
   - Includes both `closedwon` and `34692158` (Recovery) stages
   - Properties fetched:
     - `dealname`
     - `amount`
     - `dealstage`
     - `closedate`
     - `createdate`
     - `hubspot_owner_id`
     - `hs_all_collaborator_owner_ids` ⭐ **Critical for collaborator attribution**

3. **Owner Details API:** `GET /crm/v3/owners/{ownerId}`
   - Gets team information for each rep
   - Used to determine Closers vs Accountant Channel

### Date Range

- **Start Date:** Earliest rep start date (currently April 2024)
- **End Date:** December 2025 (or latest available data)
- **Deals Filtered:** Only closed won deals (`closedwon` or `34692158` stages)

---

## Output Files

All output files are saved to: `tools/outputs/visualizations/hubspot/`

### 1. Cohort Data CSV
**File:** `sales_ramp_cohort_data.csv`

**Columns:**
- `rep_name`: Sales rep name
- `cohort_month`: Month from start (0, 1, 2, ...)
- `deals_count`: Deals closed in that month
- `cumulative_deals`: Running total of deals

**Purpose:** Raw cohort data for further analysis

### 2. Cohort Grid Table CSV
**File:** `cohort_grid_table.csv`

**Format:** Wide format with reps as columns, months as rows

**Columns:**
- `MES`: Cohort month (0, 1, 2, ...)
- `[Rep Name 1]`: Deals for that rep in that month
- `[Rep Name 2]`: Deals for that rep in that month
- ...

**Purpose:** Used for heatmap visualization

### 3. Deals Per Month Table CSV
**File:** `deals_per_rep_per_month.csv`

**Format:** Calendar months (Jan 2024, Feb 2024, ..., Dec 2025)

**Columns:**
- `Rep Name`
- `Jan 2024`, `Feb 2024`, ..., `Dec 2025`
- `Total`

**Purpose:** Calendar-based reporting (not cohort-based)

### 4. Visualizations

#### Line Chart
**File:** `sales_ramp_cohort_analysis.png`

**Features:**
- Individual lines for each rep
- X-axis: Cohort Month (Month 0 = First Month)
- Y-axis: Deals Closed in Month
- Legend includes start dates: "Rocio Luque (Apr 2024)"
- Markers show individual data points
- X marker at Month 0 indicates start

#### Heatmap Grid
**File:** `cohort_grid_visualization.png`

**Features:**
- Color-coded grid (darker blue = more deals)
- Rows: Sales reps (with start dates in labels)
- Columns: Cohort Months (M0, M1, M2, ...)
- Gray cells: No deals (0 deals)
- Numbers displayed in each cell
- Color bar legend shows scale (0-40+ deals)

---

## Usage

### Running the Script

```bash
cd /Users/virulana/openai-cookbook
python3 tools/scripts/hubspot/sales_ramp_cohort_analysis.py
```

### Prerequisites

1. **Environment Variables:**
   - `HUBSPOT_API_KEY` or `COLPPY_CRM_AUTOMATIONS` set in `.env` file

2. **Python Dependencies:**
   - `pandas`
   - `matplotlib`
   - `seaborn`
   - `numpy`
   - `python-dotenv`
   - HubSpot API client (from `tools/hubspot_api/`)

### Output

The script will:
1. ✅ Fetch all sales reps from HubSpot
2. ✅ Match reps to hardcoded start dates
3. ✅ Fetch all closed won deals from HubSpot
4. ✅ Calculate cohort data (including collaborator attribution)
5. ✅ Generate CSV tables
6. ✅ Create visualizations
7. ✅ Display summary statistics

---

## Methodology

### Step 1: Fetch Sales Reps

1. Get all active owners from HubSpot
2. Filter by team membership (Closers, Accountant Channel)
3. Exclude specified reps (Sofia, Mariano)
4. Map names to owner IDs

### Step 2: Match Start Dates

1. Load hardcoded `SALES_REP_START_DATES` dictionary
2. Match HubSpot rep names to start dates
3. Handle name variations (accents, alternate spellings)
4. Skip reps without start dates

### Step 3: Fetch Deals

1. Determine date range (earliest start date to December 2025)
2. Fetch deals with filters:
   - Stage: `closedwon` OR `34692158` (Recovery)
   - Close date: Within date range
3. Include required properties (especially `hs_all_collaborator_owner_ids`)

### Step 4: Calculate Cohort Data

For each deal:

1. **Identify Reps Involved:**
   - Check if deal owner is in our rep list → add to `reps_involved`
   - Parse `hs_all_collaborator_owner_ids` (semicolon-separated)
   - For each collaborator:
     - Skip if collaborator is also the owner (HubSpot includes owner in list)
     - Check if collaborator is Accountant Channel → add to `reps_involved`
     - Closers never added as collaborators

2. **Calculate Cohort Month:**
   - For each rep in `reps_involved`:
     - Get rep's start date (month, year)
     - Calculate cohort month using formula
     - Increment deal count for that rep/month

3. **Fill All Months:**
   - For each rep, create entries for Month 0 to max_month
   - Set deals_count = 0 for months with no deals
   - This ensures proper comparison across reps

### Step 5: Generate Outputs

1. **Cohort Data CSV:** Long format (rep_name, cohort_month, deals_count, cumulative_deals)
2. **Cohort Grid Table:** Wide format for visualization
3. **Deals Per Month Table:** Calendar-based table
4. **Visualizations:** Line chart and heatmap

---

## Visualizations

### Line Chart Features

- **Individual Trajectories:** Each rep has their own colored line
- **Cohort Alignment:** All reps start at Month 0, regardless of actual calendar date
- **Performance Comparison:** Easy to see who performs best at Month 1, Month 5, etc.
- **Growth Patterns:** Identify reps with consistent growth vs. inconsistent performance
- **Start Date Context:** Legend shows when each rep started (e.g., "Karina Lorena Russo (Sep 2024)")

### Heatmap Grid Features

- **Visual Intensity:** Color intensity shows deal volume
- **Complete Coverage:** All months shown, even with 0 deals (gray cells)
- **Quick Comparison:** Easy to compare reps side-by-side at same cohort month
- **Peak Identification:** Darkest cells show peak performance months
- **Start Dates:** Y-axis labels include start dates for context

---

## Technical Details

### API Endpoints Used

1. **Owners API:**
   - `GET /crm/v3/owners` - List all owners
   - `GET /crm/v3/owners/{ownerId}` - Get owner details (teams)

2. **Deals Search API:**
   - `POST /crm/v3/objects/deals/search` - Search deals with filters

### Critical Properties

- **`hs_all_collaborator_owner_ids`:** ⭐ Semicolon-separated string of owner IDs
  - Format: `"103406387;78535701"`
  - May include owner ID when there are other collaborators
  - Must parse and filter out owner ID

- **`hubspot_owner_id`:** Deal owner's owner ID

- **`closedate`:** Deal close date (ISO format)

- **`dealstage`:** Deal stage (`closedwon` or `34692158`)

### Attribution Logic Implementation

```python
# For each deal:
reps_involved = set()

# 1. Add owner if in rep list
if owner_id in rep_list:
    reps_involved.add(owner_rep_name)

# 2. Parse collaborators
collaborator_ids = parse(hs_all_collaborator_owner_ids)

for collab_id in collaborator_ids:
    # Skip if collaborator is also owner
    if collab_id == owner_id:
        continue
    
    # Get collaborator rep info
    collab_rep_name = get_rep_name(collab_id)
    collab_rep_team = get_rep_team(collab_rep_name)
    
    # Only Accountant Channel reps count as collaborators
    if collab_rep_team == "Accountant Channel":
        reps_involved.add(collab_rep_name)
```

### Data Validation

- ✅ Validates close dates are within expected range
- ✅ Skips deals with missing close dates
- ✅ Handles name variations (accents, alternate spellings)
- ✅ Validates owner IDs exist in HubSpot
- ✅ Confirms team membership before applying attribution rules

---

## Maintenance

### Adding New Sales Reps

1. **Get Start Date:** From INGRESOS table (actual first day in Colppy)
2. **Add to Dictionary:**
   ```python
   SALES_REP_START_DATES = {
       ...
       'New Rep Name': (month, year),  # e.g., (11, 2025) for November 2025
   }
   ```
3. **Verify Team:** Ensure rep is in "Closers" or "Accountant Channel" team in HubSpot
4. **Run Script:** New rep will automatically appear in analysis

### Updating Existing Rep Start Dates

1. Locate rep in `SALES_REP_START_DATES` dictionary
2. Update tuple: `(month, year)`
3. Run script to regenerate analysis

### Troubleshooting

**Issue: Rep not appearing in analysis**
- ✅ Check rep is in hardcoded start dates dictionary
- ✅ Verify rep is active in HubSpot (not archived)
- ✅ Confirm rep is in "Closers" or "Accountant Channel" team

**Issue: Deals count seems incorrect**
- ✅ Verify deal attribution rules (Closers vs Accountant Channel)
- ✅ Check if rep appears in collaborator list when they shouldn't
- ✅ Confirm `hs_all_collaborator_owner_ids` is being parsed correctly

**Issue: Start date showing incorrect**
- ✅ Update `SALES_REP_START_DATES` dictionary with correct date
- ✅ Format: `(month, year)` where month is 1-12

---

## Related Documentation

- **[README_HUBSPOT_CONFIGURATION.md](./README_HUBSPOT_CONFIGURATION.md)** - HubSpot API configuration and property mappings
- **[HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md](./HUBSPOT_COMPLETE_RETRIEVAL_QUICK_REFERENCE.md)** - Data retrieval patterns
- **[HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md)** - General HubSpot scripts documentation

---

**Version:** 1.0.0  
**Last Updated:** 2025-12-31  
**Maintained By:** CEO Assistant

