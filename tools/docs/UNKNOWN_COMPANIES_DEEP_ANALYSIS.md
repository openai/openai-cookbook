# 🔍 Análisis Profundo de Empresas Unknown

## Documento de Análisis de Calidad de Datos

**Fecha:** Enero 2026  
**Versión:** 1.0

---

## 🎯 Objetivo

Analizar las 291 empresas clasificadas como "Unknown" en el análisis de NPS para identificar:
1. Problemas de calidad de datos
2. Oportunidades de enriquecimiento automático
3. Razones por las que un usuario que respondió el NPS está asociado a una empresa sin `type` e `industria`

---

## 📊 Resumen Ejecutivo

### Hallazgos Principales

| Métrica | Valor | Porcentaje |
|---------|-------|------------|
| **Total empresas Unknown** | 291 | 31.7% |
| **Contactos que son contadores** | 29 | 10.0% |
| **Contactos con deals asociados** | 244 | 83.8% |
| **Contactos con empresas en deals (con type)** | 164 | 56.4% |
| **Empresas enriquecibles** | 160 | 55.0% |

### Conclusiones Clave

1. **Problema de Calidad de Datos Identificado**: 56.4% de los contactos tienen empresas en deals con `type` poblado, pero su primary company es Unknown
2. **Oportunidad de Enriquecimiento**: 55% de las empresas Unknown pueden enriquecerse automáticamente
3. **Mayoría son SMBs**: Las empresas en deals sugieren que la mayoría son "Cuenta Pyme"

---

## 🔍 Análisis Detallado

### 1. Distribución de Tipos en Deals

Cuando analizamos las empresas asociadas a deals de los contactos con empresas Unknown, encontramos:

| Tipo de Empresa | Cantidad | Porcentaje |
|----------------|----------|------------|
| Cuenta Pyme | 169 | 68.4% |
| Cuenta Contador | 56 | 22.7% |
| Contador Robado | 7 | 2.8% |
| Empresa Administrada | 7 | 2.8% |
| Cuenta Contador y Reseller | 4 | 1.6% |
| **Total** | **247** | **100%** |

**Insight**: La mayoría de las empresas Unknown son probablemente "Cuenta Pyme" (68.4%)

### 2. Contactos que son Contadores

**29 contactos (10.0%)** son contadores según `es_contador` o `rol_wizard`.

**Implicación**: Estas 29 empresas Unknown podrían ser clasificadas como "Cuenta Contador" basándose en el contacto.

**Ejemplo**:
- Empresa: "90221 - EMG COMUNICACIONES SRL"
- Contacto: arieljurjo5@gmail.com
- `es_contador`: true
- **Recomendación**: Type = "Cuenta Contador"

### 3. Problemas de Calidad de Datos

**164 contactos (56.4%)** tienen empresas en deals con `type` poblado, pero su primary company es Unknown.

**Causa Raíz**: La primary company no está correctamente asignada. El contacto debería estar asociado a la empresa que aparece en los deals.

**Ejemplos de Problemas**:

#### Caso 1: Múltiples Empresas en Deals
- **Empresa Unknown**: "CRANER S.A."
- **Contacto**: sbarrera@gruasdipsa.com.ar
- **Empresas en Deals**:
  - COOPERATIVA DE TRABAJO ESCANDINAVA LTDA. (Type: Cuenta Pyme)
  - DIP S.A. (Type: Cuenta Pyme)
  - RENTAL S.A. (Type: Cuenta Pyme)
- **Problema**: El contacto tiene 3 empresas en deals, pero la primary company es Unknown

#### Caso 2: Empresa Duplicada
- **Empresa Unknown**: "62028 - TOP TECH SA"
- **Contacto**: carolina@toptechsa.com
- **Empresa en Deal**: "62028-Top Tech SA" (Type: Cuenta Pyme)
- **Problema**: Probablemente la misma empresa con nombre ligeramente diferente

#### Caso 3: Empresa Correcta en Deal
- **Empresa Unknown**: "40444 - HULLOP SOLUTIONS S.A."
- **Contacto**: mfg1979ar@gmail.com
- **Empresas en Deals**:
  - 40444 HULLOP SOLUTIONS S.A. (Type: Cuenta Pyme) ← Mismo nombre
  - Dromobox S.A. (Type: Cuenta Pyme)
- **Problema**: La empresa correcta está en el deal pero no es la primary company

---

