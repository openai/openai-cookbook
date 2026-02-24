# 🎯 Proyecto de Calidad de Datos: Intercom, Mixpanel y HubSpot

## Plan Estratégico de Mejora de Datos - Strike Team

**Fecha:** [A definir]  
**Duración:** 120 minutos  
**Participantes:** [Equipo de Producto, Data, Customer Success, Sales, Engineering]

---

## 📋 Agenda

### 1. Visión General del Proyecto (20 min)
### 2. Oportunidades por Plataforma (30 min)
### 3. Plan de Acción por Fases (40 min)
### 4. Asignación de Responsabilidades (20 min)
### 5. Timeline y Métricas (10 min)

---

## 1️⃣ VISIÓN GENERAL DEL PROYECTO

### Situación Actual

**Problemas Identificados en las Tres Plataformas:**

#### 🏢 HubSpot
- **291 empresas (31.7%)** clasificadas como "Unknown" en análisis NPS → ICP
- Empresas con `type` e `industria` en NULL/EMPTY
- Primary companies incorrectamente asignadas (56.4% de casos Unknown)
- Campos faltantes: `mixpanel_distinct_id`, `mixpanel_cohort_name`, `icp_hypothesis`
- Problemas de timezone en timestamps (45.1% de eventos aparecen "antes" de registro)
- Validación de datos faltante (churn date vs first deal date)
- UTM parameters no se pasan desde Intercom

#### 📊 Mixpanel
- **127 eventos faltantes** (36% de 350 eventos totales) no documentados
- **27 propiedades de usuario faltantes** (42% de 65 propiedades totales)
- Eventos del Wizard incompletos: faltan `role_in_company`, `company_type`, `plan_to_implement`
- Propiedades ICP faltantes: `icp_hypothesis`, `icp_confidence`, `icp_source`
- Gap de datos para contactos sales-led (solo evento "Qualification" hasta trial signup)
- Propiedades de perfil incompletas para análisis de comportamiento temprano

#### 💬 Intercom
- UTM parameters no se pasan a HubSpot cuando se crea contacto desde Intercom
- Gap de atribución: `lead_source = 'Orgánico'` cuando debería tener UTM
- Falta sincronización bidireccional completa con HubSpot
- NPS responses no enriquecidas automáticamente con datos de HubSpot

### Impacto en el Negocio

1. **Análisis Incompleto**
   - NPS no segmentable por ICP (31.7% Unknown)
   - Funnel analysis incompleto (gaps en Mixpanel para sales-led)
   - Atribución de marketing incompleta (UTM faltante)
   - Análisis de comportamiento temprano limitado (propiedades ICP faltantes)

2. **Toma de Decisiones Limitada**
   - No podemos identificar patrones por segmento
   - No podemos priorizar mejoras de producto por ICP
   - No podemos medir efectividad de canales de marketing
   - No podemos inferir ICP temprano para personalización

3. **Calidad de Datos Sistémica**
   - Problemas afectan múltiples análisis
   - Impacta reportes ejecutivos y dashboards
   - Limita capacidad de automatización y workflows

### Objetivo del Proyecto

**Mejorar calidad de datos en las tres plataformas para habilitar análisis completos y toma de decisiones basada en datos**

**Métricas Objetivo:**
- **HubSpot**: Reducir empresas Unknown de 31.7% a <10%
- **Mixpanel**: Documentar 100% de eventos y propiedades activas, crear propiedades ICP
- **Intercom**: 100% de atribución UTM en contactos creados
- **Integración**: Sincronización bidireccional completa entre plataformas

---

## 2️⃣ OPORTUNIDADES POR PLATAFORMA

### 🏢 HubSpot - Oportunidades de Mejora

#### Oportunidad 1: Enriquecimiento de Empresas Unknown
**Prioridad:** 🔴 Crítica  
**Impacto:** 291 empresas (31.7% del total)

