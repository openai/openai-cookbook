// Intercom Fast Export Script - Maximized Performance Version
const axios = require('axios');
const fs = require('fs');
const { Command } = require('commander');
const { INTERCOM_ACCESS_TOKEN } = require('./intercom-config');
const path = require('path');
const os = require('os');

// Configurar para máxima concurrencia basada en las CPUs disponibles
const CPU_COUNT = os.cpus().length;
const DEFAULT_CONCURRENCY = Math.max(CPU_COUNT * 2, 16); // Al menos 16 hilos, más en máquinas potentes

// Parse command line arguments
const program = new Command();
program
    .option('--from <date>', 'Start date (YYYY-MM-DD)')
    .option('--to <date>', 'End date (YYYY-MM-DD, defaults to today)', new Date().toISOString().split('T')[0])
    .option('--output <filename>', 'Output filename', 'intercom-conversations-abril.csv')
    .option('--batch-size <number>', 'Batch size for processing conversations', '50')
    .option('--max-concurrent <number>', 'Maximum concurrent requests', DEFAULT_CONCURRENCY.toString())
    .option('--version <version>', 'Intercom API version', '2.13')
    .option('--chunk-size <number>', 'Number of conversations to process before writing to disk', '500')
    .parse(process.argv);

const options = program.opts();
const batchSize = parseInt(options.batchSize, 10);
const maxConcurrent = parseInt(options.maxConcurrent, 10);
const chunkSize = parseInt(options.chunkSize, 10);

console.log(`🚀 Maximum performance mode: Using ${maxConcurrent} concurrent requests with batch size ${batchSize}`);
console.log(`💻 Running on ${CPU_COUNT} CPU cores`);

// Validate required parameters
if (!options.from) {
    console.error('Error: --from date is required');
    process.exit(1);
}

// Validate API token
if (!INTERCOM_ACCESS_TOKEN) {
    console.error('Error: INTERCOM_ACCESS_TOKEN is not set in intercom-config.js');
    process.exit(1);
}

// Create Axios instance with proper authentication and timeout handling
const intercomApi = axios.create({
    baseURL: 'https://api.intercom.io',
    headers: {
        'Authorization': `Bearer ${INTERCOM_ACCESS_TOKEN}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Intercom-Version': options.version
    },
    timeout: 30000, // 30s timeout
    maxContentLength: 50 * 1024 * 1024 // Allow larger responses
});

// Retry mechanism for failed requests
async function retryableRequest(fn, maxRetries = 3, delay = 750) {
    let lastError;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error;

            // Check if we should retry or give up
            if (attempt < maxRetries) {
                if (error.response && error.response.status === 429) {
                    // Rate limited - use exponential backoff
                    const retryAfter = parseInt(error.response.headers['retry-after'] || '5', 10);
                    const waitTime = retryAfter * 1000 || Math.min(delay * Math.pow(2, attempt), 30000);
                    console.log(`Rate limited. Retrying after ${waitTime / 1000}s (attempt ${attempt}/${maxRetries})...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                } else {
                    // Other error, normal backoff
                    const waitTime = delay * Math.pow(1.5, attempt - 1);
                    console.log(`Request failed. Retrying after ${waitTime / 1000}s (attempt ${attempt}/${maxRetries})...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                }
            }
        }
    }

    throw lastError;
}

// Helper function to format date
function formatDate(date) {
    return date.toISOString().split('T')[0];
}

// Setup CSV writer - replacing the library dependency with direct file writing
const csvHeader = [
    { id: 'conversation_id', title: 'Conversation ID' },
    { id: 'created_at', title: 'Created At' },
    { id: 'updated_at', title: 'Updated At' },
    { id: 'message_id', title: 'Message ID' },
    { id: 'message_body', title: 'Message Body' },
    { id: 'part_type', title: 'Part Type' },
    { id: 'author_type', title: 'Author Type' },
    { id: 'author_id', title: 'Author ID' },
    { id: 'author_name', title: 'Author Name' },
    { id: 'owner_name', title: 'Owner Name' },
    { id: 'user_id', title: 'User ID' },
    { id: 'company_id', title: 'Company ID' },
    { id: 'state', title: 'State' },
    { id: 'read', title: 'Read' }
];

// Direct CSV row writing function
function writeCSVRow(row) {
    if (!row) return '';

    // Map through the header IDs to ensure we keep the same column order
    return csvHeader.map(col => {
        const val = row[col.id] || '';
        // Escape quotes and wrap in quotes
        return `"${String(val).replace(/"/g, '""')}"`;
    }).join(',');
}

