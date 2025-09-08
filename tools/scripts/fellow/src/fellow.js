import axios from 'axios';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

const API_URL = process.env.API_URL || 'https://colppy.fellow.app/api/v1';
const API_KEY = process.env.API_KEY;
const WORKSPACE_ID = process.env.WORKSPACE_ID;

if (!API_KEY) {
  throw new Error('API_KEY environment variable is required. Please check your Fellow API key.');
}

// Create Axios client for Fellow Meeting API
const fellowClient = axios.create({
  baseURL: API_URL,
  headers: {
    'X-API-KEY': API_KEY,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  timeout: 30000,
});

// Add workspace to requests if provided
if (WORKSPACE_ID) {
  fellowClient.defaults.headers['X-Workspace-ID'] = WORKSPACE_ID;
}

// Add response interceptor for error handling and debugging
fellowClient.interceptors.request.use(
  (config) => {
    if (process.env.DEBUG === 'true') {
      console.log('Fellow API Request:', {
        method: config.method?.toUpperCase(),
        url: config.url,
        baseURL: config.baseURL,
        headers: config.headers
      });
    }
    return config;
  },
  (error) => {
    console.error('Fellow API Request Error:', error);
    return Promise.reject(error);
  }
);

fellowClient.interceptors.response.use(
  (response) => {
    if (process.env.DEBUG === 'true') {
      console.log('Fellow API Response:', {
        status: response.status,
        statusText: response.statusText,
        data: response.data
      });
    }
    return response;
  },
  (error) => {
    if (error.response) {
      console.error('Fellow API Error:', {
        status: error.response.status,
        statusText: error.response.statusText,
        data: error.response.data,
        url: error.config?.url
      });
    } else if (error.request) {
      console.error('Fellow API Network Error:', {
        message: error.message,
        url: error.config?.url
      });
    } else {
      console.error('Fellow API Error:', error.message);
    }
    throw error;
  }
);

export { fellowClient };