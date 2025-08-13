require('dotenv').config();
const axios = require('axios');
const { createObjectCsvWriter } = require('csv-writer');
const { Command } = require('commander');
const fs = require('fs');
const path = require('path');
// const { INTERCOM_ACCESS_TOKEN } = require('../intercom-config');

// Helper function to format date to YYYY-MM-DD
function formatDate(date) {
  return date.toISOString().split('T')[0];
}

// Parse command line arguments
const program = new Command();
program
  .option('--from <date>', 'Start date (YYYY-MM-DD)')
  .option('--to <date>', 'End date (YYYY-MM-DD, defaults to today)', formatDate(new Date()))
  .option('--output <filename>', 'Output filename', 'intercom-conversations.csv')
  .option('--limit <number>', 'Max conversations to retrieve', Infinity)
  .parse(process.argv);

const options = program.opts();

// Validate required parameters
if (!options.from) {
  console.error('Error: --from date is required');
  process.exit(1);
}

// Validate API token
if (!process.env.INTERCOM_ACCESS_TOKEN) {
  console.error('Error: INTERCOM_ACCESS_TOKEN is not set in the .env file');
  process.exit(1);
}

// Use token from config file if environment variable is not set
const accessToken = process.env.INTERCOM_ACCESS_TOKEN;

// Intercom API client
const intercomClient = axios.create({
  baseURL: 'https://api.intercom.io',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Accept': 'application/json',
    'Intercom-Version': '2.8'
  }
});

// Main function
async function main() {
  try {
    console.log(`Starting Intercom conversation export from ${options.from} to ${options.to}`);
    console.log('Calculating total conversations to process...');

    // Get count of conversations in the date range to provide progress reporting
    const totalConversations = await getConversationCount(options.from, options.to);
    console.log(`Found ${totalConversations} conversations in the specified date range`);

    if (totalConversations === 0) {
      console.log('No conversations found in the specified date range');
      return;
    }

    // Calculate potential row count (rough estimate: 1 conversation + avg 5 conversation parts per convo)
    const estimatedRows = totalConversations * 6;
    console.log(`Estimated rows in CSV output: ~${estimatedRows}`);

    // Determine if we should proceed based on the limit
    const limit = Math.min(totalConversations, options.limit === 'Infinity' ? Infinity : parseInt(options.limit));
    if (limit < totalConversations) {
      console.log(`Limiting export to ${limit} conversations due to --limit option`);
    }

    // Initialize CSV writer
    const csvWriter = createObjectCsvWriter({
      path: options.output,
      header: [
        { id: 'conversation_id', title: 'Conversation ID' },
        { id: 'created_at', title: 'Created At' },
        { id: 'updated_at', title: 'Updated At' },
        { id: 'user_id', title: 'User ID' },
        { id: 'user_email', title: 'User Email' },
        { id: 'user_name', title: 'User Name' },
        { id: 'admin_id', title: 'Admin ID' },
        { id: 'admin_name', title: 'Admin Name' },
        { id: 'part_type', title: 'Part Type' },
        { id: 'part_created_at', title: 'Part Created At' },
        { id: 'body', title: 'Message Body' },
        { id: 'url', title: 'URL' }
      ]
    });

    // Fetch and process conversations
    await processAllConversations(csvWriter, options.from, options.to, limit);

    console.log(`\nExport completed. Results saved to: ${options.output}`);
  } catch (error) {
    console.error('Error occurred:', error.message);
    if (error.response) {
      console.error('API Error:', error.response.data);
    }
    process.exit(1);
  }
}

// Get total count of conversations in date range
async function getConversationCount(fromDate, toDate) {
  const fromTimestamp = new Date(fromDate).getTime() / 1000;
  const toTimestamp = new Date(toDate).getTime() / 1000;

  const params = {
    query: {
      field: 'created_at',
      operator: 'between',
      value: [fromTimestamp, toTimestamp]
    }
  };

  console.log('Using token:', accessToken);
  console.log('Token length:', accessToken.length);

  try {
    const response = await intercomClient.post('/conversations/search', params);
    return response.data.total_count;
  } catch (error) {
    console.error('Full error details:', error);
    throw new Error(`Failed to retrieve conversation count: ${error.message}`);
  }
}