// Function to write CSV header
function writeCSVHeader() {
    return csvHeader.map(col => `"${col.title}"`).join(',');
}

// Get detailed conversation including all parts
async function getConversationDetails(conversationId) {
    try {
        return await retryableRequest(async () => {
            const response = await intercomApi.get(`/conversations/${conversationId}`);
            return response.data;
        });
    } catch (error) {
        console.error(`Failed to retrieve conversation ${conversationId} after retries: ${error.message}`);
        return null;
    }
}

// Process a conversation to extract all messages
async function processConversation(conversation) {
    if (!conversation) return [];

    const conversationId = conversation.id;
    const createdAt = conversation.created_at ? new Date(conversation.created_at * 1000).toISOString() : '';
    const updatedAt = conversation.updated_at ? new Date(conversation.updated_at * 1000).toISOString() : '';
    const state = conversation.state || '';
    const read = conversation.read !== undefined ? conversation.read.toString() : '';

    // Extract admin assignee (owner) information
    let ownerName = '';
    if (conversation.admin_assignee_id) {
        // Find admin in teammates array
        if (conversation.teammates && conversation.teammates.admins) {
            const admin = conversation.teammates.admins.find(a => a.id === conversation.admin_assignee_id.toString());
            if (admin && admin.name) {
                ownerName = admin.name;
            }
        }
    }

    // Extract user information
    let userId = '';
    let companyId = '';
    if (conversation.contacts && conversation.contacts.contacts && conversation.contacts.contacts.length > 0) {
        const contact = conversation.contacts.contacts[0];
        userId = contact.id || '';
        // Company ID if available
        if (contact.companies && contact.companies.length > 0) {
            companyId = contact.companies[0].id;
        }
    }

    const rows = [];

    // Process the main conversation message
    if (conversation.source) {
        const mainRow = {
            conversation_id: conversationId,
            created_at: createdAt,
            updated_at: updatedAt,
            message_id: conversation.source.id || '',
            message_body: conversation.source.body || '',
            part_type: 'conversation',
            author_type: conversation.source.author ? conversation.source.author.type : '',
            author_id: conversation.source.author ? conversation.source.author.id : '',
            author_name: conversation.source.author ? conversation.source.author.name : '',
            owner_name: ownerName,
            user_id: userId,
            company_id: companyId,
            state: state,
            read: read
        };
        rows.push(mainRow);
    }

    // Process all conversation parts
    if (conversation.conversation_parts && conversation.conversation_parts.conversation_parts) {
        conversation.conversation_parts.conversation_parts.forEach(part => {
            if (part) {
                const partRow = {
                    conversation_id: conversationId,
                    created_at: part.created_at ? new Date(part.created_at * 1000).toISOString() : '',
                    updated_at: updatedAt, // Parts don't have their own updated_at
                    message_id: part.id || '',
                    message_body: part.body || '',
                    part_type: part.part_type || '',
                    author_type: part.author ? part.author.type : '',
                    author_id: part.author ? part.author.id : '',
                    author_name: part.author ? part.author.name : '',
                    owner_name: ownerName, // Same owner for the entire conversation
                    user_id: userId, // Same user for the entire conversation
                    company_id: companyId, // Same company for the entire conversation
                    state: state,
                    read: read
                };
                rows.push(partRow);
            }
        });
    }

    return rows;
}

