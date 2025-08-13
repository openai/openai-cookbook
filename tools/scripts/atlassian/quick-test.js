#!/usr/bin/env node

import axios from 'axios';
import dotenv from 'dotenv';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load environment variables
dotenv.config({ path: join(__dirname, '../../.env') });

async function testConnection() {
  console.log('🔍 Testing Atlassian Connection...\n');
  
  // Check environment variables
  if (!process.env.ATLASSIAN_DOMAIN || !process.env.ATLASSIAN_EMAIL || !process.env.ATLASSIAN_API_TOKEN) {
    console.error('❌ Missing required environment variables!');
    console.log('Please ensure your .env file contains:');
    console.log('  - ATLASSIAN_DOMAIN (e.g., "colppy")');
    console.log('  - ATLASSIAN_EMAIL');
    console.log('  - ATLASSIAN_API_TOKEN');
    return;
  }

  console.log('📋 Configuration:');
  console.log(`  Domain: ${process.env.ATLASSIAN_DOMAIN}.atlassian.net`);
  console.log(`  Email: ${process.env.ATLASSIAN_EMAIL}`);
  console.log(`  Token: ${process.env.ATLASSIAN_API_TOKEN.substring(0, 4)}...`);
  console.log('');

  // Create API client
  const auth = Buffer.from(`${process.env.ATLASSIAN_EMAIL}:${process.env.ATLASSIAN_API_TOKEN}`).toString('base64');
  const api = axios.create({
    baseURL: `https://${process.env.ATLASSIAN_DOMAIN}.atlassian.net`,
    headers: {
      'Authorization': `Basic ${auth}`,
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    timeout: 10000,
  });

  try {
    // Test 1: List projects
    console.log('📂 Testing Jira API - Listing Projects...');
    const projectsResponse = await api.get('/rest/api/3/project');
    console.log(`✅ Found ${projectsResponse.data.length} projects:`);
    projectsResponse.data.slice(0, 5).forEach(project => {
      console.log(`   - ${project.key}: ${project.name}`);
    });
    console.log('');

    // Test 2: Current user
    console.log('👤 Getting current user info...');
    const userResponse = await api.get('/rest/api/3/myself');
    console.log(`✅ Logged in as: ${userResponse.data.displayName} (${userResponse.data.emailAddress})`);
    console.log('');

    // Test 3: Search for recent issues
    console.log('🔍 Searching for recent issues...');
    const searchResponse = await api.get('/rest/api/3/search', {
      params: {
        jql: 'updated >= -7d ORDER BY updated DESC',
        maxResults: 5,
        fields: 'key,summary,status'
      }
    });
    console.log(`✅ Found ${searchResponse.data.total} issues updated in the last 7 days:`);
    searchResponse.data.issues.forEach(issue => {
      console.log(`   - ${issue.key}: ${issue.fields.summary} [${issue.fields.status.name}]`);
    });
    console.log('');

    // Test 4: Confluence spaces (if available)
    console.log('📚 Testing Confluence API - Listing Spaces...');
    try {
      const spacesResponse = await api.get('/wiki/rest/api/space?limit=5');
      console.log(`✅ Found ${spacesResponse.data.size} spaces:`);
      spacesResponse.data.results.forEach(space => {
        console.log(`   - ${space.key}: ${space.name}`);
      });
    } catch (error) {
      if (error.response?.status === 404) {
        console.log('⚠️  Confluence might not be available on this instance');
      } else {
        throw error;
      }
    }

    console.log('\n✅ All tests passed! Your Atlassian MCP server is ready to use.');
    
  } catch (error) {
    console.error('\n❌ Connection test failed!');
    if (error.response) {
      console.error(`Status: ${error.response.status}`);
      console.error(`Message: ${error.response.data?.message || error.response.statusText}`);
      
      if (error.response.status === 401) {
        console.log('\n🔑 Authentication failed. Please check:');
        console.log('  1. Your email address is correct');
        console.log('  2. Your API token is valid');
        console.log('  3. The token was created for the correct account');
      } else if (error.response.status === 404) {
        console.log('\n🌐 Domain not found. Please check:');
        console.log('  1. Your ATLASSIAN_DOMAIN is correct (without .atlassian.net)');
        console.log('  2. Example: use "colppy" not "colppy.com" or "colppy.atlassian.net"');
      }
    } else {
      console.error('Error:', error.message);
    }
  }
}

// Run the test
testConnection();






