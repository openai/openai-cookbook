import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import { fellowClient } from "../../fellow.js";

const toolSchema = {
  name: "get_authenticated_user",
  description: "Get information about the authenticated user - useful for testing API connection",
  inputSchema: {
    type: "object",
    properties: {},
    additionalProperties: false
  },
};

async function getAuthenticatedUser() {
  try {
    // Use Fellow's Get Authenticated User API endpoint (GET method)
    console.log('Getting authenticated user info...');
    const response = await fellowClient.get('/me');

    // Handle Fellow API response structure
    const data = response.data?.data || response.data || {};
    
    return {
      success: true,
      user: data,
      api_endpoint_used: '/me'
    };

  } catch (error) {
    console.error('Get authenticated user error:', error);
    
    if (error.response) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `Fellow API error (${error.response.status}): ${error.response.statusText}. ${error.response.data?.message || 'Check your API key and ensure API is enabled.'}`
      );
    } else if (error.request) {
      throw new McpError(
        ErrorCode.InternalError,
        `Network error connecting to Fellow API: ${error.message}`
      );
    } else {
      throw new McpError(
        ErrorCode.InternalError,
        `Error retrieving user info: ${error.message}`
      );
    }
  }
}

export { toolSchema, getAuthenticatedUser as handler };