// Process queue of conversation IDs with concurrency control
async function processWithConcurrency(conversationIds, outputStream) {
    // Validate input
    if (!Array.isArray(conversationIds)) {
        throw new Error(`Expected conversationIds to be an array, got ${typeof conversationIds}`);
    }

    const queue = [...conversationIds];
    const results = [];
    let inProgress = 0;
    let totalProcessed = 0;
    let totalRows = 0;

    // Create temp directory if it doesn't exist
    const tempDir = path.join(process.cwd(), 'temp_files');
    if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir);
    }

    console.log(`⚙️ Processing ${queue.length} conversations with ${maxConcurrent} parallel workers`);
    console.log(`📊 Progress will be shown every ${Math.min(100, Math.ceil(queue.length / 10))} conversations`);

    return new Promise((resolve, reject) => {
        // Write CSV header directly
        outputStream.write(writeCSVHeader() + '\n');

        // Function to process next item in queue
        async function processNext() {
            if (queue.length === 0 && inProgress === 0) {
                // Make sure any remaining results are written
                if (results.length > 0) {
                    try {
                        const csvContent = results.map(row => writeCSVRow(row)).filter(Boolean).join('\n') + '\n';
                        outputStream.write(csvContent);
                        console.log(`Wrote final batch of ${results.length} rows`);
                    } catch (err) {
                        console.error('Error writing final results:', err);
                    }
                }

                console.log(`✅ All ${totalProcessed} conversations processed successfully, generated ${totalRows} rows`);
                outputStream.end();
                return resolve();
            }

            if (queue.length === 0) return;

            const conversationId = queue.shift();
            inProgress++;

            try {
                if (!conversationId) {
                    console.error('Warning: Found undefined conversationId');
                    inProgress--;
                    processNext();
                    return;
                }

                const conversation = await getConversationDetails(conversationId);

                if (!conversation) {
                    console.log(`No data returned for conversation ${conversationId}`);
                    inProgress--;
                    processNext();
                    return;
                }

                console.log(`Processing conversation: ${conversationId}`);

                // Convert conversation to rows manually
                const rows = await processConversation(conversation);

                // Add rows to results
                if (rows.length > 0) {
                    results.push(...rows);
                    totalRows += rows.length;

                    // Write to file and clear results when we've reached a chunk
                    if (results.length >= chunkSize) {
                        try {
                            const csvContent = results.map(row => writeCSVRow(row)).filter(Boolean).join('\n') + '\n';

                            outputStream.write(csvContent);
                            console.log(`Wrote batch of ${results.length} rows to CSV file`);
                            results.length = 0; // Clear the array
                        } catch (err) {
                            console.error('Error writing chunk to CSV:', err);
                        }
                    }
                }

                totalProcessed++;
                if (totalProcessed % Math.min(100, Math.ceil(conversationIds.length / 10)) === 0 || totalProcessed === conversationIds.length) {
                    const percent = Math.round(totalProcessed / conversationIds.length * 100);
                    console.log(`⏱️ Progress: ${totalProcessed}/${conversationIds.length} conversations (${percent}%), ${totalRows} total rows`);
                }
            } catch (error) {
                console.error(`❌ Error processing conversation ${conversationId}: ${error.message}`);
                console.error(error.stack);
            } finally {
                inProgress--;
                processNext();
            }

            // Start new tasks if queue not empty and below concurrency limit
            while (inProgress < maxConcurrent && queue.length > 0) {
                processNext();
            }
        }

        // Initial kickoff - start up to maxConcurrent workers
        const initialBatch = Math.min(maxConcurrent, queue.length);
        for (let i = 0; i < initialBatch; i++) {
            processNext();
        }
    });
}