**Hallazgos:**
- 160 empresas (55%) pueden enriquecerse automáticamente
- 29 empresas (10%): desde contacto (si es contador)
- 164 empresas (56.4%): desde deals (empresas con type en deals)
- 56.4% tienen problemas de calidad de datos (primary company incorrecta)

**Acciones:**
1. Enriquecer desde contacto (29 empresas)
2. Enriquecer desde deals simples (~50 empresas)
3. Corregir primary company (164 empresas)
4. Inferencia estadística para restantes (~50 empresas)

#### Oportunidad 2: Campos de Integración Mixpanel
**Prioridad:** 🟡 Alta  
**Impacto:** Sincronización HubSpot ↔ Mixpanel

**Campos Faltantes:**
- `mixpanel_distinct_id` - Identificador único de Mixpanel
- `mixpanel_cohort_name` - Nombre del cohort desde Mixpanel
- `mixpanel_cohort_id` - ID del cohort
- `mixpanel_project_id` - ID del proyecto Mixpanel
- `mixpanel_session_id` - ID de sesión

**Acciones:**
1. Crear campos en HubSpot (Contact + Company)
2. Implementar sincronización bidireccional
3. Backfill de datos históricos

#### Oportunidad 3: Propiedades ICP
**Prioridad:** 🟡 Alta  
**Impacto:** Inferencia temprana de ICP

**Campos Faltantes:**
- `icp_hypothesis` - Hipótesis de ICP (pyme_operator, accountant_advisor, tech_integrator, unknown)
- `icp_confidence` - Nivel de confianza (0-100)
- `icp_source` - Fuente de la hipótesis (behavior, wizard, hubspot)
- `icp_secondary` - Segunda mejor hipótesis

**Acciones:**
1. Crear campos en HubSpot (Contact + Company)
2. Implementar lógica de scoring desde Mixpanel
3. Sincronización automática desde Mixpanel

#### Oportunidad 4: Validación de Datos
**Prioridad:** 🟡 Media  
**Impacto:** Prevención de errores

**Problemas Identificados:**
- Churn date puede ser < First Deal Date (inconsistencia)
- Companies con deals pueden no tener First Deal Date
- Problemas de timezone en timestamps

**Acciones:**
1. Crear workflows de validación
2. Implementar reglas de negocio
3. Alertas automáticas para inconsistencias

#### Oportunidad 5: Atribución UTM desde Intercom
**Prioridad:** 🟡 Media  
**Impacto:** Atribución de marketing

**Problema:**
- Intercom captura UTM pero no los pasa a HubSpot
- `lead_source = 'Orgánico'` cuando debería tener UTM
- Atribución retroactiva solo si usuario hace trial

**Acciones:**
1. Modificar integración Intercom → HubSpot para pasar UTM
2. Backfill de contactos existentes sin UTM
3. Workflow para atribución retroactiva

---

### 📊 Mixpanel - Oportunidades de Mejora

#### Oportunidad 1: Documentación Completa de Eventos
**Prioridad:** 🟡 Alta  
**Impacto:** 127 eventos faltantes (36%)

**Hallazgos:**
- 223 eventos documentados (64%)
- 127 eventos faltantes probablemente en:
  - Operaciones financieras avanzadas (20-30 eventos)
  - Integraciones y APIs (15-25 eventos)
  - Gestión avanzada de usuarios (10-15 eventos)
  - Operaciones de negocio avanzadas (15-20 eventos)

**Acciones:**
1. Análisis exhaustivo del lexicon de Mixpanel
2. Documentar eventos faltantes
3. Categorizar y priorizar eventos por uso

#### Oportunidad 2: Propiedades de Usuario Completas
**Prioridad:** 🟡 Alta  
**Impacto:** 27 propiedades faltantes (42%)

**Hallazgos:**
- 38 propiedades documentadas (58%)
- 27 propiedades faltantes necesarias para análisis completos

**Acciones:**
1. Extraer todas las propiedades del lexicon
2. Documentar propiedades faltantes
3. Mapear propiedades a casos de uso de negocio

