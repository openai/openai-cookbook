/**
 * Test Script to Compare Current vs Improved Code
 */

// Sample data matching your webhook format
const sampleInputData = {
    raw: JSON.stringify({
        "action": "members",
        "parameters": {
            "mixpanel_project_id": "2201475",
            "mixpanel_cohort_name": "Registros Ultimas 24 horas",
            "members": [
                {
                    "$distinct_id": "yolandacabral81@gmail.com.ar",
                    "$email": "yolandacabral81@gmail.com.ar",
                    "$name": "Mirna",
                    "$os": "Android",
                    "$phone": "+543704546789",
                    "Fecha de registro": "2025-01-31T08:57:52",
                    "Fecha del primer login": "2025-01-31T08:57:52",
                    "mixpanel_distinct_id": "yolandacabral81@gmail.com.ar",
                    "utm_campaign": "Sales-Performance Max-V2",
                    "utm_content": "",
                    "utm_medium": "ppc",
                    "utm_source": "google",
                    "utm_term": ""
                },
                {
                    "$distinct_id": "p_armanasco@hotmail.com",
                    "$email": "p_armanasco@hotmail.com",
                    "$name": "Paula Armanasco",
                    "$os": "Windows",
                    "$phone": "+102964510707",
                    "Fecha de registro": "2025-01-31T11:27:06",
                    "Fecha del primer login": "2025-01-31T11:27:06",
                    "mixpanel_distinct_id": "p_armanasco@hotmail.com",
                    "utm_campaign": "Search_Branding_Leads_ARG",
                    "utm_content": "",
                    "utm_medium": "ppc",
                    "utm_source": "google",
                    "utm_term": "colppy",
                    "¿Cuál es tu rol? wizard": "Soy contador/ administrativo de un estudio contable"
                }
            ]
        }
    })
};

console.log('=== TESTING CURRENT CODE (ONLY EMAIL) ===');
const rawData = sampleInputData.raw || '{}';
const parsedData = JSON.parse(rawData);
const members = parsedData.parameters?.members || [];

// ❌ Your current code - only extracts email
const currentOutput = members.map(member => ({ email: member.$email }));
console.log('Current output (only email):', JSON.stringify(currentOutput, null, 2));

console.log('\n=== TESTING IMPROVED CODE (ALL FIELDS) ===');
// ✅ Improved code - extracts all fields
const improvedOutput = members.map(member => ({
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
    row_number: members.indexOf(member) + 1
}));

console.log('Improved output (all fields):', JSON.stringify(improvedOutput, null, 2));

console.log('\n=== COMPARISON SUMMARY ===');
console.log(`Current code extracts: ${Object.keys(currentOutput[0]).length} field(s)`);
console.log(`Improved code extracts: ${Object.keys(improvedOutput[0]).length} field(s)`);
console.log('Fields in current code:', Object.keys(currentOutput[0]));
console.log('Fields in improved code:', Object.keys(improvedOutput[0]));



