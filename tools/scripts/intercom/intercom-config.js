// Intercom configuration
const dotenv = require('dotenv');
const path = require('path');

// Load environment variables from .env file in the project root
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

// Export Intercom access token from environment variables
const INTERCOM_ACCESS_TOKEN = process.env.INTERCOM_ACCESS_TOKEN;

if (!INTERCOM_ACCESS_TOKEN) {
        console.warn('Warning: INTERCOM_ACCESS_TOKEN is not set in the environment variables');
}

module.exports = {
        INTERCOM_ACCESS_TOKEN
}; 