#### Oportunidad 3: Eventos del Wizard Completos
**Prioridad:** 🔴 Crítica  
**Impacto:** Inferencia temprana de ICP

**Propiedades Faltantes en "Finalizar Wizard":**
- `role_in_company` - Rol del usuario (Contador/Asesor, Dueño, etc.)
- `company_type` - Tipo de empresa (Estudio contable, Empresa PyME)
- `plan_to_implement` - Plan de implementación (Ahora, Esta semana, etc.)

**Mapeo a HubSpot:**
- `rol_wizard` → `role_in_company`
- `lead_company_type` → `company_type`
- `implementacion_wizard` → `plan_to_implement`

**Acciones:**
1. Agregar propiedades faltantes al evento "Finalizar Wizard"
2. Sincronizar con HubSpot
3. Usar para scoring de ICP

#### Oportunidad 4: Propiedades ICP en Perfiles
**Prioridad:** 🔴 Crítica  
**Impacto:** Inferencia temprana de ICP

**Propiedades Faltantes:**
- `icp_hypothesis` - Hipótesis de ICP
- `icp_confidence` - Nivel de confianza
- `icp_source` - Fuente de la hipótesis
- `icp_secondary` - Segunda mejor hipótesis
- `did_key_event_early` - Eventos clave en primeras 120 min
- `explored_multiempresa_early` - Exploración multiempresa temprana

**Acciones:**
1. Crear propiedades en Mixpanel
2. Implementar lógica de scoring
3. Sincronizar con HubSpot

#### Oportunidad 5: Gap de Datos para Sales-Led Contacts
**Prioridad:** 🟡 Media  
**Impacto:** Análisis de funnel incompleto

**Problema:**
- Contactos sales-led solo tienen evento "Qualification" en Mixpanel
- No hay eventos de producto hasta que usuario hace trial
- Gap de semanas/meses entre qualification y trial signup

**Acciones:**
1. Documentar gap claramente
2. Crear dashboard que combine HubSpot + Mixpanel
3. Considerar eventos adicionales desde HubSpot

---

### 💬 Intercom - Oportunidades de Mejora

#### Oportunidad 1: Pasar UTM a HubSpot
**Prioridad:** 🟡 Alta  
**Impacto:** Atribución de marketing

**Problema:**
- Intercom captura UTM cuando usuario visita website
- Integración no pasa UTM a HubSpot
- `lead_source = 'Orgánico'` cuando debería tener UTM

**Acciones:**
1. Modificar integración Intercom → HubSpot
2. Pasar `utm_source`, `utm_campaign`, `utm_medium`, etc.
3. Backfill de contactos existentes

#### Oportunidad 2: Enriquecimiento Automático de NPS
**Prioridad:** 🟡 Media  
**Impacto:** Análisis de NPS por ICP

**Estado Actual:**
- NPS responses en Intercom
- Enriquecimiento manual con HubSpot
- No hay automatización

**Acciones:**
1. Crear workflow que enriquezca NPS automáticamente
2. Sincronizar con HubSpot (contacto → empresa → ICP)
3. Dashboard de NPS por ICP

#### Oportunidad 3: Sincronización Bidireccional Completa
**Prioridad:** 🟡 Baja  
**Impacto:** Consistencia de datos

**Problema:**
- Sincronización unidireccional (Intercom → HubSpot)
- Cambios en HubSpot no se reflejan en Intercom

**Acciones:**
1. Evaluar necesidad de sincronización bidireccional
2. Implementar si es necesario para casos de uso específicos

---

## 3️⃣ PLAN DE ACCIÓN POR FASES

### Fase 1: Quick Wins - HubSpot (Semanas 1-2)

#### ✅ Tarea 1.1: Enriquecer Empresas Unknown desde Contacto
**Responsable:** [Data Engineer]  
**Esfuerzo:** 4 horas  
**Impacto:** 29 empresas (10%)

