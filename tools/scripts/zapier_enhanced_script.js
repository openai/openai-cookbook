// Enhanced JavaScript script for Zapier with error handling and debugging
// This version includes proper error handling and debugging information

try {
    // Debug: Log the input data to see what we're receiving
    console.log('Input data received:', typeof inputData, inputData);
    
    // Get the raw data from the previous step
    const rawData = inputData.raw || '{}';
    
    // Debug: Log the raw data
    console.log('Raw data:', rawData);
    
    // Check if rawData is valid before parsing
    if (!rawData || rawData === '{}') {
        throw new Error('No raw data received from previous step');
    }
    
    // Parse the JSON string to a JavaScript object
    const parsedData = JSON.parse(rawData);
    
    // Debug: Log the parsed data structure
    console.log('Parsed data keys:', Object.keys(parsedData));
    
    // Extract the members array from the parsed data
    const members = parsedData.parameters?.members || [];
    
    // Debug: Log member count
    console.log('Number of members found:', members.length);
    
    if (members.length === 0) {
        throw new Error('No members found in the data');
    }
    
    // Create the output array with all fields for each member
    const processedMembers = members.map((member, index) => {
        // Debug: Log each member being processed
        console.log(`Processing member ${index + 1}:`, member.$email || 'No email');
        
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
            
            // Row number for tracking
            row_number: index + 1
        };
    });
    
    // Debug: Log success
    console.log(`Successfully processed ${processedMembers.length} members`);
    
    // Set the output variable (this is what Zapier expects)
    output = processedMembers;
    
} catch (error) {
    // Error handling - log the error and provide a fallback
    console.error('Error processing webhook data:', error.message);
    
    // Set a fallback output to prevent Zap failure
    output = [{
        error: error.message,
        raw_data_received: inputData.raw ? 'Yes' : 'No',
        timestamp: new Date().toISOString()
    }];
}