## 💡 Oportunidades de Enriquecimiento

### Método 1: Enriquecimiento desde Contacto

**Criterio**: Si el contacto tiene `es_contador = true` o `rol_wizard` contiene "contador"

**Empresas afectadas**: 29 empresas

**Acción**:
```python
if contact.es_contador == True OR "contador" in contact.rol_wizard:
    company.type = "Cuenta Contador"
```

**Ejemplo**:
- Empresa: "90221 - EMG COMUNICACIONES SRL"
- Contacto: arieljurjo5@gmail.com (es_contador: true)
- **Resultado**: Type = "Cuenta Contador"

### Método 2: Enriquecimiento desde Deals

**Criterio**: Si el contacto tiene empresas en deals con `type` poblado

**Empresas afectadas**: 164 empresas

**Estrategias**:

#### Estrategia A: Usar la Empresa Más Frecuente
- Si un contacto tiene múltiples empresas en deals, usar la que aparece más frecuentemente
- Si hay empate, usar la más reciente

#### Estrategia B: Usar la Empresa con Mismo Nombre
- Si hay una empresa en deal con nombre similar a la Unknown, usar esa
- Ejemplo: "62028 - TOP TECH SA" → "62028-Top Tech SA"

#### Estrategia C: Usar la Empresa Primary en Deal
- Si hay una empresa marcada como Primary (typeId: 5) en un deal, usar esa

**Ejemplo**:
- Empresa Unknown: "40444 - HULLOP SOLUTIONS S.A."
- Empresa en Deal: "40444 HULLOP SOLUTIONS S.A." (Type: Cuenta Pyme)
- **Resultado**: Type = "Cuenta Pyme" (mismo nombre)

### Método 3: Inferencia Estadística

**Criterio**: Basado en la distribución de tipos en deals

**Empresas afectadas**: Resto de empresas sin deals o sin type en deals

**Acción**:
- Si no hay información en deals, inferir "Cuenta Pyme" (68.4% de probabilidad)
- Solo usar si no hay otra información disponible

---

## 🔧 Recomendaciones de Implementación

### Fase 1: Enriquecimiento Automático (Inmediato)

1. **Enriquecer desde Contacto** (29 empresas)
   - Script que identifique contactos contadores
   - Actualizar `company.type = "Cuenta Contador"` para esas empresas

2. **Enriquecer desde Deals - Casos Simples** (estimado: ~50 empresas)
   - Empresas con mismo nombre en deal
   - Empresas únicas en deals del contacto

### Fase 2: Corrección de Calidad de Datos (Corto Plazo)

1. **Reasignar Primary Company** (164 empresas)
   - Identificar empresas correctas en deals
   - Actualizar primary company del contacto
   - Considerar crear workflow que detecte y corrija automáticamente

2. **Deduplicación de Empresas**
   - Identificar empresas duplicadas (mismo nombre, diferentes IDs)
   - Consolidar empresas duplicadas

### Fase 3: Prevención (Mediano Plazo)

1. **Workflow de Validación**
   - Cuando se crea/actualiza un deal, verificar que la primary company tenga `type`
   - Si no tiene, intentar inferir desde otras empresas en deals del contacto

2. **Workflow de Enriquecimiento Proactivo**
   - Cuando una empresa queda sin `type`, buscar en deals asociados
   - Enriquecer automáticamente si se encuentra información

---

## 📋 Plan de Acción

### Prioridad Alta (Implementar Inmediatamente)

1. ✅ **Script de Enriquecimiento desde Contacto**
   - Archivo: `tools/scripts/hubspot/enrich_unknown_companies_from_contact.py`
   - Impacto: 29 empresas (10%)
   - Esfuerzo: Bajo

2. ✅ **Script de Enriquecimiento desde Deals - Casos Simples**
   - Archivo: `tools/scripts/hubspot/enrich_unknown_companies_from_deals.py`
   - Impacto: ~50 empresas (17%)
   - Esfuerzo: Medio

### Prioridad Media (Implementar en 2-4 semanas)

3. ⚠️ **Script de Corrección de Primary Company**
   - Archivo: `tools/scripts/hubspot/fix_primary_company_from_deals.py`
   - Impacto: 164 empresas (56%)
   - Esfuerzo: Alto (requiere validación manual)

4. ⚠️ **Workflow de Validación en HubSpot**
   - Workflow que valide primary company cuando se crea deal
   - Impacto: Prevención futura
   - Esfuerzo: Medio