**Acción:**
- Script que identifique contactos con `es_contador = true` o `rol_wizard` contiene "contador"
- Actualizar `company.type = "Cuenta Contador"` para esas empresas
- Validar resultados

**Criterios de Éxito:**
- 29 empresas actualizadas
- 0 errores en la actualización
- Validación manual de 5 casos aleatorios

#### ✅ Tarea 1.2: Enriquecer Empresas Unknown desde Deals - Casos Simples
**Responsable:** [Data Engineer]  
**Esfuerzo:** 8 horas  
**Impacto:** ~50 empresas (17%)

**Acción:**
- Script que identifique:
  - Empresas con mismo nombre en deal
  - Empresas únicas en deals del contacto
- Actualizar `company.type` desde la empresa en deal
- Validar resultados

**Criterios de Éxito:**
- ~50 empresas actualizadas
- 0 errores en la actualización
- Validación manual de 10 casos aleatorios

#### ✅ Tarea 1.3: Crear Campos Mixpanel en HubSpot
**Responsable:** [Product Manager]  
**Esfuerzo:** 2 horas  
**Impacto:** Habilitar sincronización

**Acción:**
- Crear campos en HubSpot:
  - `mixpanel_distinct_id` (Contact + Company)
  - `mixpanel_cohort_name` (Contact + Company)
  - `mixpanel_cohort_id` (Contact + Company)
  - `mixpanel_project_id` (Contact + Company)
  - `mixpanel_session_id` (Contact)

**Criterios de Éxito:**
- 5 campos creados en Contact
- 4 campos creados en Company
- Documentación actualizada

**Total Fase 1:** ~77 empresas enriquecidas + campos creados

---

### Fase 2: Corrección de Calidad - HubSpot (Semanas 2-3)

#### ⚠️ Tarea 2.1: Análisis y Corrección de Primary Company
**Responsable:** [Customer Success + Data Engineer]  
**Esfuerzo:** 20 horas  
**Impacto:** 164 empresas (56.4%)

**Acción:**
- Revisar casos donde el contacto tiene empresas en deals con `type`
- Determinar cuál debería ser la primary company correcta
- Script que actualice primary company basándose en análisis
- Validar cambios antes de aplicar

**Criterios de Éxito:**
- 164 casos analizados
- 80%+ de casos con primary company corregida
- Script validado con casos de prueba
- Rollback plan disponible

#### ⚠️ Tarea 2.2: Inferencia Estadística para Restantes
**Responsable:** [Data Engineer]  
**Esfuerzo:** 4 horas  
**Impacto:** ~50 empresas restantes (17%)

**Acción:**
- Para empresas sin información en deals o contactos:
  - Inferir "Cuenta Pyme" (68.4% de probabilidad)
  - Marcar como "inferido" para tracking
  - Validar con muestra aleatoria

**Criterios de Éxito:**
- ~50 empresas inferidas
- Documentación de método de inferencia
- Validación de 10 casos aleatorios

**Total Fase 2:** ~164 empresas corregidas + ~50 inferidas

---

### Fase 3: Mixpanel - Propiedades y Eventos (Semanas 3-4)

#### 📝 Tarea 3.1: Crear Propiedades ICP en Mixpanel
**Responsable:** [Product Manager + Data Engineer]  
**Esfuerzo:** 8 horas  
**Impacto:** Inferencia temprana de ICP

**Acción:**
- Crear propiedades en Mixpanel:
  - `icp_hypothesis` (enumeration)
  - `icp_confidence` (number 0-100)
  - `icp_source` (enumeration)
  - `icp_secondary` (enumeration)
  - `did_key_event_early` (boolean)
  - `explored_multiempresa_early` (boolean)

**Criterios de Éxito:**
- 6 propiedades creadas
- Documentación actualizada
- Sincronización con HubSpot configurada

#### 📝 Tarea 3.2: Agregar Propiedades Faltantes al Evento Wizard
**Responsable:** [Engineering]  
**Esfuerzo:** 12 horas  
**Impacto:** Scoring de ICP desde Wizard

