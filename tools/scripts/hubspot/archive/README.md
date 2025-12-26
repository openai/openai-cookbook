# HubSpot Scripts Archive

**Purpose:** Archive directory for specific use case scripts and one-off implementations

---

## 📁 Files in This Directory

These scripts are archived because they represent specific use cases or one-off implementations. The generic utilities are in `../data_management/`.

### Specific Use Case Scripts

#### `make_accountant_primary.py`
**Purpose:** Makes accountant primary for GORUKA deal (one-off script)  
**Status:** Archived - Specific implementation  
**Note:** Generic functionality available in `../data_management/switch_primary_company.py`

---

#### `preview_referencia_updates.py`
**Purpose:** Preview updates for Referencia Empresa Administrada deals  
**Status:** Archived - Specific use case  
**Note:** Shows current state vs proposed changes without making modifications

---

#### `update_referencia_empresa_primaries.py`
**Purpose:** Update primary company for Referencia deals (batch processing)  
**Status:** Archived - Specific batch processing script  
**Note:** Processes deals one by one with confirmation for testing

---

#### `update_single_deal.py`
**Purpose:** Update single deal's primary company (GLAM FILMS example)  
**Status:** Archived - Specific example/one-off script  
**Note:** Example implementation for updating a single deal

---

## 🔄 Using Generic Utilities Instead

For similar operations, use the generic utilities in `../data_management/`:
- **Primary Company Switching:** Use `switch_primary_company.py`
- **Company Identification:** Use `hubspot_hybrid_identifier_implementation.py`

---

## 📝 Notes

- These scripts are kept for reference
- Logic from these scripts can be extracted to generic utilities if needed
- See `../data_management/README.md` for reusable utilities

---

**Last Updated:** 2025-01-27

