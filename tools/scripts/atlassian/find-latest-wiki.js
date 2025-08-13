#!/usr/bin/env node

import axios from 'axios';
import dotenv from 'dotenv';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load environment variables
dotenv.config({ path: join(__dirname, '../../.env') });

async function findLatestWikiDocuments() {
  console.log('🔍 Searching for Latest Confluence Documents...\n');
  
  // Check environment variables
  if (!process.env.ATLASSIAN_DOMAIN || !process.env.ATLASSIAN_EMAIL || !process.env.ATLASSIAN_API_TOKEN) {
    console.error('❌ Missing required environment variables!');
    console.log('Please ensure your .env file contains:');
    console.log('  - ATLASSIAN_DOMAIN');
    console.log('  - ATLASSIAN_EMAIL');
    console.log('  - ATLASSIAN_API_TOKEN');
    return;
  }

  // Create API client
  const auth = Buffer.from(`${process.env.ATLASSIAN_EMAIL}:${process.env.ATLASSIAN_API_TOKEN}`).toString('base64');
  
  // Handle domain with or without .atlassian.net
  const domain = process.env.ATLASSIAN_DOMAIN.replace('.atlassian.net', '');
  const baseURL = `https://${domain}.atlassian.net`;
  
  console.log(`Connecting to: ${baseURL}\n`);
  
  const api = axios.create({
    baseURL: baseURL,
    headers: {
      'Authorization': `Basic ${auth}`,
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    timeout: 10000,
  });

  try {
    // Search for recently modified pages
    console.log('📚 Finding recently modified Confluence pages...\n');
    
    // CQL query for pages modified in the last 30 days, ordered by modification date
    const cql = 'type=page and lastmodified > now("-30d") order by lastmodified desc';
    
    const response = await api.get('/wiki/rest/api/content/search', {
      params: {
        cql: cql,
        limit: 10,
        expand: 'space,version,history.lastUpdated'
      }
    });

    if (response.data.results && response.data.results.length > 0) {
      console.log(`✅ Found ${response.data.size} recently modified pages\n`);
      console.log('📄 Latest Documents:\n');
      
      response.data.results.forEach((page, index) => {
        const modifiedDate = new Date(page.history?.lastUpdated?.when || page.version?.when);
        const author = page.history?.lastUpdated?.by?.displayName || page.version?.by?.displayName || 'Unknown';
        const space = page.space?.name || 'Unknown Space';
        
        console.log(`${index + 1}. ${page.title}`);
        console.log(`   Space: ${space}`);
        console.log(`   Last Modified: ${modifiedDate.toLocaleString()}`);
        console.log(`   Modified By: ${author}`);
        console.log(`   URL: https://${domain}.atlassian.net/wiki${page._links.webui}`);
        console.log('');
      });

      // Get the very latest document details
      const latestPage = response.data.results[0];
      console.log('📝 Most Recent Document Details:');
      console.log('================================');
      console.log(`Title: ${latestPage.title}`);
      console.log(`ID: ${latestPage.id}`);
      console.log(`Type: ${latestPage.type}`);
      console.log(`Status: ${latestPage.status}`);
      
      // Get more details about the latest page
      const pageDetails = await api.get(`/wiki/rest/api/content/${latestPage.id}`, {
        params: {
          expand: 'body.view,version,space'
        }
      });
      
      if (pageDetails.data.body?.view?.value) {
        console.log('\n📄 Content Preview (first 500 characters):');
        console.log('-'.repeat(50));
        const textContent = pageDetails.data.body.view.value
          .replace(/<[^>]*>/g, '') // Remove HTML tags
          .replace(/\s+/g, ' ') // Normalize whitespace
          .trim()
          .substring(0, 500);
        console.log(textContent + '...\n');
      }
      
    } else {
      console.log('❌ No Confluence pages found');
      console.log('\nPossible reasons:');
      console.log('  1. No pages have been modified recently');
      console.log('  2. You don\'t have access to any Confluence spaces');
      console.log('  3. Confluence might not be enabled for your Atlassian instance');
    }

    // Also search for blog posts
    console.log('\n📝 Checking for recent blog posts...\n');
    const blogCql = 'type=blogpost and lastmodified > now("-30d") order by lastmodified desc';
    
    const blogResponse = await api.get('/wiki/rest/api/content/search', {
      params: {
        cql: blogCql,
        limit: 5
      }
    });

    if (blogResponse.data.results && blogResponse.data.results.length > 0) {
      console.log(`Found ${blogResponse.data.size} recent blog posts:`);
      blogResponse.data.results.forEach((post, index) => {
        const modifiedDate = new Date(post.history?.lastUpdated?.when || post.version?.when);
        console.log(`${index + 1}. ${post.title} (${modifiedDate.toLocaleDateString()})`);
      });
    }
    
  } catch (error) {
    console.error('\n❌ Failed to search Confluence!');
    if (error.response) {
      console.error(`Status: ${error.response.status}`);
      console.error(`Message: ${error.response.data?.message || error.response.statusText}`);
      
      if (error.response.status === 404) {
        console.log('\n⚠️  Confluence might not be available on your Atlassian instance');
        console.log('  Or you might not have access to any Confluence spaces');
      } else if (error.response.status === 401) {
        console.log('\n🔑 Authentication failed. Please check your credentials');
      }
    } else {
      console.error('Error:', error.message);
    }
  }
}

// Run the search
console.log('🚀 Atlassian Confluence Document Search\n');
findLatestWikiDocuments();
