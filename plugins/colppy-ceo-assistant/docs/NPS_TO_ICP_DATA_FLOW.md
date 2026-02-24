# 📊 Flujo de Datos: NPS a ICP en HubSpot

## Documento para Equipo de Lealtad del Canal de Contadores

**Fecha:** Enero 2026  
**Versión:** 1.0

---

## 🎯 Objetivo

Este documento explica cómo fluyen los datos desde las respuestas del NPS (Net Promoter Score) en Intercom hasta la identificación del ICP (Ideal Customer Profile) en HubSpot, incluyendo el modelo de datos y el proceso de enriquecimiento.

---

## 📋 Tabla de Contenidos

1. [Visión General del Flujo](#visión-general-del-flujo)
2. [Paso 1: Captura de NPS desde Intercom](#paso-1-captura-de-nps-desde-intercom)
3. [Paso 2: Enriquecimiento a Nivel de Contacto](#paso-2-enriquecimiento-a-nivel-de-contacto)
4. [Paso 3: Enriquecimiento a Nivel de Empresa](#paso-3-enriquecimiento-a-nivel-de-empresa)
5. [Paso 4: Identificación del ICP](#paso-4-identificación-del-icp)
6. [Modelo de Datos](#modelo-de-datos)
7. [Funnel de Clasificación](#funnel-de-clasificación)
8. [Cobertura y Calidad de Datos](#cobertura-y-calidad-de-datos)

---

## 🔄 Visión General del Flujo

```
┌─────────────────┐
│  NPS Intercom   │  →  Respuesta del usuario con email
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Enriquecimiento│  →  Buscar contacto en HubSpot por email
│  Nivel Contacto  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Identificación │  →  ¿Es contador? (es_contador, rol_wizard)
│  Tipo Usuario   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Asociación     │  →  Contacto → Empresa (Primary Company)
│  Contacto-Empresa│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Enriquecimiento│  →  Obtener datos de la empresa
│  Nivel Empresa  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Identificación │  →  ICP: Contador / SMB / Partner / Unknown
│  ICP Empresa    │
└─────────────────┘
```

---

## 📥 Paso 1: Captura de NPS desde Intercom

### Fuente de Datos
- **Plataforma:** Intercom
- **Tipo:** Encuestas NPS
- **Formato:** CSV exportado
- **Campos clave:**
  - `email` - Email del usuario que respondió
  - `score` - Puntuación NPS (0-10)
  - `comment` - Comentario opcional
  - `created_at` - Fecha de respuesta

### Proceso
1. Exportación manual o automática desde Intercom
2. Archivos CSV con respuestas por período
3. Consolidación de múltiples archivos en un dataset único
4. Deduplicación inteligente (considera respuestas en diferentes períodos)

**Script:** `tools/scripts/intercom/analyze_nps_data.py`

---

## 👤 Paso 2: Enriquecimiento a Nivel de Contacto

### Objetivo
Identificar si el usuario que respondió el NPS es un **contador** o no.

### Proceso

#### 2.1. Búsqueda del Contacto en HubSpot
- **Método:** Búsqueda por email usando HubSpot API
- **Endpoint:** `GET /crm/v3/objects/contacts/search`
- **Resultado:** ID del contacto si existe

#### 2.2. Identificación de Tipo de Usuario
Una vez encontrado el contacto, se consultan los siguientes campos:

| Campo HubSpot | Nombre Interno | Descripción |
|--------------|----------------|-------------|
| `es_contador` | `es_contador` | Checkbox que indica si es contador |
| `rol_wizard` | `rol_wizard` | Rol del usuario (puede indicar contador) |

**Lógica de Clasificación:**
```python
if es_contador == True OR rol_wizard contiene "contador":
    user_type = "Accountant"
else:
    user_type = "Non-Accountant"
```

### Cobertura Actual
- **Contactos encontrados:** ~99.3% de los emails del NPS
- **Contactos no encontrados:** ~0.7% (emails que no existen en HubSpot)

**Script:** `tools/scripts/intercom/analyze_nps_by_user_type.py`

---

## 🏢 Paso 3: Enriquecimiento a Nivel de Empresa

### Objetivo
Identificar la **empresa** asociada al contacto y obtener su **ICP**.

### Proceso: Método Híbrido (4 Pasos)

#### **Paso 3.1: Primary Company (Asociación Tipo 1)**
- **Método:** Obtener empresa primaria del contacto
- **Asociación:** `contact → company` (typeId: 1)
- **Cobertura:** ~93% de los contactos
- **Prioridad:** ⭐ Más confiable

**Endpoint:** `GET /crm/v3/objects/contacts/{contactId}/associations/companies`

#### **Paso 3.2: Deal Primary Company (Asociación Tipo 5)**
- **Método:** Si no hay primary company, buscar en deals del contacto
- **Asociación:** `deal → company` (typeId: 5)
- **Cobertura:** Mejora la cobertura total
- **Prioridad:** ⭐⭐ Fallback confiable

#### **Paso 3.3: Cualquier Empresa Asociada**
- **Método:** Si no hay primary, buscar cualquier empresa asociada
- **Asociación:** Cualquier tipo de asociación contacto-empresa
- **Cobertura:** Mejora aún más la cobertura
- **Prioridad:** ⭐⭐⭐ Último recurso

#### **Paso 3.4: Clasificación Final**
- **Método:** Combinar resultados de pasos anteriores
- **Prioridad:** Primary Company > Deal Primary > Cualquier Asociación

### Campos de Empresa Consultados

| Campo HubSpot | Nombre Interno | Tipo | Descripción |
|--------------|----------------|------|-------------|
| `Type` | `type` | Enum | Tipo de cuenta: "Cuenta Contador" / "Cuenta Pyme" |
| `tipo_icp_contador` | `tipo_icp_contador` | Calculado | ICP calculado: "Híbrido" / "Operador" / "Asesor" |
| `industria` | `industria` | Enum | Industria de la empresa (en español) |
| `domain` | `domain` | Texto | Dominio del sitio web |

**Script:** `tools/scripts/intercom/analyze_nps_icp_data_quality.py`

---

## 🎯 Paso 4: Identificación del ICP

### Clasificación del ICP

El ICP se identifica usando el campo calculado `tipo_icp_contador` y el campo `type` de la empresa:

#### **ICP Accountant - Híbrido**
- **Condición:** `tipo_icp_contador == "Híbrido"`
- **Descripción:** Empresa contadora que opera como híbrido

#### **ICP Accountant - Operador**
- **Condición:** `tipo_icp_contador == "Operador"`
- **Descripción:** Empresa contadora que opera directamente

#### **ICP Accountant - Asesor**
- **Condición:** `tipo_icp_contador == "Asesor"`
- **Descripción:** Empresa contadora que asesora

#### **ICP Accountant (type field)**
- **Condición:** `type == "Cuenta Contador"` AND `tipo_icp_contador` está vacío
- **Descripción:** Empresa contadora identificada por el campo Type

#### **ICP SMB**
- **Condición:** `type == "Cuenta Pyme"` AND `tipo_icp_contador` está vacío
- **Descripción:** Pequeña y mediana empresa (no contadora)

#### **ICP Partner**
- **Condición:** `type == "Cuenta Partner"` (si aplica)
- **Descripción:** Empresa partner

#### **Unknown**
- **Condición:** `type` está NULL/EMPTY AND `tipo_icp_contador` está NULL/EMPTY
- **Descripción:** No se puede determinar el ICP

### Lógica de Clasificación

```python
def classify_icp(tipo_icp_contador, company_type):
    if tipo_icp_contador == "Híbrido":
        return "ICP Accountant - Híbrido"
    elif tipo_icp_contador == "Operador":
        return "ICP Accountant - Operador"
    elif tipo_icp_contador == "Asesor":
        return "ICP Accountant - Asesor"
    elif company_type == "Cuenta Contador":
        return "ICP Accountant (type field)"
    elif company_type == "Cuenta Pyme":
        return "ICP SMB"
    elif company_type == "Cuenta Partner":
        return "ICP Partner"
    else:
        return "Unknown"
```

---

## 📊 Modelo de Datos

### Estructura de Datos Final

```
NPS Response
├── email (string)
├── score (int, 0-10)
├── comment (string, opcional)
├── created_at (datetime)
│
├── Contact Enrichment
│   ├── contact_id (string)
│   ├── contact_found (boolean)
│   ├── user_type (string: "Accountant" | "Non-Accountant")
│   └── user_type_source (string: "es_contador" | "rol_wizard")
│
└── Company Enrichment
    ├── company_id (string)
    ├── company_name (string)
    ├── company_type (string: "Cuenta Contador" | "Cuenta Pyme" | NULL)
    ├── tipo_icp_contador (string: "Híbrido" | "Operador" | "Asesor" | NULL)
    ├── industria (string)
    ├── domain (string)
    ├── icp_classification (string)
    └── enrichment_method (string: "primary_company" | "deal_primary" | "any_association")
```

### Campos Clave en HubSpot

#### **Contacto (Contact)**
- `es_contador` - Indica si el contacto es contador
- `rol_wizard` - Rol del usuario
- `email` - Email (usado para búsqueda)

#### **Empresa (Company)**
- `type` - Tipo de cuenta (enum)
- `tipo_icp_contador` - ICP calculado (campo calculado)
- `industria` - Industria (enum en español)
- `domain` - Dominio del sitio web

#### **Asociaciones**
- `contact → company` (typeId: 1) - Primary Company
- `deal → company` (typeId: 5) - Primary Company en Deal

---

## 🔄 Funnel de Clasificación

### Funnel Completo

```
Total NPS Responses
    │
    ├─→ 99.3% Contactos encontrados en HubSpot
    │       │
    │       ├─→ 93.0% Con Primary Company (Step 1)
    │       │       │
    │       │       ├─→ 63.3% ICP SMB
    │       │       ├─→ 31.7% Unknown (Type NULL)
    │       │       ├─→ 2.2% ICP Accountant (type field)
    │       │       ├─→ 1.6% ICP Accountant - Operador
    │       │       ├─→ 0.7% ICP Accountant - Híbrido
    │       │       ├─→ 0.3% ICP Partner
    │       │       └─→ 0.2% ICP Accountant - Asesor
    │       │
    │       ├─→ 7.0% Sin Primary Company
    │       │       │
    │       │       └─→ Step 2: Deal Primary Company
    │       │           └─→ Step 3: Cualquier Asociación
    │       │
    │       └─→ 0.7% Contactos no encontrados
    │
    └─→ 0.7% Emails no encontrados en HubSpot
```

### Cobertura por Paso

| Paso | Método | Cobertura | Prioridad |
|------|--------|-----------|-----------|
| Step 1 | Primary Company (typeId 1) | 93.0% | ⭐⭐⭐ |
| Step 2 | Deal Primary Company (typeId 5) | +X% | ⭐⭐ |
| Step 3 | Cualquier Asociación | +Y% | ⭐ |
| Step 4 | Clasificación Final | 100% | - |

---

## 📈 Cobertura y Calidad de Datos

### Métricas Actuales (Step 1)

- **Total emails únicos:** 988
- **Contactos encontrados:** 981 (99.3%)
- **Primary Company encontrada:** 919 (93.0%)
- **Sin Primary Company:** 69 (7.0%)

### Distribución de ICP (Step 1)

| ICP Classification | Cantidad | Porcentaje |
|-------------------|----------|------------|
| ICP SMB | 582 | 63.3% |
| Unknown | 291 | 31.7% |
| ICP Accountant (type field) | 20 | 2.2% |
| ICP Accountant - Operador | 15 | 1.6% |
| ICP Accountant - Híbrido | 6 | 0.7% |
| ICP Partner | 3 | 0.3% |
| ICP Accountant - Asesor | 2 | 0.2% |

### Casos "Unknown"

**Causa Principal:** Empresas con `type` y `tipo_icp_contador` en NULL/EMPTY

**Distribución:**
- 100% de los casos Unknown tienen `type` = NULL
- 100% de los casos Unknown tienen `tipo_icp_contador` = NULL
- ~90% no tienen dominio (no se puede hacer web scraping)
- ~10% tienen dominio pero aún no han sido procesados por el workflow

**Solución Implementada:**
- Workflow automático que infiere `type` basado en `industria`
- Enriquecimiento automático de `industria` desde website o nombre de empresa
- Mejora continua de keywords para identificación

---

## 🔧 Automatizaciones Implementadas

### 1. Enriquecimiento Automático de Industria

**Workflow:** `hubspot_first_deal_won_calculations.js`

**Proceso:**
1. Si `industria` está NULL → Intenta enriquecer desde:
   - Website scraping (si hay dominio)
   - Análisis de nombre de empresa (fallback)
2. Mapea a valores en español para el campo `industria`
3. Notifica en Slack cuando se enriquece

**Keywords:** 20+ industrias con 100+ keywords en español e inglés

### 2. Inferencia Automática de Type

**Workflow:** `hubspot_first_deal_won_calculations.js`

**Proceso:**
1. Si `type` está NULL → Infiere desde `industria`:
   - Si `industria == "Contabilidad, impuestos, legales"` → `type = "Cuenta Contador"`
   - Si no → `type = "Cuenta Pyme"`
2. Notifica en Slack cuando se infiere

### 3. Caché de Datos

**Archivos CSV:**
- `hubspot_user_type_enrichment.csv` - Enriquecimiento de tipo de usuario
- `step1_primary_company_enrichment_*.csv` - Enriquecimiento de empresa (Step 1)

**Beneficio:** Evita llamadas repetidas a la API de HubSpot

---

## 📝 Scripts Disponibles

### Análisis de NPS
- **`analyze_nps_data.py`** - Análisis general de NPS (score, tendencias, feedback)
- **`analyze_nps_by_user_type.py`** - Análisis de NPS segmentado por tipo de usuario (contador/no contador)

### Análisis de ICP
- **`analyze_nps_icp_data_quality.py`** - Análisis paso a paso de calidad de datos para ICP

### Enriquecimiento
- **`enrich_company_industry.py`** - Enriquecimiento manual de industria desde nombre/dominio

---

## 🎯 Próximos Pasos

### Mejoras en Curso

1. **Reducción de Casos "Unknown"**
   - Workflow automático ejecutándose
   - Mejora continua de keywords
   - Enriquecimiento de empresas sin dominio

2. **Mejora de Cobertura**
   - Implementar Steps 2 y 3 del método híbrido
   - Mejorar asociaciones contacto-empresa

3. **Validación de Datos**
   - Validar consistencia entre `type` y `tipo_icp_contador`
   - Identificar y corregir inconsistencias

### Recomendaciones

1. **Monitoreo Continuo**
   - Revisar casos "Unknown" periódicamente
   - Validar enriquecimientos automáticos

2. **Mejora de Datos en HubSpot**
   - Poblar campo `domain` cuando sea posible
   - Validar campo `industria` para empresas existentes

3. **Automatización**
   - Considerar workflow que se ejecute periódicamente
   - Notificaciones para casos que requieren atención manual

---

## 📞 Contacto y Soporte

Para preguntas sobre este flujo de datos o para solicitar mejoras, contactar al equipo de Producto/Data.

---

**Última actualización:** Enero 2026  
**Versión del documento:** 1.0

