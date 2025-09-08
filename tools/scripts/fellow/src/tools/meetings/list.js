import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import { fellowClient } from "../../fellow.js";

const toolSchema = {
  name: "list_recordings",
  description: "Retrieve recording data from Fellow meetings with optional date filtering and status filters",
  inputSchema: {
    type: "object",
    properties: {
      date_filter: {
        type: "string",
        description: "Date filter: 'today', 'this_week', 'this_month', or specific YYYY-MM-DD format",
        default: "today"
      },
      status: {
        type: "string",
        description: "Meeting status filter",
        enum: ["scheduled", "completed", "cancelled", "in_progress"],
      },
      limit: {
        type: "number", 
        description: "Maximum number of meetings to return (default: 50)",
        default: 50,
        minimum: 1,
        maximum: 500
      },
      offset: {
        type: "number",
        description: "Pagination offset (default: 0)", 
        default: 0,
        minimum: 0
      },
      include_transcripts: {
        type: "boolean",
        description: "Whether to include transcript data (default: false)",
        default: false
      }
    },
    additionalProperties: false
  },
};

async function listRecordings({ 
  date_filter = "today", 
  status, 
  limit = 50, 
  offset = 0,
  include_transcripts = false 
}) {
  try {
    // Build query parameters
    const params = {
      limit,
      offset
    };

    // Add status filter
    if (status) {
      params.status = status;
    }

    // Add transcript inclusion
    if (include_transcripts) {
      params.include_transcripts = true;
    }

    // Add date filtering
    if (date_filter === "today") {
      const today = new Date().toISOString().split('T')[0];
      params.date = today;
    } else if (date_filter === "this_week") {
      const now = new Date();
      const weekStart = new Date(now.setDate(now.getDate() - now.getDay()));
      params.start_date = weekStart.toISOString().split('T')[0];
    } else if (date_filter === "this_month") {
      const now = new Date();
      const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
      params.start_date = monthStart.toISOString().split('T')[0];
    } else if (date_filter.match(/^\d{4}-\d{2}-\d{2}$/)) {
      params.date = date_filter;
    }

    // Use Fellow's actual Recordings API endpoint (POST method with pagination body)
    const requestBody = {
      pagination: {
        cursor: null,
        page_size: limit
      }
    };
    
    // Add filters to the request body if needed  
    if (status) {
      requestBody.status = status;
    }
    
    console.log('Calling Fellow Recordings API with body:', requestBody);
    const response = await fellowClient.post('/recordings', requestBody);

    // Handle Fellow API response structure
    const data = response.data?.data || response.data || [];
    
    return {
      success: true,
      date_filter,
      status: status || 'all',
      total_returned: Array.isArray(data) ? data.length : 0,
      recordings: data,
      api_endpoint_used: '/recordings'
    };

  } catch (error) {
    console.error('List meetings error:', error);
    
    if (error.response) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `Fellow API error (${error.response.status}): ${error.response.statusText}. ${error.response.data?.message || 'Check your API configuration.'}`
      );
    } else if (error.request) {
      throw new McpError(
        ErrorCode.InternalError,
        `Network error connecting to Fellow API: ${error.message}`
      );
    } else {
      throw new McpError(
        ErrorCode.InternalError,
        `Error retrieving recordings: ${error.message}`
      );
    }
  }
}

export { toolSchema, listRecordings as handler };