// Process all conversations with pagination
async function processAllConversations(csvWriter, fromDate, toDate, limit) {
  let page = 1;
  let totalProcessed = 0;
  let hasMore = true;
  const csvData = [];

  const fromTimestamp = new Date(fromDate).getTime() / 1000;
  const toTimestamp = new Date(toDate).getTime() / 1000;

  const params = {
    query: {
      field: 'created_at',
      operator: 'between',
      value: [fromTimestamp, toTimestamp]
    },
    sort: {
      field: 'created_at',
      order: 'ascending'
    },
    pagination: {
      per_page: 50
    }
  };

  console.log('Starting to fetch conversations...');

  while (hasMore && totalProcessed < limit) {
    params.pagination.page = page;

    try {
      console.log(`Fetching page ${page}...`);
      const response = await intercomClient.post('/conversations/search', params);
      const conversations = response.data.conversations;

      if (conversations.length === 0) {
        hasMore = false;
        continue;
      }

      // Process each conversation
      for (const conversation of conversations) {
        if (totalProcessed >= limit) break;

        // Fetch full conversation details to get conversation_parts
        const fullConversation = await getConversationDetails(conversation.id);
        const rows = convertConversationToRows(fullConversation);
        csvData.push(...rows);

        totalProcessed++;
        process.stdout.write(`\rProcessed ${totalProcessed}/${Math.min(limit, response.data.total_count)} conversations`);
      }

      // Check if we have more pages
      if (!response.data.pages.next || totalProcessed >= limit) {
        hasMore = false;
      } else {
        page++;
      }
    } catch (error) {
      throw new Error(`Failed to process conversations on page ${page}: ${error.message}`);
    }
  }

  // Write all data to CSV
  console.log('\nWriting data to CSV file...');
  await csvWriter.writeRecords(csvData);
}

// Get detailed conversation including all parts
async function getConversationDetails(conversationId) {
  try {
    const response = await intercomClient.get(`/conversations/${conversationId}`);
    return response.data;
  } catch (error) {
    throw new Error(`Failed to retrieve conversation details: ${error.message}`);
  }
}

// Convert conversation to CSV rows
function convertConversationToRows(conversation) {
  const rows = [];

  // Get basic user info
  let userName = '';
  let userEmail = '';
  let userId = '';

  if (conversation.customers && conversation.customers.contacts) {
    const user = conversation.customers.contacts[0];
    if (user) {
      userName = user.name || '';
      userEmail = user.email || '';
      userId = user.id || '';
    }
  }

  // Get assignee info
  let adminId = '';
  let adminName = '';

  if (conversation.assignee && conversation.assignee.id) {
    adminId = conversation.assignee.id;
    adminName = conversation.assignee.name || '';
  }

  // Add conversation info as the first row
  const mainRow = {
    conversation_id: conversation.id,
    created_at: formatDate(new Date(conversation.created_at * 1000)),
    updated_at: formatDate(new Date(conversation.updated_at * 1000)),
    user_id: userId,
    user_email: userEmail,
    user_name: userName,
    admin_id: adminId,
    admin_name: adminName,
    part_type: 'conversation',
    part_created_at: formatDate(new Date(conversation.created_at * 1000)),
    body: conversation.source?.body || '',
    url: `https://app.intercom.com/a/apps/${conversation.app_id}/conversations/${conversation.id}`
  };

  rows.push(mainRow);

  // Add each conversation part as a row
  if (conversation.conversation_parts && conversation.conversation_parts.conversation_parts) {
    for (const part of conversation.conversation_parts.conversation_parts) {
      // Skip system messages if needed
      // if (part.part_type === 'system') continue;

      const partRow = {
        conversation_id: conversation.id,
        created_at: formatDate(new Date(conversation.created_at * 1000)),
        updated_at: formatDate(new Date(conversation.updated_at * 1000)),
        user_id: part.author.id,
        user_email: '', // Not available in conversation parts
        user_name: part.author.name || '',
        admin_id: part.author.type === 'admin' ? part.author.id : '',
        admin_name: part.author.type === 'admin' ? part.author.name : '',
        part_type: part.part_type,
        part_created_at: formatDate(new Date(part.created_at * 1000)),
        body: part.body,
        url: `https://app.intercom.com/a/apps/${conversation.app_id}/conversations/${conversation.id}`
      };

      rows.push(partRow);
    }
  }

  return rows;
}

// Run the main function
main(); 