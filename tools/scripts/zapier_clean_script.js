// Clean JavaScript script for Zapier - No duplicate variable declarations
// This script processes webhook data and extracts all member fields

// Get the raw data from the previous step
const rawData = inputData.raw || '{}';

// Parse the JSON string to a JavaScript object
const parsedData = JSON.parse(rawData);

// Extract the members array from the parsed data
const members = parsedData.parameters?.members || [];

// Create the output array with all fields for each member
const processedMembers = members.map((member, index) => ({
    // Core user identification
    distinct_id: member.$distinct_id || '',
    email: member.$email || '',
    name: member.$name || '',
    
    // Device and contact info
    os: member.$os || '',
    phone: member.$phone || '',
    
    // Registration dates
    registration_date: member['Fecha de registro'] || '',
    first_login_date: member['Fecha del primer login'] || '',
    
    // UTM parameters for marketing attribution
    utm_source: member.utm_source || '',
    utm_campaign: member.utm_campaign || '',
    utm_term: member.utm_term || '',
    utm_medium: member.utm_medium || '',
    utm_content: member.utm_content || '',
    
    // Additional Mixpanel data
    mixpanel_distinct_id: member.mixpanel_distinct_id || '',
    
    // Wizard responses (if available)
    role: member['¿Cuál es tu rol? wizard'] || '',
    implementation_timeline: member['¿Cuándo querés implementar Colppy? wizard'] || '',
    
    // Row number for tracking
    row_number: index + 1
}));

// Set the output variable (this is what Zapier expects)
output = processedMembers;



