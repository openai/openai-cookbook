/**
 * Webhook Data Processor for Zapier Integration
 * Processes Mixpanel webhook data and formats it for Google Sheets via Zapier
 * 
 * Input: Raw webhook body from Mixpanel
 * Output: Array of formatted objects ready for Zapier line-item processing
 */

function processWebhookData(rawBody) {
    try {
        // Parse the raw JSON body
        const webhookData = JSON.parse(rawBody);
        
        // Extract the members array
        const members = webhookData.parameters.members;
        
        if (!members || !Array.isArray(members)) {
            throw new Error('No members array found in webhook data');
        }
        
        // Process each member into a formatted object
        const processedMembers = members.map((member, index) => {
            return {
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
                
                // Metadata
                row_number: index + 1,
                processed_at: new Date().toISOString()
            };
        });
        
        return {
            success: true,
            total_members: processedMembers.length,
            cohort_name: webhookData.parameters.mixpanel_cohort_name || '',
            cohort_id: webhookData.parameters.mixpanel_cohort_id || '',
            processed_at: new Date().toISOString(),
            members: processedMembers
        };
        
    } catch (error) {
        return {
            success: false,
            error: error.message,
            processed_at: new Date().toISOString()
        };
    }
}

/**
 * Alternative function that returns only the members array for direct Zapier integration
 * This is useful when you want to use Zapier's Line Itemizer utility
 */
function extractMembersForZapier(rawBody) {
    try {
        const webhookData = JSON.parse(rawBody);
        const members = webhookData.parameters.members;
        
        if (!members || !Array.isArray(members)) {
            throw new Error('No members array found in webhook data');
        }
        
        // Return simplified format for Zapier Line Itemizer
        return members.map(member => ({
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
            role: member['¿Cuál es tu rol? wizard'] || '',
            implementation_timeline: member['¿Cuándo querés implementar Colppy? wizard'] || ''
        }));
        
    } catch (error) {
        console.error('Error processing webhook data:', error);
        return [];
    }
}

/**
 * Test function with sample data
 */
function testProcessor() {
    const sampleWebhookData = `{
        "action": "members",
        "parameters": {
            "mixpanel_project_id": "2201475",
            "mixpanel_integration_id": "0",
            "mixpanel_cohort_name": "Registros Ultimas 24 horas",
            "mixpanel_cohort_id": "5167408",
            "mixpanel_session_id": "9b5bbfa4-1b9a-41fe-bf60-cd31274ef05d",
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
    }`;
    
    console.log('Testing webhook processor...');
    
    // Test full processing
    const result = processWebhookData(sampleWebhookData);
    console.log('Full processing result:', JSON.stringify(result, null, 2));
    
    // Test Zapier extraction
    const zapierData = extractMembersForZapier(sampleWebhookData);
    console.log('Zapier extraction result:', JSON.stringify(zapierData, null, 2));
    
    return { result, zapierData };
}

// Export functions for use in different environments
if (typeof module !== 'undefined' && module.exports) {
    // Node.js environment
    module.exports = {
        processWebhookData,
        extractMembersForZapier,
        testProcessor
    };
} else if (typeof window !== 'undefined') {
    // Browser environment
    window.WebhookProcessor = {
        processWebhookData,
        extractMembersForZapier,
        testProcessor
    };
}

// Auto-run test if this script is executed directly
if (typeof require !== 'undefined' && require.main === module) {
    testProcessor();
}
