import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import { fellowClient } from "../../fellow.js";

const toolSchema = {
  name: "get_recording",
  description: "Retrieve recording data including transcript content for a specific recording by recording ID",
  inputSchema: {
    type: "object",
    properties: {
      recording_id: {
        type: "string",
        description: "The ID of the recording to retrieve",
      },
      format: {
        type: "string", 
        description: "Transcript format preference",
        enum: ["text", "structured", "srt", "vtt"],
        default: "text"
      },
      include_speakers: {
        type: "boolean",
        description: "Whether to include speaker identification (default: true)",
        default: true
      },
      include_timestamps: {
        type: "boolean",
        description: "Whether to include timestamps (default: true)", 
        default: true
      }
    },
    required: ["recording_id"],
    additionalProperties: false
  },
};

async function getRecording({ 
  recording_id, 
  format = "text", 
  include_speakers = true, 
  include_timestamps = true 
}) {
  try {
    // Build query parameters
    const params = {
      format,
      include_speakers,
      include_timestamps
    };

    // Use Fellow's actual Retrieve Recording API endpoint (GET method)
    console.log(`Retrieving recording ${recording_id} with params:`, params);
    const response = await fellowClient.get(`/recording/${recording_id}`);

    // Handle Fellow API response structure
    const data = response.data?.data || response.data || {};
    
    return {
      success: true,
      recording_id,
      format,
      recording: data,
      api_endpoint_used: `/recording/${recording_id}`,
      metadata: {
        include_speakers,
        include_timestamps,
        content_length: typeof data === 'string' ? data.length : JSON.stringify(data).length
      }
    };

  } catch (error) {
    console.error('Get transcript error:', error);
    
    if (error.response) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `Fellow API error (${error.response.status}): ${error.response.statusText}. ${error.response.data?.message || `Could not retrieve recording ${recording_id}`}`
      );
    } else if (error.request) {
      throw new McpError(
        ErrorCode.InternalError,
        `Network error connecting to Fellow API: ${error.message}`
      );
    } else {
      throw new McpError(
        ErrorCode.InternalError,
        `Error retrieving recording: ${error.message}`
      );
    }
  }
}

export { toolSchema, getRecording as handler };


