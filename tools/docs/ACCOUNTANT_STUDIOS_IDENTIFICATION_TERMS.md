# Términos de Identificación de Estudios Contables - RNS Dataset

**Script:** `tools/scripts/analyze_accountant_studios_rns.py`  
**Última actualización:** 2025-01-05  
**Propósito:** Documentar todos los términos, keywords y códigos utilizados para identificar estudios contables en el dataset RNS (Registro Nacional de Sociedades)

---

## 📋 Resumen

El script identifica estudios contables basándose en **múltiples criterios** que se evalúan de forma independiente. Una empresa se considera estudio contable si cumple **CUALQUIERA** de los siguientes criterios:

1. **Nombre de la empresa** (`razon_social`) contiene keywords de contador
2. **Descripción de actividad** (`actividad_descripcion`) contiene keywords de contabilidad/impuestos/sueldos
3. **Descripción de actividad** contiene códigos AFIP de servicios contables

El campo **`actividad_descripcion`** es el **más confiable** para identificar la industria/actividad de la empresa.

---

## 🔍 Criterio 1: Keywords en Nombre de Empresa

**Variable en script:** `ACCOUNTANT_KEYWORDS`  
**Campo evaluado:** `razon_social` (razón social de la empresa)  
**Ubicación en código:** Líneas 22-38

### Lista de Términos:

| # | Término | Descripción |
|---|---------|-------------|
| 1 | `estudio contable` | Estudio contable |
| 2 | `estudio de contadores` | Estudio de contadores |
| 3 | `estudio contador` | Estudio contador |
| 4 | `contador público` | Contador público |
| 5 | `contadores públicos` | Contadores públicos |
| 6 | `asesor contable` | Asesor contable |
| 7 | `asesores contables` | Asesores contables |
| 8 | `consultor contable` | Consultor contable |
| 9 | `consultores contables` | Consultores contables |
| 10 | `servicios contables` | Servicios contables |
| 11 | `servicio contable` | Servicio contable |
| 12 | `contaduría` | Contaduría |
| 13 | `contaduria` | Contaduría (sin tilde) |
| 14 | `contador` | Contador |
| 15 | `contadores` | Contadores |

**Total:** 15 términos

**Nota:** La búsqueda es **case-insensitive** (no distingue mayúsculas/minúsculas) y busca coincidencias como palabras completas o substrings.

---

## 🔍 Criterio 2: Keywords en Descripción de Actividad

**Variable en script:** `ACCOUNTANT_ACTIVITY_KEYWORDS`  
**Campo evaluado:** `actividad_descripcion` (descripción de la actividad económica)  
**Ubicación en código:** Líneas 41-77  
**Importancia:** ⭐ **CAMPO PRIMARIO** para identificación de industria

### Lista de Términos:

#### A. Términos de Contabilidad General

| # | Término | Descripción |
|---|---------|-------------|
| 1 | `contable` | Contable |
| 2 | `contador` | Contador |
| 3 | `contadores` | Contadores |
| 4 | `contaduría` | Contaduría |
| 5 | `contaduria` | Contaduría (sin tilde) |
| 6 | `asesoría contable` | Asesoría contable |
| 7 | `asesoria contable` | Asesoría contable (sin tilde) |
| 8 | `servicios contables` | Servicios contables |
| 9 | `servicio contable` | Servicio contable |
| 10 | `auditoría` | Auditoría |
| 11 | `auditoria` | Auditoría (sin tilde) |
| 12 | `consultoría contable` | Consultoría contable |
| 13 | `consultoria contable` | Consultoría contable (sin tilde) |

#### B. Términos de Impuestos y Fiscal

| # | Término | Descripción |
|---|---------|-------------|
| 14 | `tributaria` | Tributaria |
| 15 | `tributario` | Tributario |
| 16 | `impuestos` | Impuestos |
| 17 | `impuesto` | Impuesto |
| 18 | `fiscal` | Fiscal |
| 19 | `societaria` | Societaria |
| 20 | `societario` | Societario |

#### C. Términos de Liquidación de Sueldos

