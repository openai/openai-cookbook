# Tools Directory Cleanup and Organization

**Date:** 2025-01-27  
**Last Updated:** 2026-01-28  
**Status:** 📋 Historical document – cleanup completed

> **Note:** This document described a planned cleanup. The referenced scripts (`hubspot_hybrid_identifier_implementation.py`, `hubspot_list_contactability_analysis.py`, `hubspot_lists_api_working.py`, `make_accountant_primary.py`, `switch_primary_company.py`, `update_companies_via_deals.py`, etc.) have been **removed** in subsequent cleanups. This doc is retained for historical reference only.

---

## 📋 Files Found in `tools/` Root (Historical)

### HubSpot Data Management Scripts (9 files)

These scripts should be moved to `tools/scripts/hubspot/data_management/`:

| File | Purpose | Status |
|------|---------|--------|
| `hubspot_hybrid_identifier_implementation.py` | Company identification using CUIT and normalized names | ✅ Unique |
| `hubspot_list_contactability_analysis.py` | Contactability analysis for HubSpot lists | ✅ Unique |
| `hubspot_lists_api_working.py` | Lists API implementation and testing | ✅ Unique |
| `make_accountant_primary.py` | Makes accountant primary for specific deal (GORUKA) | ⚠️ Specific use case |
| `switch_primary_company.py` | Generic primary company switcher for deals | ✅ Generic utility |
| `update_companies_via_deals.py` | Updates companies with CUITs via deal associations | ✅ Unique |
| `preview_referencia_updates.py` | Preview updates for Referencia Empresa Administrada deals | ⚠️ Related to switch_primary |
| `update_referencia_empresa_primaries.py` | Update primary company for Referencia deals | ⚠️ Related to switch_primary |
| `update_single_deal.py` | Update single deal's primary company (GLAM FILMS example) | ⚠️ Specific use case |

**Analysis:**
- `switch_primary_company.py` is the **generic utility** - should be kept
- `preview_referencia_updates.py`, `update_referencia_empresa_primaries.py`, `update_single_deal.py` are **specific implementations** using similar logic
- `make_accountant_primary.py` is a **one-off script** for a specific deal

**Recommendation:**
- **KEEP:** `switch_primary_company.py` (generic utility)
- **ARCHIVE/CONSOLIDATE:** `preview_referencia_updates.py`, `update_referencia_empresa_primaries.py`, `update_single_deal.py`, `make_accountant_primary.py` (specific use cases, can reference generic utility)

---

### Test Files (7 files)

These should be moved to `tools/tests/hubspot/`:

| File | Purpose | Category |
|------|---------|----------|
| `test_associations.py` | Test HubSpot associations API | HubSpot |
| `test_deal_structure.py` | Test deal structure | HubSpot |
| `test_databases.py` | Test database connections | Database |
| `test_db_names.py` | Test database names | Database |
| `test_empresa_table.py` | Test empresa table | Database |
| `test_lead_source_values.py` | Test lead source values | HubSpot |
| `test_raw_connection.py` | Test raw database connection | Database |

**Recommendation:**
- Move HubSpot tests → `tools/tests/hubspot/`
- Move Database tests → `tools/tests/database/`

---

### Database Setup (1 file)

| File | Purpose | Location |
|------|---------|----------|
| `setup_database.py` | Database setup and testing script | Should be in `tools/database/` or kept in root as entry point |

---

## 🎯 Recommended Actions

### Step 1: Create Directory Structure

```bash
mkdir -p tools/scripts/hubspot/data_management
mkdir -p tools/tests/hubspot
mkdir -p tools/tests/database
mkdir -p tools/scripts/hubspot/archive  # For specific use case scripts
```

### Step 2: Move HubSpot Data Management Scripts

```bash
# Move unique utilities
mv tools/hubspot_hybrid_identifier_implementation.py tools/scripts/hubspot/data_management/
mv tools/hubspot_list_contactability_analysis.py tools/scripts/hubspot/data_management/
mv tools/hubspot_lists_api_working.py tools/scripts/hubspot/data_management/
mv tools/switch_primary_company.py tools/scripts/hubspot/data_management/
mv tools/update_companies_via_deals.py tools/scripts/hubspot/data_management/

# Move specific use case scripts to archive
mv tools/make_accountant_primary.py tools/scripts/hubspot/archive/
mv tools/preview_referencia_updates.py tools/scripts/hubspot/archive/
mv tools/update_referencia_empresa_primaries.py tools/scripts/hubspot/archive/
mv tools/update_single_deal.py tools/scripts/hubspot/archive/
```

### Step 3: Move Test Files