**Acción:**
- Modificar evento "Finalizar Wizard" para incluir:
  - `role_in_company` (desde `rol_wizard` en HubSpot)
  - `company_type` (desde `lead_company_type` en HubSpot)
  - `plan_to_implement` (desde `implementacion_wizard` en HubSpot)

**Criterios de Éxito:**
- 3 propiedades agregadas al evento
- Eventos históricos backfilled si es posible
- Validación de eventos nuevos

#### 📝 Tarea 3.3: Documentar Eventos y Propiedades Faltantes
**Responsable:** [Data Engineer]  
**Esfuerzo:** 16 horas  
**Impacto:** Documentación completa

**Acción:**
- Análisis exhaustivo del lexicon de Mixpanel
- Documentar 127 eventos faltantes
- Documentar 27 propiedades de usuario faltantes
- Categorizar y priorizar por uso

**Criterios de Éxito:**
- 100% de eventos documentados
- 100% de propiedades documentadas
- Documentación actualizada en lexicon

**Total Fase 3:** Propiedades ICP creadas + Wizard completo + Documentación completa

---

### Fase 4: Integración y Sincronización (Semanas 4-5)

#### 🔄 Tarea 4.1: Crear Propiedades ICP en HubSpot
**Responsable:** [Product Manager]  
**Esfuerzo:** 2 horas  
**Impacto:** Sincronización HubSpot ↔ Mixpanel

**Acción:**
- Crear campos en HubSpot (Contact + Company):
  - `icp_hypothesis` (enumeration)
  - `icp_confidence` (number)
  - `icp_source` (enumeration)
  - `icp_secondary` (enumeration)

**Criterios de Éxito:**
- 4 campos creados en Contact
- 4 campos creados en Company
- Documentación actualizada

#### 🔄 Tarea 4.2: Implementar Sincronización Mixpanel → HubSpot
**Responsable:** [Data Engineer]  
**Esfuerzo:** 16 horas  
**Impacto:** Sincronización automática

**Acción:**
- Implementar lógica de scoring de ICP en Mixpanel
- Crear workflow/job que sincronice propiedades ICP a HubSpot
- Implementar guard de confianza (solo actualizar si nueva confianza es mayor)
- Backfill de datos históricos

**Criterios de Éxito:**
- Sincronización funcionando en tiempo real
- Guard de confianza implementado
- Backfill completado
- Monitoreo y alertas configurados

#### 🔄 Tarea 4.3: Modificar Integración Intercom → HubSpot para UTM
**Responsable:** [Engineering]  
**Esfuerzo:** 8 horas  
**Impacto:** Atribución de marketing

**Acción:**
- Modificar integración Intercom → HubSpot
- Pasar UTM parameters cuando se crea contacto
- Backfill de contactos existentes sin UTM

**Criterios de Éxito:**
- UTM parameters pasados correctamente
- Backfill completado
- Validación de nuevos contactos

**Total Fase 4:** Sincronización completa + UTM desde Intercom

---

### Fase 5: Prevención y Validación (Semanas 5-6)

#### 🛡️ Tarea 5.1: Workflows de Validación en HubSpot
**Responsable:** [Product Manager + Data Engineer]  
**Esfuerzo:** 12 horas  
**Impacto:** Prevención futura

**Acción:**
- Crear workflows que:
  - Validen que primary company tenga `type` cuando se crea/actualiza deal
  - Alerten si primary company es Unknown
  - Sugieran empresas en deals del contacto
  - Validen churn date >= first deal date

**Criterios de Éxito:**
- Workflows implementados y activos
- Alertas funcionando
- Documentación del workflow

#### 🛡️ Tarea 5.2: Workflow de Enriquecimiento Proactivo
**Responsable:** [Product Manager + Data Engineer]  
**Esfuerzo:** 12 horas  
**Impacto:** Prevención futura

**Acción:**
- Crear workflow que:
  - Detecte empresas sin `type`
  - Busque en deals asociados del contacto
  - Enriquezca automáticamente si encuentra información

