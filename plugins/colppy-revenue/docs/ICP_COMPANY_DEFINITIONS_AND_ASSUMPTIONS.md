# ICP y Assumptions a Nivel Objeto Compañía — Documento para RevOps

## 📋 Propósito del documento

Este documento define **qué es ICP a nivel objeto Compañía** y **qué assumptions usan los scripts de análisis** (funnel, billing, referrals, etc.) cuando trabajan con empresas en HubSpot. Está pensado para **RevOps**: saber exactamente qué se considera en los scripts evita inconsistencias entre reportes, workflows y datos.

**Última actualización**: 2025-01-26  
**Estado**: Documento vivo — actualizar cuando cambien definiciones o scripts  
**Audiencia**: RevOps, Revenue, Data / Analytics

**Referencias cruzadas**:
- **Funnel y definiciones Lead/MQL/SQL**: [COLPPY_FUNNEL_MAPPING_COMPLETE.md](./COLPPY_FUNNEL_MAPPING_COMPLETE.md)
- **Configuración HubSpot (campos, asociaciones)**: [README_HUBSPOT_CONFIGURATION.md](./README_HUBSPOT_CONFIGURATION.md)
- **Scripts HubSpot**: [HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md)
- **Deal–Company associations, billing rule, facturacion as master**: [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md)

---

## 🎯 Resumen ejecutivo (TL;DR)

- **ICP Operador (billing)**: Se determina **solo** por el **tipo de la PRIMARY company** del deal. Si `type` ∈ `Cuenta Contador` | `Cuenta Contador y Reseller` | `Contador Robado` → facturamos al contador (ICP Operador). Cualquier otro caso → ICP PYME (facturamos a la PyME).
- **Primary company**: Es la compañía con **asociación tipo 5** (PRIMARY) en deal–company. Los scripts **solo usan esta** para clasificar ICP Operador vs PYME.
- **Plan name / `nombre_del_plan`**: **No** se usa para ICP Operador. Una PyME referida por contador puede tener plan “ICP Contador” pero facturamos a la PyME; el tipo de la primary company es la fuente de verdad.
- **Association type 8** (Estudio Contable): Se usa para **accountant involvement** (contador involucrado en venta SMB), no para definir “quién facturamos”. Un deal puede tener type 8 y no ser ICP Operador (ej. PyME con contador asociado).
- **Deals sin primary company**: No se pueden clasificar como ICP Operador ni PYME. Los scripts los reportan como **issues de calidad de datos**.

---

## 📋 Company object — Quick reference (campos usados en scripts)

**Mapping completo**: Ver `README_HUBSPOT_CONFIGURATION.md` (sección Objeto Compañías y Canal Contador).

| Nombre interno | UI / descripción | Uso en scripts |
|----------------|------------------|----------------|
| `type` | Type (tipo de cuenta) | **Clasificación ICP**: Cuenta Contador, Cuenta Pyme, etc. |
| `tipo_icp_contador` | Campo calculado | NPS / enrichments (Híbrido, Operador, Asesor). **No** usado para ICP Operador en funnel/billing. |
| `industria` | Sector | Enrichment, inferencia de `type`, reporting. |
| `domain` | Dominio del sitio web | Enrichment, identificación. |
| `name` | Nombre de empresa | Identificación, reportes. |

### Campo en Deal: `primary_company_type`

- **Origen**: Propiedad sincronizada desde la **primary company** del deal (tipo de la compañía con asociación PRIMARY).
- **Uso en scripts**: Los scripts **prefieren** `primary_company_type` en el deal (si existe y es válido) y, si no, consultan la primary company vía API y leen `type`.
- **Objetivo**: Evitar llamadas extra a la API cuando el deal ya trae el tipo de la primary.

---

## 🏢 Valores de `type` (Company) relevantes para ICP

Valores que importan para **clasificación ICP en scripts**:

| Valor interno | Descripción | Uso en ICP |
|---------------|-------------|------------|
| **Cuenta Contador** | Estudio contable / cuenta contador | ICP Operador (facturamos al contador) |
| **Cuenta Contador y Reseller** | Contador que también revende | ICP Operador |
| **Contador Robado** | Contador descubierto vía cliente SMB | ICP Operador |
| **Cuenta Pyme** | PyME estándar | ICP PYME (facturamos a la PyME) |
| Otros (Alianza, Integración, Reseller, etc.) | Partnerships, otros | No tratados como ICP Operador en billing/funnel |

