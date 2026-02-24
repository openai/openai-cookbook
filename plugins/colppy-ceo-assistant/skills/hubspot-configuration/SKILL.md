---
name: hubspot-configuration
description: Colppy's complete HubSpot CRM configuration including field mappings, Lead object definitions, deal associations, API patterns, teams/owners, UTM tracking, and critical rules. Apply when working with HubSpot data, creating queries, analyzing CRM records, or debugging data issues.
---

# HubSpot Configuration — Colppy

Complete reference for Colppy's HubSpot CRM setup. Use this when querying, analyzing, or modifying HubSpot data.

---

## What is a "Lead" in Colppy

**CRITICAL**: A Lead in Colppy is NOT just a contact with `lifecyclestage = 'lead'`.

- A "Lead" = **Contact with an associated Lead object** (separate HubSpot object)
- Requires a Lead object to be created AND associated with the contact
- A contact can have `lifecyclestage = 'lead'` but NOT be a Lead if no Lead object exists

**How to check**: Use `hubspot-list-associations` (contact → leads). If results exist → IS a Lead.

**Lead creation methods**:
1. **Workflow (automatic)**: HubSpot workflow creates Lead when contact is created via API from Colppy platform (trial signup). Source: `AUTOMATION_PLATFORM`
2. **Manual**: Salesperson creates Lead. Source: `CRM_UI`

---

## API Key Configuration

Scripts check these environment variables in order:
1. `HUBSPOT_API_KEY` — Primary
2. `COLPPY_CRM_AUTOMATIONS` — Alternative
3. `ColppyCRMAutomations` — Legacy

---

## Critical API Rules

### Clearing Fields
**ALWAYS use empty string `""` to clear HubSpot fields, NEVER use `null`**

### Teams and Owners
**ALWAYS use Owners API** (`/crm/v3/owners/{ownerId}`) for team information.
- **NEVER use** Users API (`/settings/v3/users/{userId}`) — returns 404 or missing team data
- Teams are in the `teams` array with `name` and `primary` properties
- Check `team.name === 'Accountant Channel'` for accountant channel team

### Deal Collaborators
**ALWAYS use** `hs_all_collaborator_owner_ids` deal property.
- **NEVER use** contact associations for collaborators
- Split by `;` to get individual owner IDs

---

## Deal-Company Associations

| TypeId | Label | Usage |
|--------|-------|-------|
| **5** | PRIMARY | Primary company → defines ICP (via `type` field) |
| **8** | Estudio Contable | Accountant referral channel. NOT billing |
| 341 | Default | Standard association |

---

## Key Company Fields

| Internal Name | UI Label | Usage |
|--------------|----------|-------|
| `type` | Type | **ICP Classification**: Cuenta Contador, Cuenta Pyme, etc. |
| `tipo_icp_contador` | Calculated field | NPS/enrichment only (Hibrido, Operador, Asesor). NOT for ICP billing |
| `industria` | Sector | Enrichment, inference, reporting |
| `domain` | Website domain | Enrichment, identification |
| `cuit` | CUIT | Argentine tax ID |
| `name` | Company name | Identification, reports |

---

## Key Deal Fields

| Internal Name | Usage |
|--------------|-------|
| `primary_company_type` | Synced from primary company `type`. Used for ICP classification without API call |
| `dealstage` | Deal pipeline stage |
| `closedate` | When deal was closed |
| `createdate` | When deal was created |
| `amount` | Deal amount |
| `id_empresa` | Colppy empresa ID (links to Colppy database) |
| `nombre_del_plan_del_negocio` | Plan name (NOT used for ICP) |
| `hubspot_owner_id` | Deal owner |
| `hs_all_collaborator_owner_ids` | Semicolon-separated collaborator owner IDs |

---

## Key Contact Fields

| Internal Name | Usage |
|--------------|-------|
| `lifecyclestage` | Lifecycle stage (lead, subscriber, opportunity, customer, etc.) |
| `hs_lead_status` | Lead status |
| `hs_v2_date_entered_opportunity` | When contact entered Opportunity stage (= SQL) |
| `rol_wizard` | Role from signup wizard. Determines MQL channel (accountant vs SMB) |
| `hubspot_score` | Contact score |
| `createdate` | Contact creation date |

---

## UTM Marketing Fields (Verified)

8 fields: `utm_campaign`, `utm_source`, `utm_medium`, `utm_term`, `utm_content`, `initial_utm_campaign`, `initial_utm_source`, `initial_utm_medium`

---

## Company Type Values (12 types)

Relevant for ICP: `Cuenta Contador`, `Cuenta Contador y Reseller`, `Contador Robado`, `Cuenta Pyme`
Others: Alianza, Integracion, Reseller, etc.

---

## Output Standards

- All tabular data in **Markdown tables** (not ASCII art)
- CSV exports to `tools/outputs/`
- API-based queries are the **source of truth** (CSV exports may exclude edge cases)

---

## Related Skills

- **icp-classification** — Detailed ICP rules
- **funnel-analysis** — Funnel stage definitions
- **hubspot-api-patterns** — API package usage
