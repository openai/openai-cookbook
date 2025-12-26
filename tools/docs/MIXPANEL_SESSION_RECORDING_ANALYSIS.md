# Mixpanel Session Recording - Complete Analysis

**Project:** Colppy  
**Date:** 2024-12-24  
**Status:** ✅ Complete Analysis

---

## Executive Summary

Mixpanel session recording is **triggered automatically** when users access the Colppy workspace in the **LIVE environment**. The recording is started via `mixpanel.start_session_recording()` and Mixpanel automatically tracks each recording as a `$mp_session_record` event.

---

## 🔍 Where Session Recording is Triggered

### Primary Location: `Workspace.js`

**File:** `/Users/virulana/colppy-app/resources/js/ColppyManager/Workspace.js`

**Line:** 2771-2773

```2769:2773:colppy-app/resources/js/ColppyManager/Workspace.js
            console.log("ENV", env) //Para monitorear en test

            if (env == 'LIVE') {
                mixpanel.start_session_recording();
            }
```

### Context: When This Code Executes

This code runs in the `ColppyManager.workspace.init()` function, specifically after:
1. User successfully logs in
2. Company data is loaded (`GlobalesEmpresa` function completes)
3. Workspace UI is initialized
4. Chat functionality is checked (`chequearSiSePuedeVerElChat()`)

**Full context:**
```2746:2775:colppy-app/resources/js/ColppyManager/Workspace.js
            else {
                wrc = Ext.getCmp('center_region');
                prevType = moduloInicial;
                wrc.remove('center_region_proveedores');
                Cerrar_Windows();
                wrc.add({
                    id: 'center_region_proveedores',
                    xtype: moduloInicial
                });
                wrc.doLayout();
                btn = Ext.getCmp(btnInicial);
                if (!btn.pressed) {
                    btn.toggle(true, true);
                }

                colppyAnalytics(idEmpresaUsuario, 'record', 'Visualizó inicio colppy', {}, 'intercom');
            }

            chequearSiSePuedeVerElChat();

            // if ((idPlanEmpresa == 1) || (idEmpresaUsuario == idEmpresaDemo || (RECORD_MIXPANEL == 1))) {
            //     mixpanel.start_session_recording();
            // }
            console.log("ENV", env) //Para monitorear en test

            if (env == 'LIVE') {
                mixpanel.start_session_recording();
            }

            loadProvinciasApi();
```

---

## 🎛️ How Recording is Controlled

### Current Implementation (Active)

**Condition:** Environment-based
- **Triggers when:** `env == 'LIVE'`
- **Does NOT trigger when:** `env != 'LIVE'` (e.g., TEST, DEV, LOCAL)

### Previous Implementation (Commented Out)

**Lines:** 2766-2768 (commented)

```2766:2768:colppy-app/resources/js/ColppyManager/Workspace.js
            // if ((idPlanEmpresa == 1) || (idEmpresaUsuario == idEmpresaDemo || (RECORD_MIXPANEL == 1))) {
            //     mixpanel.start_session_recording();
            // }
```

**Previous conditions (now disabled):**
1. `idPlanEmpresa == 1` - Plan ID 1 (specific plan)
2. `idEmpresaUsuario == idEmpresaDemo` - Demo company
3. `RECORD_MIXPANEL == 1` - Database flag enabled

### Database Flag (Available but Not Used)

**Migration:** `/Users/virulana/colppy-benjamin/database/migrations/2025_02_13_104650_KAN-11316_record_mixpanel.php`

```php
Schema::table('empresa', function (Blueprint $table) {
    $table->boolean('recordMixPanel')->default(0)->nullable()->after('estrategiaBk');
});
```

**Variable:** `RECORD_MIXPANEL` is set from backend response:
```407:407:colppy-app/resources/js/ColppyManager/Workspace.js
    RECORD_MIXPANEL = response.recordMixPanel;
```

**Status:** This flag exists in the database but is **not currently used** in the active code.

---

## 📊 How Mixpanel Calculates Recordings

### Automatic Event: `$mp_session_record`

When `mixpanel.start_session_recording()` is called, Mixpanel automatically:

1. **Starts recording** the user's session using their session replay technology
2. **Generates a `$mp_session_record` event** when the recording is complete
3. **Attaches metadata** to the event with recording details

### Event Properties

The `$mp_session_record` event includes these properties:

| Property | Type | Description |
|----------|------|-------------|
| `replay_length_ms` | Number | Duration of the recording in milliseconds |
| `replay_env` | String | Environment where recording occurred |
| `replay_region` | String | Geographic region |
| `replay_start_time` | String | When recording started |
| `replay_start_url` | String | URL where recording began |
| `replay_version` | String | Version of replay technology |
| `$user_agent` | String | Browser user agent |
| `$mp_replay_retention_period` | String | How long recording will be retained |
| `seq_no` | Number | Sequence number |
| `batch_start_time` | String | Batch processing timestamp |