**Criterios de Éxito:**
- Workflow implementado y activo
- Enriquecimiento automático funcionando
- Documentación del workflow

#### 🛡️ Tarea 5.3: Casos Manuales Restantes
**Responsable:** [Customer Success]  
**Esfuerzo:** 8 horas  
**Impacto:** ~20 empresas restantes (7%)

**Acción:**
- Revisar casos que no se pueden enriquecer automáticamente
- Contactar clientes si es necesario
- Actualizar manualmente en HubSpot

**Criterios de Éxito:**
- 20 casos revisados
- 80%+ de casos resueltos
- Documentación de casos no resueltos

**Total Fase 5:** Prevención implementada + Casos manuales resueltos

---

## 4️⃣ ASIGNACIÓN DE RESPONSABILIDADES

### Roles y Responsabilidades

| Rol | Responsabilidades | Tiempo Estimado |
|-----|------------------|-----------------|
| **Data Engineer** | Scripts de enriquecimiento, sincronización, documentación | 80 horas |
| **Product Manager** | Coordinación, creación de campos, validación | 24 horas |
| **Engineering** | Modificaciones de integraciones, eventos Mixpanel | 20 horas |
| **Customer Success** | Análisis manual, validación de casos | 24 horas |
| **Sales** | Validación de casos complejos, conocimiento de clientes | 8 horas |

### Equipo Strike Team

**Líder del Proyecto:** [Nombre]  
**Data Lead:** [Nombre]  
**Product Lead:** [Nombre]  
**Engineering Lead:** [Nombre]  
**Customer Success Lead:** [Nombre]  
**Sales Lead:** [Nombre]

### Comunicación

- **Daily Standup:** 15 min diarios (últimas 4 semanas)
- **Weekly Review:** 30 min semanales
- **Slack Channel:** #strike-team-data-quality

---

## 5️⃣ TIMELINE Y MÉTRICAS

### Timeline

```
Semanas 1-2: Quick Wins - HubSpot
├── Tarea 1.1: Enriquecer desde Contacto (4h)
├── Tarea 1.2: Enriquecer desde Deals (8h)
└── Tarea 1.3: Crear Campos Mixpanel (2h)
    → Objetivo: 77 empresas enriquecidas + campos creados

Semanas 2-3: Corrección de Calidad - HubSpot
├── Tarea 2.1: Análisis y Corrección Primary Company (20h)
└── Tarea 2.2: Inferencia Estadística (4h)
    → Objetivo: 164 empresas corregidas + 50 inferidas

Semanas 3-4: Mixpanel - Propiedades y Eventos
├── Tarea 3.1: Crear Propiedades ICP (8h)
├── Tarea 3.2: Agregar Propiedades al Wizard (12h)
└── Tarea 3.3: Documentar Eventos/Propiedades (16h)
    → Objetivo: Propiedades ICP + Wizard completo + Documentación

Semanas 4-5: Integración y Sincronización
├── Tarea 4.1: Crear Propiedades ICP en HubSpot (2h)
├── Tarea 4.2: Sincronización Mixpanel → HubSpot (16h)
└── Tarea 4.3: UTM desde Intercom (8h)
    → Objetivo: Sincronización completa + UTM

Semanas 5-6: Prevención y Validación
├── Tarea 5.1: Workflows de Validación (12h)
├── Tarea 5.2: Workflow de Enriquecimiento Proactivo (12h)
└── Tarea 5.3: Casos Manuales (8h)
    → Objetivo: Prevención + Casos manuales resueltos
```

### Métricas de Éxito