| # | Término | Descripción |
|---|---------|-------------|
| 21 | `liquidaci` | Liquidación (raíz, captura variantes) |
| 22 | `sueldo` | Sueldo |
| 23 | `sueldos` | Sueldos |
| 24 | `nómina` | Nómina |
| 25 | `nomina` | Nómina (sin tilde) |
| 26 | `jornales` | Jornales |
| 27 | `jornal` | Jornal |
| 28 | `cargas sociales` | Cargas sociales |
| 29 | `carga social` | Carga social |
| 30 | `convenio colectivo` | Convenio colectivo |
| 31 | `convenios colectivos` | Convenios colectivos |
| 32 | `remuneraci` | Remuneración (raíz, captura variantes) |
| 33 | `haberes` | Haberes |
| 34 | `haber` | Haber |

**Total:** 34 términos

**Nota:** Algunos términos usan raíces (ej: `liquidaci`, `remuneraci`) para capturar variantes como "liquidación", "liquidaciones", "remuneración", "remuneraciones", etc.

---

## 🔍 Criterio 3: Códigos AFIP de Actividad

**Variable en script:** `ACCOUNTING_ACTIVITY_CODES`  
**Campo evaluado:** `actividad_descripcion` o `actividad_codigo`  
**Ubicación en código:** Líneas 80-88

### Lista de Códigos AFIP:

| Código | Descripción del Servicio |
|--------|--------------------------|
| `692200` | Servicios de contabilidad, auditoría y asesoría fiscal |
| `692201` | Servicios de contabilidad |
| `692202` | Servicios de auditoría |
| `692203` | Servicios de asesoría fiscal |
| `692204` | Servicios de asesoría contable |
| `692205` | Servicios de asesoría tributaria |
| `692206` | Servicios de asesoría societaria |

**Total:** 7 códigos AFIP

**Fuente:** Clasificación de Actividades Económicas de AFIP (Administración Federal de Ingresos Públicos)

---

## 🚫 Patrones Excluidos (Falsos Positivos)

**Variable en script:** `EXCLUDED_ACTIVITY_PATTERNS`  
**Campo evaluado:** `actividad_descripcion`  
**Ubicación en código:** Líneas 91-109

### Lista de Patrones a Excluir:

#### A. Gestión Fiscal (No Contable)

| # | Patrón | Razón de Exclusión |
|---|--------|-------------------|
| 1 | `gestión de depósitos fiscal` | Gestión de depósitos fiscales (no es contabilidad) |
| 2 | `gestión de depósitos` | Variante - gestión de depósitos |
| 3 | `depósito fiscal` | Depósito fiscal (no es contabilidad) |
| 4 | `deposito fiscal` | Depósito fiscal (sin tilde) |

#### B. Actividades Agrícolas/Ganaderas

| # | Patrón | Razón de Exclusión |
|---|--------|-------------------|
| 5 | `cultivo` | Actividades agrícolas (pueden contener "contable" en otros contextos) |
| 6 | `cría de ganado` | Actividades ganaderas |
| 7 | `apicultura` | Actividades apícolas |

#### C. Otras Actividades No Contables

| # | Patrón | Razón de Exclusión |
|---|--------|-------------------|
| 8 | `alquiler de automóviles` | Alquiler de vehículos |
| 9 | `transporte automotor` | Transporte |
| 10 | `producción de filmes` | Producción cinematográfica |
| 11 | `venta al por` | Comercio minorista |
| 12 | `construcción` | Construcción |
| 13 | `edificios residenciales` | Construcción residencial |
| 14 | `edificios no residenciales` | Construcción comercial |

**Total:** 14 patrones excluidos

**Nota:** Estos patrones se excluyen porque aunque pueden contener palabras relacionadas (ej: "fiscal"), no representan servicios contables reales.

---

## 🔧 Lógica de Identificación

### Algoritmo de Matching:

1. **Normalización:** Todo el texto se convierte a minúsculas y se eliminan espacios extra
2. **Búsqueda por Palabras Completas:** Se busca coincidencias usando límites de palabra (`\b` en regex)
3. **Búsqueda por Substring:** También se busca como substring para capturar palabras compuestas
4. **Combinación OR:** Una empresa es identificada como estudio contable si cumple **CUALQUIERA** de los criterios:
   - ✅ Nombre contiene keywords **O**
   - ✅ Actividad contiene keywords **O**
   - ✅ Actividad contiene códigos AFIP
5. **Exclusión:** Si la actividad coincide con un patrón excluido, se descarta aunque tenga keywords

### Ejemplo de Matching:

```
Empresa: "Estudio Contable ABC SRL"
Actividad: "Servicios de contabilidad y asesoría fiscal"

Resultado: ✅ IDENTIFICADO COMO ESTUDIO CONTABLE
- Match por nombre: ✅ (contiene "estudio contable")
- Match por actividad: ✅ (contiene "contabilidad" y "fiscal")
- Match por código: ❌ (no contiene códigos AFIP explícitos)
```

