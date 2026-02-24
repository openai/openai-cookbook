# Post-CUIT Enrichment Pipeline — Design Document

**Status**: Design (Feb 2026)
**Owner**: RevOps / Growth Engineering
**Scope**: Lead qualification, onboarding enrichment, product-led demand generation

---

## 1. Problem Statement

AdWords lead quality is declining. The current acquisition funnel:

```
AdWords Ad → Landing Page → Trial Signup (7 days) → PQL? → Paid
```

Key stats:
- PQLs convert at **37.8%** vs **7.4%** for non-PQLs
- The onboarding wizard collects CUIT, company name, address, condición IVA, industry, role
- **Step 2 of the wizard (role/industry) is fully skippable** — many users click "Omitir"
- CUIT is already mandatory in Step 1, but the data behind it goes mostly unused

**Opportunity**: A single CUIT unlocks 6+ qualification signals from public sources, without asking the user any additional questions.

---

## 2. Validated Findings

Analysis ran on **2,360 companies** × **2,961 deals** joined against RNS (3M records):

| Signal | Finding | Impact |
|--------|---------|--------|
| CUIT → RNS match rate | **83.2%** | High coverage for enrichment |
| Business age → win rate | **5.1pp spread** (89.8% for 0-2y → 94.9% for 50y+) | Age is a real conversion predictor |
| ICP split | PyME: steady improvement with age. Contador: non-linear (2-5y danger zone at 79.9%) | Different scoring models per ICP |
| Tipo societario | SA: 93.7%, SRL: 92.4%, Asociación Civil: 98.2%, Ley 19550 Sec IV: 80.9% | Legal structure predicts quality |
| Activity sector | "contabilidad" churns most, "informática" converts best | Activity codes inform routing |

**Source**: `tools/scripts/analyze_business_age_conversion.py` → `tools/data/business_age_analysis.csv`

---

## 3. Architecture Overview

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                    ENRICHMENT PIPELINE                       │
                    │                                                              │
 User enters       │   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐ │
 CUIT in wizard ──►│   │ AFIP    │    │  RNS    │    │  ARCA   │    │  Bank    │ │
                    │   │ API     │    │ Dataset │    │ Portal  │    │ Scraper  │ │
                    │   │(real-   │    │(batch   │    │(Playw-  │    │(Playw-   │ │
                    │   │ time)   │    │ lookup) │    │ right)  │    │ right)   │ │
                    │   └────┬────┘    └────┬────┘    └────┬────┘    └────┬─────┘ │
                    │        │              │              │              │        │
                    │        ▼              ▼              ▼              ▼        │
                    │   ┌────────────────────────────────────────────────────┐     │
                    │   │              ENRICHMENT AGGREGATOR                 │     │
                    │   │  Merges signals → computes score → routes lead    │     │
                    │   └─────────┬──────────────────────────┬──────────────┘     │
                    └─────────────│──────────────────────────│────────────────────┘
                                  │                          │
                         ┌────────▼───────┐         ┌───────▼────────┐
                         │    HubSpot     │         │   Colppy App   │
                         │  (CRM write)   │         │  (wizard UX)   │
                         └────────────────┘         └────────────────┘
```

### Data Source Details

| Source | Method | Latency | Signals | Existing Code |
|--------|--------|---------|---------|---------------|
| **AFIP API** | REST via TusFacturas.app | ~1s | condición IVA, actividades + `periodo`, estado | `tools/scripts/afip_cuit_lookup.py` |
| **RNS Dataset** | Local CSV lookup (3M rows) | <100ms | fecha_contrato_social, tipo_societario, actividad, provincia | `tools/scripts/rns_dataset_lookup.py` |
| **ARCA Portal** | Playwright browser automation | ~15s | DFE notifications, Mis Comprobantes, retenciones | `arca-prototype/backend/services/` |
| **Bank (Galicia)** | Playwright browser automation | ~20s | Account balances, 6mo transaction history | `arca-prototype/backend/services/banco_galicia_scraper.py` |

---

## 4. Enrichment Flow — Step by Step

### Phase 1: Instant Enrichment (on CUIT entry, <2s)

Triggered the moment the user types a valid CUIT in the wizard.

```
CUIT entered
    ├── AFIP API call (1s) ──► condición IVA, actividades[], estado
    │                          Each actividad has `periodo` (registration date)
    │
    └── RNS local lookup (<100ms) ──► fecha_contrato_social (company age),
                                      tipo_societario, actividad_descripcion,
                                      provincia