### Prioridad Baja (Implementar en 1-2 meses)

5. 📝 **Workflow de Enriquecimiento Proactivo**
   - Workflow que enriquezca empresas sin type automáticamente
   - Impacto: Prevención futura
   - Esfuerzo: Alto

---

## 📊 Métricas de Éxito

### Objetivos

| Métrica | Actual | Objetivo | Mejora |
|---------|--------|----------|--------|
| Empresas Unknown | 291 (31.7%) | <100 (10%) | -66% |
| Empresas enriquecibles | 160 (55%) | 160 (100%) | +45% |
| Contactos con primary company correcta | 127 (43.6%) | 255 (87.6%) | +44% |

### KPIs de Seguimiento

1. **Tasa de Enriquecimiento**: % de empresas Unknown que se enriquecen exitosamente
2. **Tasa de Corrección**: % de primary companies que se corrigen
3. **Tasa de Prevención**: % de nuevas empresas Unknown que se previenen

---

## 🔍 Casos de Estudio

### Caso 1: Contacto Contador

**Empresa Unknown**: "90221 - EMG COMUNICACIONES SRL"  
**Contacto**: arieljurjo5@gmail.com  
**Datos del Contacto**:
- `es_contador`: true
- `rol_wizard`: null

**Análisis**:
- El contacto es contador, por lo tanto la empresa debería ser "Cuenta Contador"
- No hay empresas en deals, así que el enriquecimiento debe ser desde el contacto

**Acción Recomendada**:
```python
company.type = "Cuenta Contador"
company.industria = "Contabilidad, impuestos, legales"  # Si está vacío
```

### Caso 2: Empresa Duplicada

**Empresa Unknown**: "62028 - TOP TECH SA"  
**Contacto**: carolina@toptechsa.com  
**Empresa en Deal**: "62028-Top Tech SA" (Type: Cuenta Pyme)

**Análisis**:
- Mismo nombre con ligera variación
- La empresa en deal tiene type poblado
- Probablemente es la misma empresa

**Acción Recomendada**:
1. Verificar si son la misma empresa (comparar domain, otros campos)
2. Si son la misma, consolidar o actualizar la Unknown con el type del deal
3. Si son diferentes, actualizar primary company del contacto

### Caso 3: Múltiples Empresas en Deals

**Empresa Unknown**: "CRANER S.A."  
**Contacto**: sbarrera@gruasdipsa.com.ar  
**Empresas en Deals**:
- COOPERATIVA DE TRABAJO ESCANDINAVA LTDA. (Type: Cuenta Pyme)
- DIP S.A. (Type: Cuenta Pyme)
- RENTAL S.A. (Type: Cuenta Pyme)

**Análisis**:
- El contacto tiene 3 empresas en deals, todas con type
- La primary company es Unknown
- Necesita investigación manual para determinar cuál es la correcta

**Acción Recomendada**:
1. Revisar deals para determinar cuál es la empresa principal
2. Verificar si "CRANER S.A." es una empresa diferente o una de las 3
3. Actualizar primary company según resultado

---

## 📝 Notas Técnicas

### Asociaciones HubSpot

**Contact → Company Associations**:
- Type ID 1: Primary Company (HUBSPOT_DEFINED)
- Type ID 341: Default association (HUBSPOT_DEFINED)

**Deal → Company Associations**:
- Type ID 5: Primary Company (HUBSPOT_DEFINED)
- Type ID 341: Default association (HUBSPOT_DEFINED)
- Type ID 8: Estudio Contable / Asesor (USER_DEFINED)

### Campos Clave

**Contact**:
- `es_contador`: Boolean - Indica si el contacto es contador
- `rol_wizard`: String - Rol del usuario (puede contener "contador")

**Company**:
- `type`: Enum - Tipo de cuenta (Cuenta Contador, Cuenta Pyme, etc.)
- `industria`: Enum - Industria de la empresa
- `domain`: String - Dominio del sitio web

---

## 🔗 Referencias

- [Flujo de Datos NPS a ICP](tools/docs/NPS_TO_ICP_DATA_FLOW.md)
- [Configuración HubSpot](tools/docs/README_HUBSPOT_CONFIGURATION.md)
- [Workflow de Enriquecimiento](tools/scripts/hubspot/custom_code/hubspot_first_deal_won_calculations.js)

---

**Última actualización:** Enero 2026  
**Versión del documento:** 1.0