**Lista fija en código** (constante en scripts):
```text
ACCOUNTANT_COMPANY_TYPES = ['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']
```

Solo si la **primary company** del deal tiene `type` en esta lista, el deal se considera **ICP Operador** en los análisis.

---

## 🎯 Definición crítica: ICP Operador (quién facturamos)

### Regla única usada en scripts

Un deal se considera **ICP Operador** (facturado al contador) **solo** si:

1. El deal tiene **primary company** (asociación deal–company **typeId 5**).
2. Esa primary company tiene `type` ∈ `Cuenta Contador` | `Cuenta Contador y Reseller` | `Contador Robado`.

**Método**: Siempre **primary company → `type`**. No se usa plan, ni association type 8, ni ningún otro campo para esta clasificación.

### Qué no se usa para ICP Operador

- **Nombre del plan** (`nombre_del_plan_del_negocio`): No. PyMEs referidas por contador pueden tener plan “ICP Contador” y aun así facturamos a la PyME.
- **Association type 8** (Estudio Contable): Indica **involucramiento** del canal contador en el deal, no “quién factura”.
- **`tipo_icp_contador`**: Se usa en NPS y otros análisis de perfil contador (Híbrido/Operador/Asesor), pero **no** para ICP Operador en funnel/billing.

---

## 🔗 Deal–Company associations (relevantes para ICP)

| TypeId | Etiqueta | Uso en scripts |
|--------|----------|----------------|
| **5** | PRIMARY | **Primary company** del deal. **Solo esta** define ICP Operador vs PYME (vía `type`). |
| **8** | Estudio Contable / Asesor / Consultor Externo | **Canal contador / referral**. No define quién factura. |
| 341 | Default | Asociación estándar. No usada para clasificación ICP. |

**Resumen**:
- **Type 5** → primary company → `type` → ICP Operador o PYME.
- **Type 8** → contador involucrado en el deal (referral, dual-criteria en funnel).

---

## 📐 Assumptions de los scripts (qué se asume en código)

Estas son las **assumptions** explícitas que hacen los scripts al usar el objeto Compañía para ICP:

### 1. Primary company como fuente de verdad para billing

- **Assumption**: “Quién facturamos” = tipo de la **primary company** (asociación 5) del deal.
- **Scripts**: `analyze_icp_operador_billing`, `analyze_accountant_mql_funnel`, `analyze_smb_mql_funnel`, `analyze_accountant_referral_funnel`, `analyze_customer_referral_funnel`, `analyze_smb_accountant_involved_funnel`, `fetch_hubspot_deals_with_company` (con `--analyze-icp-operador`), workflow `hubspot_accountant_channel_deal_workflow`.

### 2. Plan name no define ICP Operador

- **Assumption**: El nombre del plan **no** se usa para clasificar ICP Operador. Solo `type` de la primary company.
- **Motivo**: Evitar confusión cuando la PyME tiene plan “ICP Contador” pero la facturación es a la PyME.

### 3. Uso de `primary_company_type` cuando existe

- **Assumption**: Si el deal tiene `primary_company_type` poblado y el valor está en `ACCOUNTANT_COMPANY_TYPES`, se usa eso para ICP Operador sin ir a la API de Companies.
- **Fallback**: Si falta o no aplica, se obtiene la primary company por typeId 5 y se lee `type` vía API.

### 4. Deals sin primary company = no clasificables

- **Assumption**: Sin primary company (typeId 5), el deal **no** se clasifica como ICP Operador ni como ICP PYME para billing/funnel.
- **Comportamiento**: Esos deals se reportan como **datos faltantes / calidad** (ej. en `analyze_icp_operador_billing`).

### 5. Association type 8 ≠ ICP Operador

- **Assumption**: Type 8 indica **accountant involvement** (contador involucrado en venta SMB; ver README_HUBSPOT_CONFIGURATION), no “facturamos al contador”. Un deal puede tener type 8 y ser ICP PYME (primary = PyME).
- **Billing rule:** Un producto se factura a un solo CUIT. Ese CUIT = PRIMARY. Otras compañías (contador, etc.) tienen CUITs distintos y no son PRIMARY. Ver [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md).
- **CUIT obligatorio para PRIMARY:** No aceptamos compañías sin CUIT válido como PRIMARY. La compañía debe tener CUIT en HubSpot para ser billing/primary. Si no tiene CUIT, debe enriquecerse o fusionarse antes.