```

**Outputs**:
- Company age (years since incorporation)
- Primary activity code + description
- Legal structure (SA, SRL, SAS, etc.)
- Tax condition (Responsable Inscripto, Monotributo, Exento)
- Province
- AFIP activity registration recency (`periodo`)

**Action**: Auto-fill wizard fields + store raw signals for scoring.

### Phase 2: Accountant Detection (immediate, after Phase 1)

The key ICP split is **Cuenta Contador** vs **Cuenta Pyme**. AFIP activity code alone is insufficient because:
- An accountant firm may sign up to use Colppy for *their clients* (Cuenta Contador)
- A company whose activity is "contabilidad" may sign up for *their own accounting* (Cuenta Pyme)
- The wizard's Step 2 role selector ("Contador", "Empresa") is skippable

**Proposed logic**:

```python
def detect_accountant(afip_data, rns_data):
    """Determine if we should route to Cuenta Contador or Pyme."""
    activity_codes = [a.id for a in afip_data.actividades]
    activity_descs = [a.descripcion.lower() for a in afip_data.actividades]

    # Strong accountant signals
    is_accounting_activity = any(
        "contab" in d or "auditor" in d or "asesor" in d
        for d in activity_descs
    )
    # AFIP activity codes for accounting/professional services
    is_accounting_code = any(c.startswith("69") for c in activity_codes)  # CIIU Rev 4: 69xx

    if is_accounting_activity or is_accounting_code:
        # Don't auto-classify — ASK the user
        return "needs_confirmation"

    return "pyme"  # Default to Cuenta Pyme
```

**UX for confirmation**: Instead of the skippable Step 2, show a targeted question:
> "Vemos que tu actividad es servicios contables. ¿Estás registrándote para gestionar la contabilidad de tus clientes?"
> - [Sí, soy contador/a] → route to Cuenta Contador
> - [No, es para mi empresa] → route to Cuenta Pyme

This replaces the generic role dropdown with a contextual, unskippable fork.

### Phase 3: ARCA Deep Enrichment (async, post-signup)

Not blocking onboarding. Runs in background after the user completes the wizard.

```
Background worker triggers:
    ├── DFE Notifications ──► Communication history with ARCA
    ├── Mis Comprobantes ──► Recent facturación volume (emitidos + recibidos)
    └── Retenciones ──► Tax withholding patterns
```

**Signals extracted**:
- **Facturación volume**: How many comprobantes emitidos in last 3 months → business activity proxy
- **Notification count**: Active communication with ARCA → compliance signal
- **Retenciones type/amount**: Indicates business scale and formality

**Existing code**: All three are already implemented in the ARCA prototype:
- `arca-prototype/backend/services/notifications_api.py`
- `arca-prototype/backend/services/comprobantes_api.py`
- `arca-prototype/backend/services/retenciones_api.py`

### Phase 4: Bank Statement Integration (opt-in, post-trial-start)

User-initiated during trial. Presented as a value-add feature, not a qualification gate.

```
Trial user clicks "Conectar mi banco"
    └── Playwright scraper (Galicia, others TBD)
        ├── Login with user-provided credentials
        ├── Navigate to account detail
        ├── Extract 6mo transaction history
        └── Save structured CSV + return JSON
