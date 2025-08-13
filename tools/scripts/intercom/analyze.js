const fs = require('fs');
const path = require('path');
const { Command } = require('commander');

// Parse command line arguments
const program = new Command();
program
  .requiredOption('-f, --file <path>', 'CSV file to analyze')
  .option('-s, --stats', 'Show basic statistics', true)
  .option('-t, --top-users <number>', 'Show top N users by message count', '5')
  .option('-a, --top-admins <number>', 'Show top N admins by message count', '5')
  .parse(process.argv);

const options = program.opts();

// Main function
async function main() {
  try {
    console.log(`Analyzing file: ${options.file}`);
    
    // Check if file exists
    if (!fs.existsSync(options.file)) {
      console.error(`Error: File ${options.file} does not exist`);
      process.exit(1);
    }
    
    // Read and parse CSV file
    const fileContent = fs.readFileSync(options.file, 'utf8');
    const lines = fileContent.split('\n');
    
    // Get headers (first line)
    const headers = lines[0].split(',');
    const headerIndexes = {};
    headers.forEach((header, index) => {
      headerIndexes[header.trim().replace(/"/g, '')] = index;
    });
    
    // Required fields
    const requiredFields = ['Conversation ID', 'Part Type', 'User Name', 'Admin Name', 'Message Body'];
    const missingFields = requiredFields.filter(field => !(field in headerIndexes));
    
    if (missingFields.length > 0) {
      console.error(`Error: CSV file is missing required fields: ${missingFields.join(', ')}`);
      process.exit(1);
    }
    
    // Parse data rows
    const data = [];
    for (let i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue;
      
      const row = parseCSVLine(lines[i]);
      data.push({
        conversationId: row[headerIndexes['Conversation ID']],
        partType: row[headerIndexes['Part Type']],
        userName: row[headerIndexes['User Name']],
        adminName: row[headerIndexes['Admin Name']],
        body: row[headerIndexes['Message Body']]
      });
    }
    
    // Analyze data
    if (options.stats) {
      showBasicStats(data);
    }
    
    if (options.topUsers) {
      showTopUsers(data, parseInt(options.topUsers));
    }
    
    if (options.topAdmins) {
      showTopAdmins(data, parseInt(options.topAdmins));
    }
    
  } catch (error) {
    console.error('Error occurred:', error.message);
    process.exit(1);
  }
}

// Parse a CSV line with proper handling of quoted fields
function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      // Toggle quote mode
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      // End of field
      result.push(current.replace(/"/g, ''));
      current = '';
    } else {
      // Normal character
      current += char;
    }
  }
  
  // Add last field
  result.push(current.replace(/"/g, ''));
  
  return result;
}

// Show basic statistics
function showBasicStats(data) {
  console.log('\n--- Basic Statistics ---');
  
  // Count unique conversations
  const uniqueConversations = new Set(data.map(row => row.conversationId)).size;
  console.log(`Total unique conversations: ${uniqueConversations}`);
  
  // Count message parts by type
  const partTypes = {};
  data.forEach(row => {
    partTypes[row.partType] = (partTypes[row.partType] || 0) + 1;
  });
  
  console.log('Message parts by type:');
  Object.entries(partTypes)
    .sort((a, b) => b[1] - a[1])
    .forEach(([type, count]) => {
      console.log(`  - ${type}: ${count}`);
    });
  
  // Average parts per conversation
  const avgPartsPerConversation = data.length / uniqueConversations;
  console.log(`Average message parts per conversation: ${avgPartsPerConversation.toFixed(2)}`);
}

// Show top users by message count
function showTopUsers(data, limit) {
  console.log('\n--- Top Users by Message Count ---');
  
  const userCounts = {};
  data.forEach(row => {
    if (row.userName && row.partType !== 'conversation' && !row.adminName) {
      userCounts[row.userName] = (userCounts[row.userName] || 0) + 1;
    }
  });
  
  Object.entries(userCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .forEach(([name, count], index) => {
      console.log(`${index + 1}. ${name}: ${count} messages`);
    });
}

// Show top admins by message count
function showTopAdmins(data, limit) {
  console.log('\n--- Top Admins by Message Count ---');
  
  const adminCounts = {};
  data.forEach(row => {
    if (row.adminName && row.partType !== 'conversation') {
      adminCounts[row.adminName] = (adminCounts[row.adminName] || 0) + 1;
    }
  });
  
  Object.entries(adminCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .forEach(([name, count], index) => {
      console.log(`${index + 1}. ${name}: ${count} messages`);
    });
}

// Run the main function
main(); 