| Métrica | Baseline | Objetivo | Target |
|---------|----------|----------|--------|
| **HubSpot - Empresas Unknown** | 291 (31.7%) | <100 (10%) | <50 (5%) |
| **HubSpot - Empresas enriquecidas automáticamente** | 0 (0%) | 160 (55%) | 200 (69%) |
| **HubSpot - Contactos con primary company correcta** | 127 (43.6%) | 255 (87.6%) | 270 (93%) |
| **Mixpanel - Eventos documentados** | 223 (64%) | 350 (100%) | 350 (100%) |
| **Mixpanel - Propiedades de usuario documentadas** | 38 (58%) | 65 (100%) | 65 (100%) |
| **Mixpanel - Propiedades ICP creadas** | 0 (0%) | 6 (100%) | 6 (100%) |
| **Intercom - Contactos con UTM** | ~0% | 100% (nuevos) | 100% (nuevos + backfill) |
| **Integración - Sincronización Mixpanel ↔ HubSpot** | 0% | 100% | 100% |

### KPIs de Seguimiento

1. **Tasa de Enriquecimiento Diaria** (HubSpot)
   - Objetivo: 20-30 empresas/día en Fase 1-2
   - Tracking: Dashboard diario

2. **Tasa de Documentación** (Mixpanel)
   - Objetivo: 10-15 eventos/propiedades documentados por día
   - Tracking: Revisión semanal

3. **Tasa de Sincronización** (Integración)
   - Objetivo: 100% de propiedades ICP sincronizadas
   - Tracking: Monitoreo en tiempo real

4. **Tasa de Prevención** (Workflows)
   - Objetivo: 0 nuevas empresas Unknown después de Fase 5
   - Tracking: Monitoreo semanal

---

## 6️⃣ RIESGOS Y MITIGACIONES

### Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **Actualizaciones incorrectas** | Media | Alto | Validación manual de casos críticos, rollback plan |
| **Tiempo insuficiente** | Alta | Medio | Priorizar casos de alto impacto, escalar equipo si es necesario |
| **Resistencia del equipo** | Baja | Medio | Comunicación clara de beneficios, involucrar desde el inicio |
| **Casos complejos sin resolver** | Media | Bajo | Documentar casos, plan de seguimiento post-strike team |
| **Cambios en integraciones afectan producción** | Media | Alto | Testing exhaustivo, rollback plan, deployment gradual |
| **Documentación de Mixpanel incompleta** | Baja | Medio | Acceso directo al lexicon, consultar con equipo de producto |

---

## 7️⃣ PRÓXIMOS PASOS

### Inmediatos (Esta Semana)

1. ✅ **Aprobar plan de acción**
   - Revisar y ajustar timeline
   - Confirmar recursos y disponibilidad

2. ✅ **Formar Strike Team**
   - Asignar roles y responsabilidades
   - Crear canal de comunicación

3. ✅ **Kickoff Meeting**
   - Alinear en objetivos y métricas
   - Iniciar Fase 1

### Semana 1

1. ✅ **Iniciar Tareas 1.1, 1.2, 1.3**
   - Desarrollar scripts de enriquecimiento
   - Crear campos en HubSpot
   - Validar con casos de prueba

2. ✅ **Daily Standups**
   - Tracking de progreso
   - Identificar bloqueos temprano

---

## 8️⃣ RECURSOS Y DOCUMENTACIÓN

### Documentos de Referencia

- [Análisis Profundo de Empresas Unknown](tools/docs/UNKNOWN_COMPANIES_DEEP_ANALYSIS.md)
- [Flujo de Datos NPS a ICP](tools/docs/NPS_TO_ICP_DATA_FLOW.md)
- [Configuración HubSpot](tools/docs/README_HUBSPOT_CONFIGURATION.md)
- [Lexicon Mixpanel](tools/docs/MIXPANEL_LEXICON_CONFIG.md)
- [Eventos Mixpanel](tools/docs/MIXPANEL_EVENTS_CONFIG.md)
- [Propiedades Usuario Mixpanel](tools/docs/MIXPANEL_USER_PROPERTIES_CONFIG.md)
- [Intercom Consolidado](tools/docs/README_INTERCOM_CONSOLIDATED.md)
- [Funnel Mapping Completo](tools/docs/COLPPY_FUNNEL_MAPPING_COMPLETE.md)

