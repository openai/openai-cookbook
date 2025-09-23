/**
 * Improved Webhook Data Processor - Extracts ALL Fields
 * This version extracts all available fields from each member
 */

// Your current problematic code:
const rawData = inputData.raw || '{}';
const parsedData = JSON.parse(rawData);
const members = parsedData.parameters?.members || [];

// ❌ PROBLEM: Only extracting email
// output = members.map(member => ({ email: member.$email }));

// ✅ SOLUTION: Extract ALL fields
output = members.map(member => ({
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
    
    // Optional: Add row number for tracking
    row_number: members.indexOf(member) + 1
}));

// Alternative: If you want to be more dynamic and extract ALL available fields
// This version will automatically include any field that exists in the member object
function extractAllFields(members) {
    return members.map(member => {
        const extractedMember = {};
        
        // Extract all properties from the member object
        for (const [key, value] of Object.entries(member)) {
            // Clean up the field names (remove $ prefix for cleaner output)
            const cleanKey = key.startsWith('$') ? key.substring(1) : key;
            extractedMember[cleanKey] = value || '';
        }
        
        return extractedMember;
    });
}

// Usage of the dynamic version:
// output = extractAllFields(members);

// Debug version - to see what fields are available
function debugMemberFields(members) {
    if (members.length > 0) {
        console.log('Available fields in first member:', Object.keys(members[0]));
        console.log('Sample member data:', members[0]);
    }
    return members.map(member => ({
        // Include all the fields you want
        distinct_id: member.$distinct_id || '',
        email: member.$email || '',
        name: member.$name || '',
        os: member.$os || '',
        phone: member.$phone || '',
        registration_date: member['Fecha de registro'] || '',
        first_login_date: member['Fecha del primer login'] || '',
        utm_source: member.utm_source || '',
        utm_campaign: member.utm_campaign || '',
        utm_term: member.utm_term || '',
        utm_medium: member.utm_medium || '',
        utm_content: member.utm_content || '',
        mixpanel_distinct_id: member.mixpanel_distinct_id || '',
        role: member['¿Cuál es tu rol? wizard'] || '',
        implementation_timeline: member['¿Cuándo querés implementar Colppy? wizard'] || ''
    }));
}

// Uncomment to debug what fields are available:
// debugMemberFields(members);



