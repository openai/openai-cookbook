# 🎯 CLAUDE CONTEXT MASTER DOCUMENT
## Complete Business & Technical Context for Colppy.com

**Last Updated**: 2025-10-06
**Purpose**: Permanent context for all Claude AI sessions
**Status**: ✅ Complete - Ready for Claude Desktop & Cursor Integration

---

## 🏢 BUSINESS CONTEXT

### Company Overview: Colppy.com
- **Industry**: SaaS B2B Cloud Accounting Software for SMBs
- **Market**: Argentina (exclusively)
- **Customer Segment**: SMBs (Small and Medium Businesses)
- **Business Model**: Product-Led Growth (PLG) with 7-day free trial
- **Holding Company**: SUMA SaaS (Riverwood Capital as main investor)
- **Sister Companies**: Nubox (Chile), Bind ERP (Mexico)

### CEO & Leadership
- **CEO**: Juan Ignacio Onetto (jonetto@colppy.com) - Founder, re-hired to accelerate growth
- **Focus Areas**: Demand generation, product, sales, customer success
- **Strategic Priorities**: Product-Led Growth, data-driven decisions, team culture
- **Management Philosophy**: People love to come to work, learn from co-workers, work as team

### Key Distribution Channels
1. **Accountant Channel** (Primary)
   - Accountants from SMBs are main acquisition channel
   - Accountants can have multiple client companies
   - Track accountant referrals and associations in HubSpot

2. **Tech Integrators** (Secondary)
   - Technology integration partners
   - Help reach more SMBs

3. **Direct/Self-Service** (Product-Led Growth)
   - 7-day free trial
   - Multiple subscription plans based on invoice count and features

---

## 📊 KEY BUSINESS METRICS & DEFINITIONS

### Product-Led Growth Metrics
1. **Legal Entity ID** = **One Paid Account**
   - Each company (legal entity) = 1 subscription

2. **Trial Conversion Metrics**:
   - **PQL (Product Qualified Lead)**: Contacts who performed "key event" during trial
   - **Key Event Field**: `activo` (boolean) in HubSpot Contacts
   - **Key Event Date**: `fecha_activo` in HubSpot Contacts
   - **PQL Rate**: PQLs / All Contacts Created in Month

3. **Conversion Funnel**:
   - Contact → Lead → Deal → Closed Won
   - Track: Contact-to-Lead, Lead-to-Deal, Deal Win Rate

### Subscription Plans
- **Plan Tiers**: Based on invoice count and features
- **Billing**: Monthly/Annual recurring
- **Products**: Colppy (Financial Management) vs Sueldos (Payroll Processing)

---

## 🔧 TECHNICAL INTEGRATIONS

### 1. HubSpot CRM (Complete Field Mapping)

#### **Companies Object**
| Field | Internal Property | Purpose |
|-------|------------------|---------|
| CUIT | `cuit` | Tax ID (Argentina) |
| Colppy ID | `colppy_id` | System integration ID |
| ID Empresa | `id_empresa` | **Mixpanel join key** |
| Company Type | `type` | Classification (12 types including "Cuenta Contador") |
| First Deal Won Date | `first_deal_closed_won_date` | Date of first won deal |
| Company Churn Date | `company_churn_date` | Churn detection |

#### **Deals Object**
| Field | Internal Property | Purpose |
|-------|------------------|---------|
| Deal Name | `dealname` | Identification |
| Amount | `amount` | Deal value |
| Close Date | `closedate` | Expected/actual close |
| Deal Stage | `dealstage` | Pipeline stage |
| Nombre del Plan | `nombre_del_plan_del_negocio` | Subscription plan |
| Accountant Channel Involved | `accountant_channel_involucrado_en_la_venta` | Team involvement tracking |

#### **Contacts Object**
| Field | Internal Property | Purpose |
|-------|------------------|---------|
| Email | `email` | Primary identifier |
| Lifecycle Stage | `lifecyclestage` | Lead/Customer stage |
| Hizo evento clave | `activo` | **PQL flag** (boolean) |
| Fecha evento clave | `fecha_activo` | **PQL date** |
| Es Contador | `es_contador` | Accountant flag |
| Es Administrador | `es_administrador` | Admin flag |

#### **Line Items Object** (Subscription Revenue)
| Field | Internal Property | Purpose |
|-------|------------------|---------|
| Monthly Recurring Revenue | `hs_mrr` | MRR tracking |
| Annual Recurring Revenue | `hs_arr` | ARR tracking |
| Billing Start Date | `hs_recurring_billing_start_date` | Subscription start |
| Billing End Date | `hs_recurring_billing_end_date` | Subscription end |

#### **Products Object**
| Field | Internal Property | Purpose |
|-------|------------------|---------|
| Product Family | `product_family` | Colppy (19 products) vs Sueldos (32 products) |