### 6. Constante `ACCOUNTANT_COMPANY_TYPES` única

- **Assumption**: La lista `['Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado']` es la **única** usada para ICP Operador en todos los scripts mencionados. Cambios (nuevos tipos, renombres) deben reflejarse en código y en este doc.

---

## 📂 Scripts que usan estas definiciones

| Script | Uso de Company / ICP |
|--------|----------------------|
| `analyze_icp_operador_billing.py` | ICP Operador vs PYME por primary company `type`; reporta deals sin primary. |
| `analyze_accountant_mql_funnel.py` | Segmenta MQL→Won por ICP Operador / PYME (primary company). |
| `analyze_smb_mql_funnel.py` | Ídem para funnel SMB. |
| `analyze_accountant_referral_funnel.py` | Referrals contador; ICP Operador por primary company. |
| `analyze_customer_referral_funnel.py` | Referrals cliente; ICP Operador por primary company. |
| `analyze_smb_accountant_involved_funnel.py` | Funnel SMB con/sin contador (type 8); ICP por primary company. |
| `analyze_direct_deals_lead_source.py` | Lead source y atribución; puede usar primary company. |
| `analyze_referral_type8_correlation.py` | Correlación referral vs association type 8. |
| `fetch_hubspot_deals_with_company.py` | Deals + companies; `--analyze-icp-operador` usa misma lógica. |
| `analyze_industria_field_history.py` | Historial `industria`; usa primary company para deals. |
| `enrich_company_industry.py` | Enrichment de `industria` en Companies (no clasificación ICP). |
| `hubspot_accountant_channel_deal_workflow` (custom code) | Usa `primary_company_type` para canal contador / ICP. |

---

## ✅ Validaciones y calidad de datos

### Deals sin primary company

- **Comportamiento**: Los scripts que clasifican ICP **excluyen** estos deals de conteos ICP Operador / PYME y los listan aparte.
- **Ejemplo** (`analyze_icp_operador_billing`): Se muestra número y % de deals con vs sin primary company; los sin primary se detallan para corrección.
- **Acción RevOps**: Asegurar que todo deal relevante tenga primary company (asociación 5) correcta.

### Consistencia `type` vs `tipo_icp_contador`

- **Contexto**: `tipo_icp_contador` (Híbrido, Operador, Asesor) se usa en NPS y enrichments, no en billing/funnel.
- **Recomendación**: Mantener alineación entre `type` y `tipo_icp_contador` cuando ambos existan, para que reportes NPS y operativos no se contradigan.

### `industria` y inferencia de `type`

- Workflows y `enrich_company_industry` pueden inferir `type` desde `industria` (ej. “Contabilidad, impuestos, legales” → `Cuenta Contador`). Cualquier cambio en esas reglas afecta solo inferencia, no la regla “primary company `type`” usada en scripts.

---

## 📎 Referencias

- [COLPPY_FUNNEL_MAPPING_COMPLETE.md](./COLPPY_FUNNEL_MAPPING_COMPLETE.md) — Funnels, MQL, SQL, definiciones Lead.
- [README_HUBSPOT_CONFIGURATION.md](./README_HUBSPOT_CONFIGURATION.md) — Company `type`, deal–company associations, canal contador.
- [HUBSPOT_SCRIPTS_DOCUMENTATION.md](./HUBSPOT_SCRIPTS_DOCUMENTATION.md) — Descripción de cada script.
- [NPS_TO_ICP_DATA_FLOW.md](./NPS_TO_ICP_DATA_FLOW.md) — Uso de `type` y `tipo_icp_contador` en NPS.
- [CONTACTABILITY_ANALYSIS.md](./CONTACTABILITY_ANALYSIS.md) — ICP hypothesis (Contact + Company); propiedades `icp_*` en HubSpot/Mixpanel.

---

## 📝 Changelog

| Fecha | Cambio |
|-------|--------|
| 2025-01-26 | Versión inicial: definición ICP Operador, assumptions, scripts, validaciones. |