### Datos y Scripts

- **Datos de Análisis:** `tools/outputs/nps_icp_data_quality/unknown_companies_deep_analysis.json`
- **Scripts Base:** 
  - `tools/scripts/intercom/analyze_nps_icp_data_quality.py`
  - `tools/scripts/hubspot/` (varios scripts)
- **Workflows HubSpot:** `tools/scripts/hubspot/custom_code/hubspot_first_deal_won_calculations.js`

### Herramientas

- HubSpot API
- Mixpanel API
- Intercom API
- Python scripts para enriquecimiento
- HubSpot Workflows para prevención
- Slack para comunicación

---

## 9️⃣ PREGUNTAS Y DECISIONES PENDIENTES

### Preguntas para Discutir

1. **¿Cuál es la prioridad entre plataformas?**
   - ¿HubSpot primero, luego Mixpanel, luego Intercom?
   - ¿O trabajar en paralelo?

2. **¿Qué nivel de validación necesitamos?**
   - ¿Validación manual de todos los casos o muestra aleatoria?
   - ¿Quién aprueba los cambios masivos?

3. **¿Cómo manejamos casos complejos?**
   - ¿Cuándo contactamos al cliente?
   - ¿Cuándo inferimos vs. dejamos Unknown?

4. **¿Qué hacemos con empresas duplicadas?**
   - ¿Consolidamos o mantenemos separadas?
   - ¿Cuál es el proceso de deduplicación?

5. **¿Cómo priorizamos eventos/propiedades de Mixpanel?**
   - ¿Por frecuencia de uso?
   - ¿Por impacto en análisis?

6. **¿Cuál es la estrategia de backfill?**
   - ¿Cuántos meses de datos históricos?
   - ¿Priorizamos casos activos vs. históricos?

### Decisiones Requeridas

- [ ] Aprobar plan de acción y timeline
- [ ] Asignar recursos y responsabilidades
- [ ] Definir criterios de validación
- [ ] Establecer proceso de aprobación de cambios
- [ ] Definir estrategia para casos complejos
- [ ] Priorizar eventos/propiedades de Mixpanel
- [ ] Definir estrategia de backfill

---

## 🎯 RESUMEN EJECUTIVO

### El Problema
Problemas de calidad de datos en las tres plataformas (HubSpot, Mixpanel, Intercom) que impiden análisis completos y toma de decisiones basada en datos.

### La Solución
Plan de 6 semanas para:
1. Enriquecer y corregir datos en HubSpot (291 empresas Unknown)
2. Documentar y completar datos en Mixpanel (127 eventos, 27 propiedades)
3. Mejorar integración Intercom → HubSpot (UTM parameters)
4. Implementar sincronización bidireccional entre plataformas
5. Crear workflows de prevención

### El Impacto
- Habilitar análisis completo de NPS por ICP
- Inferencia temprana de ICP para personalización
- Atribución completa de marketing
- Documentación completa de eventos y propiedades
- Prevención de problemas futuros

### El Compromiso
- 6 semanas de trabajo intensivo
- 156 horas totales de esfuerzo
- Equipo multidisciplinario (Data, Product, Engineering, CS, Sales)

---

**Preparado por:** [Nombre]  
**Fecha:** [Fecha]  
**Versión:** 2.0

---

## 📝 NOTAS DE LA REUNIÓN

### Asistentes
- [ ] [Nombre] - [Rol]
- [ ] [Nombre] - [Rol]
- [ ] [Nombre] - [Rol]

### Decisiones Tomadas
1. [Decisión 1]
2. [Decisión 2]
3. [Decisión 3]

### Acciones Inmediatas
- [ ] [Acción] - [Responsable] - [Fecha]
- [ ] [Acción] - [Responsable] - [Fecha]
- [ ] [Acción] - [Responsable] - [Fecha]

### Próxima Reunión
- **Fecha:** [Fecha]
- **Hora:** [Hora]
- **Agenda:** [Temas a discutir]