// Fetch all conversation IDs for the given date range
async function fetchAllConversationIds(fromDate, toDate) {
    const fromTimestamp = Math.floor(new Date(fromDate).getTime() / 1000);
    const toTimestamp = Math.floor(new Date(toDate).getTime() / 1000);

    console.log(`📅 Fetching conversations from ${fromDate} to ${toDate}...`);

    const allIds = [];
    let hasMore = true;
    const maxPerPage = 150; // Maximum allowed per API documentation
    let startingAfter = null;

    const progressInterval = setInterval(() => {
        console.log(`⌛ Still fetching conversations, found ${allIds.length} conversations so far...`);
    }, 5000);

    while (hasMore) {
        try {
            const paginationInfo = startingAfter
                ? `using starting_after=${startingAfter.substring(0, 8)}...`
                : 'first page';
            console.log(`📄 Fetching ${paginationInfo}...`);

            const searchQuery = {
                query: {
                    operator: 'AND',
                    value: [
                        {
                            field: 'created_at',
                            operator: '>=',
                            value: fromTimestamp
                        },
                        {
                            field: 'created_at',
                            operator: '<=',
                            value: toTimestamp
                        }
                    ]
                },
                pagination: {
                    per_page: maxPerPage
                }
            };

            // Add starting_after for pagination if we have it
            if (startingAfter) {
                searchQuery.pagination.starting_after = startingAfter;
            }

            const response = await retryableRequest(async () => {
                const resp = await intercomApi.post('/conversations/search', searchQuery);
                return resp;
            });

            const conversations = response.data.conversations || [];

            if (conversations.length === 0) {
                console.log('No more conversations found.');
                hasMore = false;
                continue;
            }

            // Add conversation IDs to our list
            const ids = conversations.map(c => c.id);
            allIds.push(...ids);

            console.log(`📈 Found ${ids.length} conversations in this batch. Total so far: ${allIds.length}`);

            // Check if we have more pages
            if (!response.data.pages.next || !response.data.pages.next.starting_after) {
                console.log('No more pages.');
                hasMore = false;
            } else {
                startingAfter = response.data.pages.next.starting_after;
                console.log(`Next page will start after: ${startingAfter}`);
            }
        } catch (error) {
            console.error(`❌ Error fetching conversations: ${error.message}`);

            if (error.response && error.response.status === 429) {
                // Rate limited - wait and retry
                const retryAfter = parseInt(error.response.headers['retry-after'] || '60', 10);
                console.log(`⏱️ Rate limited. Waiting ${retryAfter} seconds before retrying...`);
                await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
                // Don't update startingAfter, retry the same request
            } else if (error.response) {
                console.error('Response data:', JSON.stringify(error.response.data, null, 2));
                hasMore = false;
            } else {
                // Network error or timeout - wait and retry
                console.log(`⚠️ Network error. Waiting 5 seconds before retrying...`);
                await new Promise(resolve => setTimeout(resolve, 5000));
                // Don't update startingAfter, retry the same request
            }
        }
    }

    clearInterval(progressInterval);
    return allIds;
}

// Main function to run the export
async function main() {
    console.time('Total execution time');
    const fromDate = new Date(options.from);
    const toDate = new Date(options.to);

    console.log(`🔍 Searching for conversations from ${formatDate(fromDate)} to ${formatDate(toDate)}`);

    // Get conversation IDs from the specified date range
    const conversationIds = await fetchAllConversationIds(fromDate, toDate);
    console.log(`📋 Found ${conversationIds.length} conversations in the date range`);

    if (conversationIds.length === 0) {
        console.log('No conversations found. Exiting.');
        return;
    }

    // Create output file stream
    const outputStream = fs.createWriteStream(options.output);

    try {
        // Process all conversations and generate the CSV file
        await processWithConcurrency(conversationIds, outputStream);
        console.log(`✅ Export completed successfully: ${options.output}`);
    } catch (error) {
        console.error('❌ Error during export:', error);
        process.exit(1);
    } finally {
        console.timeEnd('Total execution time');
    }
}

// Run the main function
main(); 