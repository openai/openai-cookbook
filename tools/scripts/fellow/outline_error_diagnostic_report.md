# MCP Outline Authentication Error - Detailed Diagnostic Report

**Generated:** August 30, 2025  
**Workspace:** colppy.fellow.app  
**Issue:** Authentication failures with Outline Wiki API  
**Contact:** jonetto@colppy.com  

---

## 🚨 **Problem Summary**

All API calls to Fellow's Outline wiki system (`dev.fellow.wiki`) return **401 "Unable to decode token"** errors, despite:
- ✅ API key appearing **Active** in Cursor configuration
- ✅ Proper authentication headers tested
- ✅ Correct API endpoint structure  
- ✅ Valid SSL/TLS connection to server

---

## 🔧 **Current Configuration**

### **MCP Configuration (mcp.json):**
```json
"mcp-outline": {
  "command": "node",
  "args": [
    "/Users/virulana/openai-cookbook/mcp-outline/src/index.js"
  ],
  "env": {
    "API_URL": "https://dev.fellow.wiki/api",
    "API_KEY": "faf85794d4ee619f0a9ddc347a20bf85c15b9530ef14c6541a6ed55729ea93f3"
  }
}
```

### **Tested API Key:**
- **Token:** `faf85794d4ee619f0a9ddc347a20bf85c15b9530ef14c6541a6ed55729ea93f3`
- **Source:** From Cursor configuration (current in mcp.json)

---

## 📋 **Error Details**

### **Error 1: Bearer Token Authentication**
```bash
curl -H "Authorization: Bearer faf85794d4ee619f0a9ddc347a20bf85c15b9530ef14c6541a6ed55729ea93f3" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json" \
     "https://dev.fellow.wiki/api/collections.list" \
     -d '{"query": "*", "limit": 5}' -v
```

**Response:**
```
< HTTP/2 401 
< content-type: application/json; charset=utf-8
< content-length: 94
< date: Sat, 30 Aug 2025 01:01:14 GMT
< server: Fly/d0f8dfc46 (2025-08-26)
< fly-request-id: 01K3W7W9MFZ64Z9H1W1NN9YJQP-eze

{"ok":false,"error":"authentication_required","status":401,"message":"Unable to decode token"}
```

### **Error 2: X-API-KEY Header Authentication**  
```bash
curl -H "X-API-KEY: faf85794d4ee619f0a9ddc347a20bf85c15b9530ef14c6541a6ed55729ea93f3" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json" \
     "https://dev.fellow.wiki/api/collections.list" \
     -d '{"query": "*", "limit": 5}' -v
```

**Response:**
```
< HTTP/2 401 
< content-type: application/json; charset=utf-8
< content-length: 95
< date: Sat, 30 Aug 2025 01:01:28 GMT
< server: Fly/d0f8dfc46 (2025-08-26)
< fly-request-id: 01K3W7WNHC28VP2P3RXRVKSQD0-eze

{"ok":false,"error":"authentication_required","status":401,"message":"Authentication required"}
```

### **Error 3: Testing Different API Key**
When testing with the Fellow Meeting API key (`81e47357e233b204d91fa67302fa94ab2d74007724ec34f661a5513dfce5bf64`):

```
< HTTP/2 401 
{"ok":false,"error":"authentication_required","status":401,"message":"Unable to decode token"}
```

---

## 🔍 **Detailed Technical Information**

### **Server Details:**
- **Host:** dev.fellow.wiki (IP: 66.241.125.38)
- **SSL Certificate:** Valid (CN=dev.fellow.wiki)
- **Server:** Fly/d0f8dfc46 (2025-08-26)
- **Connection:** TLS 1.3 successful

### **Request Headers Tested:**
1. ✅ `Authorization: Bearer <token>`
2. ✅ `X-API-KEY: <token>`
3. ✅ `Content-Type: application/json`
4. ✅ `Accept: application/json`

### **Endpoints Tested:**
1. ❌ `POST /api/collections.list` → 401 "Unable to decode token"
2. ❌ `GET /api` → 404 "Resource not found"

### **API Response Pattern:**
Both authentication headers return identical error structures:
```json
{
  "ok": false,
  "error": "authentication_required",
  "status": 401,
  "message": "Unable to decode token" // or "Authentication required"
}
```

---

## 🤔 **Key Questions for Fellow Support**

### **1. API Key Validity:**
- Is the token `faf85794d4ee619f0a9ddc347a20bf85c15b9530ef14c6541a6ed55729ea93f3` valid for `dev.fellow.wiki`?
- Are Meeting API keys (`colppy.fellow.app`) different from Wiki API keys (`dev.fellow.wiki`)?

### **2. Authentication Method:**
- Should we use `Authorization: Bearer <token>` or `X-API-KEY: <token>`?
- Are there additional headers required for Outline API?

### **3. Workspace Configuration:**
- Do we need a separate API key specifically for the `dev.fellow.wiki` Outline system?
- Is the Outline API enabled separately from the Meeting API?

### **4. API Access:**
- Should the user generate an Outline-specific API key from `https://dev.fellow.wiki/settings/tokens`?
- Are there workspace-specific requirements for Outline API access?

---

## 📊 **Working Fellow Meeting API (for comparison)**

### **Working Example:**
```bash
curl -H "X-API-KEY: 81e47357e233b204d91fa67302fa94ab2d74007724ec34f661a5513dfce5bf64" \
     "https://colppy.fellow.app/api/v1/me"
```

**Success Response:**
```json
{
  "user": {
    "id": "GU5SXZe4t2",
    "email": "jonetto@colppy.com",
    "full_name": "Juan Ignacio Onetto"
  },
  "workspace": {
    "id": "0LL2RUpxhv",
    "name": "colppy.com",
    "subdomain": "colppy"
  }
}
```

---

## 🎯 **Status Summary**

| **System** | **Status** | **API Key** | **URL** |
|-----------|------------|-------------|---------|
| **Fellow Meeting** | ✅ **Working** | `81e47357...` | `colppy.fellow.app/api/v1` |
| **Fellow Outline** | ❌ **401 Error** | `faf85794...` | `dev.fellow.wiki/api` |

---

## 📞 **Support Request**

**Email:** help@fellow.co  
**Subject:** "Outline Wiki API - Authentication Error 401 'Unable to decode token'"

Please help us resolve the authentication issue with the Outline Wiki API. The Meeting API works perfectly, but the Outline API consistently returns 401 errors despite testing multiple authentication methods.

**Request ID Examples:**
- `01K3W7W9MFZ64Z9H1W1NN9YJQP-eze` (Bearer token test)
- `01K3W7WNHC28VP2P3RXRVKSQD0-eze` (X-API-KEY test)

Thank you for your assistance!