### Counting Recordings

**Mixpanel counts recordings by counting `$mp_session_record` events:**

1. **Each call to `start_session_recording()`** = 1 potential recording
2. **Each completed recording** = 1 `$mp_session_record` event
3. **Total recordings** = Count of unique `$mp_session_record` events

**Note:** Not every `start_session_recording()` call results in a recording:
- User must have sufficient session activity
- Recording must meet Mixpanel's minimum duration thresholds
- User must not have opted out

---

## 🔄 Recording Flow

### Complete Flow Diagram

```
1. User logs into Colppy
   ↓
2. Backend returns company data (GlobalesEmpresa)
   ↓
3. Workspace.init() executes
   ↓
4. Check environment: env == 'LIVE'?
   ├─ YES → mixpanel.start_session_recording()
   └─ NO  → Skip recording
   ↓
5. Mixpanel SDK starts recording session
   ↓
6. User interacts with application
   ↓
7. Recording ends (session ends or timeout)
   ↓
8. Mixpanel generates $mp_session_record event
   ↓
9. Event appears in Mixpanel dashboard
```

---

## 📍 Key Code Locations

### 1. Recording Trigger
- **File:** `colppy-app/resources/js/ColppyManager/Workspace.js`
- **Line:** 2772
- **Function:** `ColppyManager.workspace.init`

### 2. Environment Variable
- **Variable:** `env`
- **Set:** Likely in PHP backend or JavaScript initialization
- **Values:** `'LIVE'`, `'TEST'`, `'DEV'`, `'LOCAL'` (inferred)

### 3. Database Flag (Unused)
- **Table:** `empresa`
- **Column:** `recordMixPanel` (boolean)
- **Migration:** `2025_02_13_104650_KAN-11316_record_mixpanel.php`

### 4. Mixpanel Initialization
- **Location:** Mixpanel SDK loaded via script tag in `index.php`
- **Version:** Mixpanel Browser SDK (likely v2.70+ for session recording support)

---

## 🎯 Current Behavior

### What Happens Now

1. **Every user** who logs into Colppy in the **LIVE environment** gets session recording started
2. **No filtering** by plan, company type, or database flag
3. **All recordings** are sent to Mixpanel
4. **Mixpanel counts** each `$mp_session_record` event as one recording

### Recording Scope

- **Environment:** LIVE only
- **Users:** All users in LIVE environment
- **Frequency:** Once per session (when workspace initializes)
- **Duration:** Until session ends or timeout

---

## 💡 Recommendations

### 1. Understand Recording Costs

Mixpanel charges based on:
- **Number of recordings** (`$mp_session_record` events)
- **Recording duration** (`replay_length_ms`)
- **Storage** (retention period)

### 2. Consider Selective Recording

If costs are a concern, you could:

**Option A: Use Database Flag**
```javascript
if (env == 'LIVE' && RECORD_MIXPANEL == 1) {
    mixpanel.start_session_recording();
}
```

**Option B: Filter by Plan**
```javascript
if (env == 'LIVE' && (idPlanEmpresa == 1 || esEmpresaDemo)) {
    mixpanel.start_session_recording();
}
```

**Option C: Sample Recording**
```javascript
if (env == 'LIVE' && Math.random() < 0.1) { // 10% sample
    mixpanel.start_session_recording();
}
```

### 3. Monitor Recording Counts

Query Mixpanel to see actual recording counts:

```javascript
// JQL Query to count recordings
function main() {
    return Events({
        from_date: "2024-11-01",
        to_date: "2024-11-30"
    })
    .filter(function(event) {
        return event.name === "$mp_session_record";
    })
    .groupBy(["name"], mixpanel.reducer.count());
}
```

---

## 📋 Summary

| Aspect | Details |
|--------|---------|
| **Trigger Location** | `Workspace.js` line 2772 |
| **Trigger Condition** | `env == 'LIVE'` |
| **Method Called** | `mixpanel.start_session_recording()` |
| **Event Generated** | `$mp_session_record` |
| **Recording Count** | Count of `$mp_session_record` events |
| **Current Scope** | All users in LIVE environment |
| **Previous Control** | Plan ID, Demo flag, DB flag (all disabled) |

---

## 🔗 Related Files

1. **Main Trigger:** `colppy-app/resources/js/ColppyManager/Workspace.js:2772`
2. **Database Flag:** `colppy-benjamin/database/migrations/2025_02_13_104650_KAN-11316_record_mixpanel.php`
3. **Mixpanel Config:** `colppy-app/mfe_authentication/src/analytics/mixpanel/mixpanel.tsx`
4. **Event Documentation:** `openai-cookbook/tools/docs/MIXPANEL_LEXICON_CONFIG.md` (lines 382-391)

---

**Last Updated:** 2024-12-24  
**Status:** ✅ Complete - Ready for Review