```bash
# Move HubSpot tests
mv tools/test_associations.py tools/tests/hubspot/
mv tools/test_deal_structure.py tools/tests/hubspot/
mv tools/test_lead_source_values.py tools/tests/hubspot/

# Move Database tests
mv tools/test_databases.py tools/tests/database/
mv tools/test_db_names.py tools/tests/database/
mv tools/test_empresa_table.py tools/tests/database/
mv tools/test_raw_connection.py tools/tests/database/
```

### Step 4: Move Database Setup

```bash
# Option 1: Keep in root as entry point (recommended)
# Option 2: Move to database directory
mv tools/setup_database.py tools/database/  # If preferred
```

---

## 📝 Detailed File Analysis

### HubSpot Data Management Scripts

#### 1. `hubspot_hybrid_identifier_implementation.py` ✅ **KEEP - Unique**
**Purpose:** Company identification system using both CUIT and normalized names  
**Key Features:**
- Normalizes company names for consistent matching
- Cleans CUIT values
- Hybrid identification approach
- Uses `hubspot_api` package

**Category:** Company Identification Utility

---

#### 2. `hubspot_list_contactability_analysis.py` ✅ **KEEP - Unique**
**Purpose:** Detailed contactability analysis for HubSpot lists  
**Key Features:**
- Analyzes list contactability
- Company search functionality
- Uses HubSpot Lists API

**Category:** List Analysis

---

#### 3. `hubspot_lists_api_working.py` ✅ **KEEP - Unique**
**Purpose:** Working HubSpot Lists API implementation  
**Key Features:**
- Direct REST API calls (beyond MCP tools)
- List details retrieval
- List membership operations
- Comprehensive API client

**Category:** Lists API Utility

---

#### 4. `switch_primary_company.py` ✅ **KEEP - Generic Utility**
**Purpose:** Generic primary company switcher for deals  
**Key Features:**
- Switches primary company while preserving associations
- Uses PUT instead of DELETE
- Generic, reusable function
- Command-line interface

**Category:** Deal Association Management

---

#### 5. `update_companies_via_deals.py` ✅ **KEEP - Unique**
**Purpose:** Updates companies with CUITs via deal associations  
**Key Features:**
- Gets July 2025 closed won deals
- Finds associated companies
- Updates missing CUITs from Colppy database
- Integrates HubSpot API with Colppy database

**Category:** Data Enrichment

---

#### 6. `make_accountant_primary.py` ⚠️ **ARCHIVE - Specific Use Case**
**Purpose:** Makes accountant primary for GORUKA deal (one-off script)  
**Analysis:** Specific implementation that could use `switch_primary_company.py`

**Recommendation:** Archive, reference generic utility if needed again

---

#### 7. `preview_referencia_updates.py` ⚠️ **ARCHIVE - Specific Use Case**
**Purpose:** Preview updates for Referencia Empresa Administrada deals  
**Analysis:** Specific use case that previews changes before applying

**Recommendation:** Archive, logic could be extracted to generic utility

---

#### 8. `update_referencia_empresa_primaries.py` ⚠️ **ARCHIVE - Specific Use Case**
**Purpose:** Update primary company for Referencia deals  
**Analysis:** Specific batch processing script for Referencia deals

**Recommendation:** Archive, use generic utility for similar operations

---

#### 9. `update_single_deal.py` ⚠️ **ARCHIVE - Specific Use Case**
**Purpose:** Update single deal's primary company (GLAM FILMS example)  
**Analysis:** Specific example/one-off script

**Recommendation:** Archive, use generic utility for similar operations

---

### Test Files Analysis

#### HubSpot Tests
- `test_associations.py` - Tests associations API endpoints
- `test_deal_structure.py` - Tests deal data structure
- `test_lead_source_values.py` - Tests lead source property values

#### Database Tests
- `test_databases.py` - Tests database connectivity
- `test_db_names.py` - Tests database naming conventions
- `test_empresa_table.py` - Tests empresa table structure
- `test_raw_connection.py` - Tests raw database connections

---

## 📊 Summary

| Category | Count | Action |
|----------|-------|--------|
| **HubSpot Data Management (Unique)** | 5 | Move to `tools/scripts/hubspot/data_management/` |
| **HubSpot Data Management (Archive)** | 4 | Move to `tools/scripts/hubspot/archive/` |
| **HubSpot Tests** | 3 | Move to `tools/tests/hubspot/` |
| **Database Tests** | 4 | Move to `tools/tests/database/` |
| **Database Setup** | 1 | Keep in root or move to `tools/database/` |

**Total Files to Organize:** 17

---

## ✅ Verification Checklist

After migration:
- [ ] All HubSpot data management scripts moved
- [ ] Test files organized by category
- [ ] Archive directory created for specific use cases
- [ ] Documentation updated with new paths
- [ ] No broken imports or references
- [ ] README created for data_management directory

---

**End of Analysis**