---

## 📊 Estadísticas de Uso (Última Ejecución)

**Script:** `analyze_accountant_studios_rns.py`  
**Dataset:** RNS (Registro Nacional de Sociedades)  
**Fecha de análisis:** 2025-01-05

### Resultados:

- **Total empresas en dataset:** ~2.4M
- **Estudios contables identificados:** 5,065
- **Porcentaje del total:** 0.21%

### Breakdown por Criterio de Match:

| Criterio | Cantidad | % del Total |
|----------|----------|-------------|
| Match por nombre de empresa | ~X | ~X% |
| Match por actividad (keywords) | ~X | ~X% |
| Match por código AFIP | ~X | ~X% |
| Match múltiple (nombre + actividad) | ~X | ~X% |

*Nota: Ejecutar el script para obtener estadísticas actualizadas*

---

## 📝 Notas Importantes

### 1. Campo Primario: `actividad_descripcion`

El campo **`actividad_descripcion`** es el **más confiable** para identificar la industria/actividad de una empresa. Este campo contiene la descripción oficial de la actividad económica según AFIP.

### 2. Variantes con/sin Tilde

Los términos incluyen variantes con y sin tilde para capturar todas las formas posibles:
- `contaduría` / `contaduria`
- `asesoría` / `asesoria`
- `auditoría` / `auditoria`
- `nómina` / `nomina`

### 3. Raíces de Palabras

Algunos términos usan raíces para capturar variantes:
- `liquidaci` → captura "liquidación", "liquidaciones", "liquidar", etc.
- `remuneraci` → captura "remuneración", "remuneraciones", etc.

### 4. Inclusión de Liquidación de Sueldos

Los términos de liquidación de sueldos están incluidos porque muchos estudios contables también ofrecen servicios de liquidación de sueldos, lo cual es relevante para el análisis de mercado de Colppy.

### 5. Patrones Excluidos

Los patrones excluidos son necesarios para evitar falsos positivos. Por ejemplo:
- "Gestión de depósitos fiscales" contiene "fiscal" pero no es un servicio contable
- "Cultivo de maíz" podría coincidir con "contable" en otros contextos

---

## 🔄 Mantenimiento y Actualización

### Cuándo Actualizar:

1. **Nuevos términos identificados:** Si se encuentran estudios contables que no se están capturando
2. **Falsos positivos:** Si se identifican empresas que no son estudios contables pero están siendo capturadas
3. **Nuevos códigos AFIP:** Si AFIP agrega nuevos códigos de actividad para servicios contables
4. **Cambios en el dataset:** Si la estructura del dataset RNS cambia

### Cómo Actualizar:

1. Editar el script: `tools/scripts/analyze_accountant_studios_rns.py`
2. Agregar/remover términos en las listas correspondientes:
   - `ACCOUNTANT_KEYWORDS` (líneas 22-38)
   - `ACCOUNTANT_ACTIVITY_KEYWORDS` (líneas 41-77)
   - `ACCOUNTING_ACTIVITY_CODES` (líneas 80-88)
   - `EXCLUDED_ACTIVITY_PATTERNS` (líneas 91-109)
3. Ejecutar el script para validar los cambios
4. Actualizar esta documentación

---

## 📚 Referencias

- **Script:** `/Users/virulana/openai-cookbook/tools/scripts/analyze_accountant_studios_rns.py`
- **Dataset RNS:** Registro Nacional de Sociedades (Argentina)
- **Códigos AFIP:** Clasificación de Actividades Económicas - AFIP
- **Documentación relacionada:** 
  - [Análisis de Mercado TAM](link-to-tam-analysis)
  - [ICP Contadores](link-to-icp-doc)

---

## ✅ Checklist de Validación

Antes de usar estos términos en producción:

- [ ] Revisar que todos los términos estén correctamente escritos
- [ ] Validar que los códigos AFIP sean correctos
- [ ] Verificar que los patrones excluidos no estén eliminando estudios contables válidos
- [ ] Ejecutar el script con una muestra del dataset para validar resultados
- [ ] Revisar los ejemplos de matching para asegurar calidad

---

**Última revisión:** 2025-01-05  
**Responsable:** Equipo de Data & Analytics  
**Contacto:** Para sugerencias o correcciones, contactar al equipo de producto