```

**Value proposition to user**: "Importá tus movimientos bancarios y conciliá automáticamente con tu facturación."

**Enrichment signals (for us)**:
- Transaction volume → business activity level
- Average balance → financial health proxy
- Recurring payments → operational maturity
- Payment recipients → supplier network complexity

**Existing code**: `arca-prototype/backend/services/banco_galicia_scraper.py`
- DOM-based extraction: `div.table-row.cursor-p` elements
- JS evaluate for parsing: date/description/amount from nested divs
- CSV export with Argentine formatting

---

## 5. Lead Scoring Model

### Score Components

| Signal | Weight | Score Range | Source |
|--------|--------|-------------|--------|
| Business age | 20% | 0-100 (0-2y=40, 2-5y=60, 5-10y=75, 10-20y=85, 20y+=95) | RNS |
| Legal structure | 15% | SA=90, SRL=85, SAS=70, Monotributo=50 | RNS |
| Activity sector | 15% | Mapped per sector (informática=90, comercio=75, contabilidad=60) | AFIP/RNS |
| Tax condition | 10% | RI=90, Monotributo=50, Exento=40 | AFIP |
| Facturación volume | 20% | Based on comprobantes count (0=20, 1-10=50, 10-50=75, 50+=95) | ARCA |
| Province | 5% | CABA/GBA=80, Córdoba/Santa Fe=75, other=65 | AFIP/RNS |
| AFIP activity recency | 5% | Based on `periodo` field freshness | AFIP |
| Bank data (if available) | 10% bonus | Transaction volume + balance signals | Bank scraper |

### ICP-Specific Adjustments

**Cuenta Pyme**: Standard scoring as above.

**Cuenta Contador**: Different weights because the accountant is buying for N clients:
- Business age matters less (young firms can be great accountant clients)
- Activity sector: "contabilidad" is EXPECTED, not a red flag
- **New signal**: Number of CUITs they manage (from ARCA "representado" data)
- **Danger zone**: 2-5 year old accounting firms (79.9% WR) → flag for extra nurturing

---

## 6. Implementation Plan

### Phase A: CUIT Intelligence Layer (Week 1-2)

**Goal**: Enrich every trial signup with AFIP + RNS data, write scores to HubSpot.

1. **Build enrichment API endpoint** in `arca-prototype/backend/`:
   ```
   POST /api/enrich/cuit
   Body: { "cuit": "20XXXXXXXXX" }
   Response: { afip: {...}, rns: {...}, score: 78, signals: [...] }
   ```
   Combines `afip_cuit_lookup.py` + `rns_dataset_lookup.py` into a single call.

2. **Integrate with onboarding wizard** (`colppy-vue`):
   - On CUIT input blur/validation, fire enrichment API
   - Auto-populate remaining wizard fields from response
   - If accountant detected → show contextual role confirmation (replaces skippable Step 2)

3. **Write to HubSpot** via existing `automated_cuit_enrichment.py` pattern:
   - New properties: `enrichment_score`, `business_age_years`, `tipo_societario`, `afip_activity_primary`
   - Update contact + company on enrichment

4. **Traffic quality dashboard**: Extend `docs/icp_dashboard.html` with:
   - Score distribution by UTM source/campaign
   - Conversion rate by score bucket
   - Real-time feed of today's signups with scores

### Phase B: ARCA Deep Enrichment (Week 3-4)

**Goal**: Add async ARCA signals (comprobantes, notifications, retenciones) as background enrichment.

1. **Background worker**: Trigger ARCA enrichment 1h after signup
   - Requires Clave Fiscal (can only run if user connects ARCA in-app)
   - Re-uses all existing `arca-prototype/backend/services/` code

2. **Comprobantes volume metric**: Count emitidos last 3 months → `facturacion_volume_3m` HubSpot property

3. **Score update**: Re-compute lead score with ARCA signals → update HubSpot

### Phase C: Bank Statement MVP (Week 5-6)

**Goal**: Offer bank import as a trial value-add, extract enrichment signals.

1. **User-facing "Conectar Banco" feature** in Colppy app
2. **Banco Galicia scraper** (already built) → production-ready with error handling
3. **Transaction categorization**: Basic rules for income/expense/transfer classification
4. **Reconciliation preview**: Match bank transactions with comprobantes from ARCA

### Phase D: Product-Led Demand Generation (Month 2+)

**Goal**: Free ARCA tools as lead magnets, reducing AdWords dependency.

1. **Free ARCA scanner**: "Ingresá tu CUIT y conocé tu situación fiscal"
   - No signup required → captures CUIT + enrichment data
   - Shows: DFE notifications, comprobante summary, retenciones
   - CTA: "Querés automatizar todo esto? Probá Colppy gratis"

2. **SEO landing pages**: Per-sector pages optimized for ARCA-related keywords
3. **Campaign scoring**: Measure PQL rate by acquisition channel, not just conversion

---

## 7. Key Files Reference

### Existing (ready to use)
| File | Purpose |
|------|---------|
| `tools/scripts/afip_cuit_lookup.py` | AFIP API via TusFacturas.app |
| `tools/scripts/rns_dataset_lookup.py` | RNS batch CUIT lookup |
| `tools/scripts/automated_cuit_enrichment.py` | CUIT → HubSpot write pipeline |
| `arca-prototype/backend/services/arca_scraper.py` | ARCA portal login + navigation |
| `arca-prototype/backend/services/notifications_api.py` | DFE notification extraction |
| `arca-prototype/backend/services/comprobantes_api.py` | Mis Comprobantes extraction |
| `arca-prototype/backend/services/retenciones_api.py` | Retenciones extraction |
| `arca-prototype/backend/services/banco_galicia_scraper.py` | Bank statement scraper |

### To Build
| File | Purpose |
|------|---------|
| `arca-prototype/backend/services/cuit_enrichment.py` | Unified enrichment orchestrator |
| `arca-prototype/backend/services/lead_scorer.py` | Score computation from merged signals |
| `arca-prototype/backend/routers/enrich.py` | REST API for enrichment |
| `colppy-vue/src/components/wizard-empresa/AccountantDetection.vue` | Contextual role confirmation UI |

### Data
| File | Contents |
|------|----------|
| `tools/data/business_age_analysis.csv` | 2,360-company analysis with RNS join |
| `tools/scripts/rns_datasets/registro-nacional-sociedades-202511.csv` | RNS dataset (3M rows) |
| `arca-prototype/data/banco_galicia_statements_20260223.csv` | 181 transactions (Oct 2025 - Feb 2026) |

---

## 8. Open Questions

1. **Clave Fiscal in onboarding**: Should we ask for Clave Fiscal during trial signup for ARCA enrichment, or wait until the user voluntarily connects ARCA in-app?
2. **Bank integration scope**: Galicia is proven. Which banks to add next? (BBVA, Santander, Macro cover ~70% of PyME accounts)
3. **Score threshold for PQL**: What enrichment score should trigger PQL status in HubSpot? Need to calibrate after Phase A data.
4. **RNS dataset freshness**: Currently using Nov 2025 snapshot. Should we automate monthly downloads from datos.gob.ar?
5. **Privacy/consent**: Bank credentials are sensitive. Need clear consent flow and credential handling policy before production.
