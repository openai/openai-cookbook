#!/usr/bin/env node

/**
 * Fellow API Debug Tool
 * Tests various API patterns to help diagnose connection issues
 */

import axios from 'axios';
import dotenv from 'dotenv';

dotenv.config();

const API_KEY = "81e47357e233b204d91fa67302fa94ab2d74007724ec34f661a5513dfce5bf64";
const WORKSPACE = "colppy";

async function testAPIPatterns() {
  console.log("🔍 Fellow API Debug Tool");
  console.log("========================");
  console.log(`API Key: ${API_KEY.substring(0, 8)}...${API_KEY.substring(-8)}`);
  console.log(`Workspace: ${WORKSPACE}`);
  console.log("");

  const testPatterns = [
    // Different base URLs
    { url: `https://${WORKSPACE}.fellow.app/api/users/me`, method: 'GET', desc: 'Workspace API v1' },
    { url: `https://${WORKSPACE}.fellow.app/api/v1/users/me`, method: 'GET', desc: 'Workspace API v2' },
    { url: `https://api.${WORKSPACE}.fellow.app/v1/users/me`, method: 'GET', desc: 'Subdomain API' },
    { url: `https://${WORKSPACE}.fellow.app/developers/api/users/me`, method: 'GET', desc: 'Developer API path' },
    { url: `https://${WORKSPACE}.fellow.app/api/auth/me`, method: 'GET', desc: 'Auth endpoint' },
    
    // Test root endpoints  
    { url: `https://${WORKSPACE}.fellow.app/api`, method: 'GET', desc: 'API Root' },
    { url: `https://${WORKSPACE}.fellow.app/api/v1`, method: 'GET', desc: 'API V1 Root' },
    
    // Test different auth headers
    { url: `https://${WORKSPACE}.fellow.app/api/users/me`, method: 'GET', desc: 'Bearer token', headers: { 'Authorization': `Bearer ${API_KEY}` } },
    { url: `https://${WORKSPACE}.fellow.app/api/users/me`, method: 'GET', desc: 'API Key header', headers: { 'X-API-Key': API_KEY } },
    { url: `https://${WORKSPACE}.fellow.app/api/users/me`, method: 'GET', desc: 'Token header', headers: { 'X-Auth-Token': API_KEY } },
  ];

  for (const test of testPatterns) {
    try {
      console.log(`Testing: ${test.desc}`);
      console.log(`  URL: ${test.url}`);
      
      const config = {
        method: test.method,
        url: test.url,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'User-Agent': 'Fellow-Debug-Tool/1.0',
          ...(test.headers || { 'Authorization': `Bearer ${API_KEY}` })
        },
        timeout: 10000,
        validateStatus: () => true // Don't throw on any status code
      };

      const response = await axios(config);
      
      console.log(`  Status: ${response.status} ${response.statusText}`);
      console.log(`  Headers: ${JSON.stringify({
        'x-user-id': response.headers['x-user-id'],
        'x-request-id': response.headers['x-request-id'],
        'content-type': response.headers['content-type']
      })}`);
      
      if (response.status === 200) {
        console.log(`  ✅ SUCCESS! Data: ${JSON.stringify(response.data, null, 2)}`);
        break; // Stop on first success
      } else if (response.status === 401) {
        console.log(`  🔐 Auth issue: ${response.data?.message || 'Invalid credentials'}`);
      } else if (response.status === 403) {
        console.log(`  🚫 Forbidden: ${response.data?.message || 'Access denied'}`);
      } else if (response.status === 404) {
        console.log(`  ❌ Not found: ${response.data?.message || 'Endpoint not found'}`);
      } else {
        console.log(`  ⚠️  Other: ${response.data?.message || 'Unknown error'}`);
      }
      
    } catch (error) {
      console.log(`  💥 Error: ${error.message}`);
    }
    
    console.log("");
  }
}

console.log("Starting Fellow API debug tests...\n");
testAPIPatterns().catch(console.error);
