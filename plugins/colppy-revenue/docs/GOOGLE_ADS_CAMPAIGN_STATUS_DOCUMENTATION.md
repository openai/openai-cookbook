# 📊 Google Ads Campaign Status Documentation

**Fecha:** 8 de septiembre de 2025  
**Propósito:** Explicar los diferentes estados de campañas en Google Ads API vs Interface

---

## 🔍 **ESTADOS DE CAMPAÑAS EN GOOGLE ADS**

### **📋 CAMPOS DE ESTADO PRINCIPALES:**

#### **1. `campaign.status` (Estado del Usuario)**
- **ENABLED:** El usuario ha habilitado la campaña manualmente
- **PAUSED:** El usuario ha pausado la campaña manualmente  
- **REMOVED:** El usuario ha eliminado la campaña

#### **2. `campaign.serving_status` (Estado de Servicio)**
- **SERVING:** La campaña está sirviendo anuncios actualmente
- **NONE:** La campaña no está sirviendo anuncios
- **ENDED:** La campaña ha terminado (fechas de inicio/fin)

#### **3. `campaign.primary_status` (Estado Primario)**
- **ELIGIBLE:** Campaña elegible para servir anuncios
- **PAUSED:** Campaña pausada por el usuario
- **ENDED:** Campaña terminada por fechas
- **LIMITED:** Campaña con restricciones pero sirviendo
- **LEARNING:** Campaña en fase de aprendizaje
- **REMOVED:** Campaña eliminada

---

## 🚨 **CASOS ESPECIALES: "TÉCNICAMENTE ENABLED"**

### **❌ CAMPAÑAS CON `status = 'ENABLED'` PERO NO SIRVIENDO:**

#### **Caso 1: Campañas con Fechas de Fin**
```
campaign.status = 'ENABLED'          ✅ Usuario la habilitó
campaign.serving_status = 'ENDED'    ❌ Terminó por fechas
campaign.primary_status = 'ENDED'    ❌ No puede servir más
```

**Ejemplo:** `Search_SistemasDeGestión_Leads_ARG Prueba 327`
- El usuario nunca la pausó manualmente
- Pero tiene fecha de fin configurada que ya pasó
- Por eso aparece como "ENABLED" en la API pero no sirve anuncios

#### **Caso 2: Campañas con Restricciones**
```
campaign.status = 'ENABLED'          ✅ Usuario la habilitó
campaign.serving_status = 'SERVING' ✅ Está sirviendo
campaign.primary_status = 'LIMITED' ⚠️ Con restricciones
```

**Ejemplo:** `Android App promotion-App-1`
- Está sirviendo anuncios
- Pero tiene restricciones (presupuesto, targeting, etc.)

---

## 📊 **FILTROS DE LA INTERFAZ GOOGLE ADS**

### **🎯 CRITERIOS QUE USA LA INTERFAZ:**

La interfaz de Google Ads filtra automáticamente las campañas usando:

1. **`campaign.status = 'ENABLED'`** - Solo campañas habilitadas por el usuario
2. **`campaign.serving_status = 'SERVING'`** - Solo campañas sirviendo anuncios HOY
3. **Excluye automáticamente:** Campañas con `primary_status = 'ENDED'`

### **✅ RESULTADO:**
- **API devuelve:** Todas las campañas con `status = 'ENABLED'`
- **Interfaz muestra:** Solo campañas que están sirviendo anuncios HOY

---

## 🔧 **QUERIES RECOMENDADAS**

### **Para Obtener Campañas Activas (Como la Interfaz):**
```sql
SELECT campaign.name, campaign.status, campaign.serving_status, campaign.primary_status, metrics.impressions, metrics.clicks, metrics.conversions 
FROM campaign 
WHERE segments.date DURING LAST_7_DAYS 
AND campaign.status = 'ENABLED' 
AND campaign.serving_status = 'SERVING'
ORDER BY metrics.impressions DESC
```

### **Para Obtener Todas las Campañas Habilitadas:**
```sql
SELECT campaign.name, campaign.status, campaign.serving_status, campaign.primary_status 
FROM campaign 
WHERE segments.date DURING LAST_7_DAYS 
AND campaign.status = 'ENABLED'
ORDER BY campaign.name
```

---

## 📈 **EJEMPLOS PRÁCTICOS**

### **✅ CAMPAÑAS REALMENTE ACTIVAS:**
```
Android App promotion-App-1
- status: ENABLED ✅
- serving_status: SERVING ✅  
- primary_status: LIMITED ⚠️
- Resultado: Aparece en interfaz
```

### **❌ CAMPAÑAS "TÉCNICAMENTE ENABLED":**
```
Search_SistemasDeGestión_Leads_ARG Prueba 327
- status: ENABLED ✅
- serving_status: ENDED ❌
- primary_status: ENDED ❌
- Resultado: NO aparece en interfaz
```

---

## 🎯 **RECOMENDACIONES**

### **Para Análisis de Performance:**
- Usar solo campañas con `serving_status = 'SERVING'`
- Ignorar campañas con `primary_status = 'ENDED'`

### **Para Gestión de Campañas:**
- Revisar campañas con `status = 'ENABLED'` pero `serving_status = 'ENDED'`
- Pueden necesitar reactivación o eliminación

### **Para Reportes Ejecutivos:**
- Usar el mismo filtro que la interfaz de Google Ads
- Garantiza consistencia entre API y UI

---

## 📚 **REFERENCIAS**

- [Google Ads API - Campaign Status](https://developers.google.com/google-ads/api/reference/rpc/v21/Campaign)
- [Campaign Status Values](https://developers.google.com/google-ads/api/reference/rpc/v21/CampaignStatusEnum)
- [Serving Status Values](https://developers.google.com/google-ads/api/reference/rpc/v21/CampaignServingStatusEnum)

---

**Última actualización:** 8 de septiembre de 2025  
**Autor:** AI Assistant - Colppy Google Ads Analysis