#### **CRITICAL HubSpot API Rules**
1. **Field Clearing**: Use empty string `""` NOT `null` to clear fields
2. **Team Detection**: Use Owners API (`/crm/v3/owners/{ownerId}`) NOT Users API
3. **Collaborators**: Use deal property `hs_all_collaborator_owner_ids` (semicolon-separated)
4. **Pagination**: Always use `after` parameter for complete data retrieval
5. **Association Types**: PRIMARY = main company deal, UNLABELED = secondary associations

---

### 2. Mixpanel Product Analytics

#### **Project Details**
- **Project ID**: 2201475 (Production)
- **Total Events**: 350 (223 documented = 64%)
- **Total User Properties**: 65 (100% documented)
- **Integration Key**: `idEmpresa` = Company ID (joins with HubSpot `id_empresa`)

#### **Key Company Identifiers**
- `company_id`
- `idEmpresa` (primary for JQL queries)
- `$groups.Company`
- `company` (string or array)

#### **Key User Identifiers**
- `$user_id`
- `Email` / `$email` / `email`
- `idUsuario`
- `usuario`

#### **Event Categories** (223 documented)
1. **System Events** ($-prefixed): 7 events - EXCLUDE from analytics
2. **User Authentication**: 3 events (Login, Registro, Validó email)
3. **Company Management**: 8 events (Crear Empresa, Cambió de empresa)
4. **Financial Operations**: 25+ events (Generó comprobante, Liquidar sueldo)
5. **Mobile App Events**: 20+ events (app login, app generó comprobante)
6. **UI/UX Events**: 30+ events (Click en elegir plan, Abrió el módulo)
7. **Reporting**: 15+ events (Descargó el balance, Genera reporte)
8. **Import/Export**: 10+ events (Subió archivo, Finalizó importación)

#### **Critical Mixpanel Rules**
1. **Exclude Internal Events**: Filter out events starting with `$` (e.g., `$identify`, `$mp_click`)
2. **Company Association**: Use Events() queries NOT People() queries for company data
3. **Rate Limiting**: 60 queries per hour per project
4. **JQL Best Practices**: Check multiple property locations with fallbacks
5. **Data Model**: User-company associations stored in EVENT properties, not user profiles

---

### 3. Intercom Customer Support
- **MCP Integration**: Remote access via `mcp.intercom.com/mcp`
- **Data Volume**: 456.9 MB conversation exports
- **Key Metrics**: CSAT, response times, team performance
- **Integration**: Connect NPS with Mixpanel for unified customer view

---

### 4. Google Ads & Meta Ads
- **Google Ads**: Campaign performance, cost analysis
- **Meta Ads**: Facebook/Instagram campaigns, creative performance
- **Attribution**: UTM parameters tracked in HubSpot (8 fields verified)

---

## 🔄 AUTOMATED WORKFLOWS

### HubSpot Custom Code Workflows

#### 1. First Deal Won Date Calculator
- **File**: `hubspot_custom_code_latest.py`
- **Version**: 1.12.44
- **Trigger**: Company updates
- **Logic**: Calculates earliest won date from PRIMARY deals only
- **Auto-fix**: Adds PRIMARY association if missing for single-company deals
- **Churn Detection**: Updates `company_churn_date` when all primary deals lost

#### 2. Accountant Channel Deal Workflow
- **File**: `hubspot_accountant_channel_deal_workflow.py`
- **Version**: 1.0.0
- **Trigger**: Deal updates
- **Logic**: Detects if deal owner OR any collaborator belongs to "Accountant Channel" team
- **Field Updated**: `accountant_channel_involucrado_en_la_venta` (true/false)
- **Use Case**: Revenue attribution, channel performance tracking

---

## 📐 ARGENTINA-SPECIFIC STANDARDS

### Number Formatting
- **Decimal Separator**: Comma (`,`) → `1.234,56`
- **Thousand Separator**: Period (`.`) → `$1.234.567,89`
- **Currency Symbol**: `$` (Argentine Peso)
- **Measurement System**: Metric (SI units)

### Formula Separators
- **Excel/Google Sheets**: Use semicolon `;` as parameter separator
- **Example**: `=SUM(A1;A10)` NOT `=SUM(A1,A10)`

### Date Formats
- **Standard**: ISO 8601 (YYYY-MM-DD)
- **Display**: Local preference varies

---

## 🎯 COMMON ANALYSIS PATTERNS

### September 2025 Conversion Analysis (Example)
**Results**:
- 884 contacts created
- 638 leads (72.2% contact-to-lead rate)
- 110 deals created (17.24% lead-to-deal rate)
- 43 closed won (6.74% lead-to-closed-won rate)
- Deal win rate: 55.84% (strong performance)

### Monthly PQL Analysis Pattern
```bash
# Current month
./tools/scripts/run_monthly_pql.sh

# Specific month
./tools/scripts/run_monthly_pql.sh 2025-09

# Multi-month comparison
./tools/scripts/run_monthly_pql.sh last4
```

**Output**: CSV/JSON with PQL Rate = PQLs / All Contacts Created

---

## 🚨 CRITICAL INSTRUCTIONS FOR CLAUDE

