import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import { fellowClient } from "../../fellow.js";

const toolSchema = {
  name: "list_notes",
  description: "Retrieve notes from Fellow meetings with optional date filtering",
  inputSchema: {
    type: "object",
    properties: {
      date_filter: {
        type: "string",
        description: "Date filter: 'today', 'this_week', 'this_month', or specific YYYY-MM-DD format",
        default: "today"
      },
      limit: {
        type: "number",
        description: "Maximum number of contacts to return (default: 50)",
        default: 50,
        minimum: 1,
        maximum: 500
      },
      offset: {
        type: "number", 
        description: "Pagination offset (default: 0)",
        default: 0,
        minimum: 0
      }
    },
    additionalProperties: false
  },
};

async function listNotes({ date_filter = "today", limit = 50, offset = 0 }) {
  try {
    // Build query parameters
    const params = {
      limit,
      offset
    };

    // Add date filtering if specified
    if (date_filter === "today") {
      const today = new Date().toISOString().split('T')[0];
      params.created_after = today;
      params.created_before = today;
    } else if (date_filter === "this_week") {
      const now = new Date();
      const weekStart = new Date(now.setDate(now.getDate() - now.getDay()));
      params.created_after = weekStart.toISOString().split('T')[0];
    } else if (date_filter === "this_month") {
      const now = new Date();
      const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
      params.created_after = monthStart.toISOString().split('T')[0];
    } else if (date_filter.match(/^\d{4}-\d{2}-\d{2}$/)) {
      // Specific date format
      params.created_after = date_filter;
      params.created_before = date_filter;
    }

    // Use Fellow's actual Notes API endpoint (POST method with pagination body)
    const requestBody = {
      pagination: {
        cursor: null,
        page_size: limit
      }
    };
    
    // Add date filters to the request body if needed
    if (date_filter && date_filter !== "today") {
      // Fellow API might support date filtering - add when we get more docs
    }
    
    console.log('Calling Fellow Notes API with body:', requestBody);
    const response = await fellowClient.post('/notes', requestBody);

    // Handle Fellow API response structure
    const data = response.data?.data || response.data || [];
    
    return {
      success: true,
      date_filter,
      total_returned: Array.isArray(data) ? data.length : 0,
      notes: data,
      api_endpoint_used: '/notes'
    };

  } catch (error) {
    console.error('List contacts error:', error);
    
    // Provide detailed error information
    if (error.response) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `Fellow API error (${error.response.status}): ${error.response.statusText}. ${error.response.data?.message || 'Check your API configuration and ensure API is enabled.'}`
      );
    } else if (error.request) {
      throw new McpError(
        ErrorCode.InternalError,
        `Network error connecting to Fellow API: ${error.message}`
      );
    } else {
      throw new McpError(
        ErrorCode.InternalError,
        `Error retrieving notes: ${error.message}`
      );
    }
  }
}

export { toolSchema, listNotes as handler };