### When Analyzing Data
1. **Always exclude Mixpanel internal events** (starting with `$`)
2. **Use `id_empresa` / `idEmpresa`** as join key between HubSpot and Mixpanel
3. **Check multiple property locations** with fallbacks (Mixpanel data quality)
4. **Use Argentina number formatting** in all reports (comma for decimal)
5. **State row count and character count** before analyzing spreadsheets

### When Writing Code
1. **Never hard-code dates** - use variables/placeholders
2. **Respect existing code structure** - don't create new folders without request
3. **Produce functions, not scripts** - wrap routines in callable functions
4. **Centralize shared utilities** - use existing utils/services folders
5. **Max 300 lines per file** - refactor when approaching limit
6. **Check Mixpanel Lexicon** before adding tracking (avoid duplicates)

### When Using HubSpot API
1. **Clear fields with empty string** (`""`) NOT `null`
2. **Use Owners API** for team information (NOT Users API)
3. **Check `hs_all_collaborator_owner_ids`** for deal collaborators
4. **Always paginate** using `after` parameter for complete data
5. **Verify field names** - map UI names to internal properties

### When Reporting
1. **Include metadata**: date range, data source, record count, filters
2. **Use Argentina formatting**: `$1.234,56` for currency
3. **Provide executive summary** with TL;DR bullets
4. **Add visual emphasis**: headers, bold, bullet lists
5. **No unnecessary disclaimers** unless required by unverified facts rule

---

## 🎓 LEARNING RESOURCES

### Internal Documentation
- `tools/docs/README_HUBSPOT_CONFIGURATION.md` - Complete HubSpot field mapping
- `tools/docs/README_MIXPANEL_API.md` - Mixpanel JQL query patterns
- `tools/docs/MIXPANEL_EVENTS_CONFIG.md` - All 223 documented events
- `tools/docs/MIXPANEL_USER_PROPERTIES_CONFIG.md` - All 65 user properties
- `tools/docs/README_HUBSPOT_PAGINATION_STANDARDS.md` - Complete data retrieval
- `tools/docs/README_INTERCOM_CONSOLIDATED.md` - Intercom MCP integration

### External References
- [Mixpanel JQL Reference](https://developer.mixpanel.com/reference/query-jql)
- [HubSpot API Docs](https://developers.hubspot.com/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)

---

## 🔐 MCP SERVER CONFIGURATION

### Claude Desktop Config Location
`~/Library/Application Support/Claude/claude_desktop_config.json`

### Configured MCP Servers (8 total)
1. **hubspot** - HubSpot CRM access
2. **mixpanel** - Product analytics (remote via mcp.mixpanel.com)
3. **meta-ads** - Meta/Facebook Ads (local Python)
4. **google-ads** - Google Ads (local Python)
5. **intercom** - Customer messaging (remote via mcp.intercom.com)
6. **atlassian-mcp-server** - Confluence wiki
7. **fellow-meeting** - Meeting notes
8. **GitKraken** - Git operations

### Environment Variables Required
- `HUBSPOT_API_KEY` / `ColppyCRMAutomations`
- `MIXPANEL_PROJECT_ID` / `MIXPANEL_API_SECRET`
- `INTERCOM_ACCESS_TOKEN`
- `META_ADS_*` (6 variables)
- `GOOGLE_ADS_*` (6 variables)
- `CONFLUENCE_*` (3 variables)

---

## 📊 KEY DASHBOARDS & REPORTS

### CEO Daily Brief Components
1. **Sales Pipeline**: New leads, deals, win rate
2. **Product Usage**: Top events, active companies, engagement
3. **Customer Success**: NPS, CSAT, churn risk
4. **Marketing**: Campaign performance, attribution
5. **Team Performance**: Response times, resolution rates

### Weekly Reports
1. **Operational Intelligence**: KPIs, bottlenecks, team productivity
2. **Growth Opportunities**: Expansion, upsell, channel performance
3. **Customer Health**: At-risk accounts, success stories

### Monthly Analysis
1. **PQL Analysis**: Trial conversion, key event completion
2. **Revenue Metrics**: MRR, ARR, churn, expansion
3. **Channel Performance**: Accountant referrals, integration partners

---

## 🚀 NEXT STEPS FOR IMPLEMENTATION

### Phase 1: Data Validation (Week 1)
1. Test all MCP server connections
2. Verify field mappings in HubSpot
3. Validate Mixpanel event tracking
4. Confirm Argentina formatting standards

### Phase 2: Core Analytics (Week 2-3)
1. Build conversion funnel analysis
2. Implement PQL tracking dashboard
3. Create accountant channel attribution
4. Setup automated daily briefings

### Phase 3: Advanced Intelligence (Week 4-6)
1. Predictive churn modeling
2. Expansion opportunity detection
3. Customer health scoring
4. Strategic recommendation engine

---

**Remember**: This context should be referenced at the start of EVERY Claude session to ensure consistent, accurate, and business-relevant analysis.

**Last Updated**: 2025-10-06 by Claude Code
**Version**: 1.0.0
**Status**: ✅ Production Ready

