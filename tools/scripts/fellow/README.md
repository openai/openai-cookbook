# Fellow Meeting App MCP Server

## Overview

This is a Model Context Protocol (MCP) server implementation that integrates with Fellow's meeting management API. The server provides tools for AI agents (like Cursor) to interact with Fellow's meeting app, enabling access to contacts, meetings, transcripts, and copilot features.

## Features

- **📞 List Contacts** - Retrieve contacts with date filtering (today's contacts, this week, etc.)
- **📅 List Meetings** - Get meetings with status and date filters, optionally include transcripts  
- **📝 Get Transcripts** - Retrieve meeting transcripts in various formats with speaker identification

## Installation

### Prerequisites

- Node.js (v18 or later)
- npm or yarn
- Fellow App API key

### Setup

1. **Clone/Navigate to the directory:**
   ```bash
   cd /path/to/openai-cookbook/tools/scripts/fellow
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure your Fellow API credentials:**
   
   Create a `.env` file with your Fellow API configuration:
   ```bash
   # Fellow Meeting App API Configuration
   # Replace with your workspace-specific API URL
   API_URL=https://your-workspace.fellow.app/api/v1
   API_KEY=your_fellow_api_key_here
   
   # Optional: Workspace identifier if needed separately  
   WORKSPACE_ID=your_workspace_id
   
   # Optional: For debugging
   DEBUG=false
   ```

4. **Get your Fellow API key:**
   - Go to your Fellow account settings
   - Navigate to "API Tokens" or "Developer tools"
   - Create a new API key
   - **Important:** Determine your correct API URL (see Troubleshooting section)

5. **Test locally (optional):**
   ```bash
   npm run dev
   ```

## Cursor Integration

Add this server to your Cursor MCP settings (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "fellow-meeting": {
      "command": "node",
      "args": [
        "/path/to/openai-cookbook/tools/scripts/fellow/src/index.js"
      ],
      "env": {
        "API_URL": "https://your-workspace.fellow.app/api/v1",
        "API_KEY": "your_fellow_api_key_here"
      }
    }
  }
}
```

**After adding the configuration:**
1. **Restart Cursor completely**
2. **Wait for MCP servers to initialize**
3. **Test the tools**

## Available Tools

### 1. `list_contacts`
Get contacts from Fellow with date filtering.

**Parameters:**
- `date_filter` (string): "today" (default), "this_week", "this_month", or "YYYY-MM-DD"
- `limit` (number): Max results (default: 50, max: 500)
- `offset` (number): Pagination offset (default: 0)

**Example:**
```javascript
// Get today's contacts
list_contacts({ date_filter: "today", limit: 10 })

// Get contacts from specific date
list_contacts({ date_filter: "2025-08-30", limit: 25 })
```

### 2. `list_meetings`
Retrieve meetings with various filters.

**Parameters:**
- `date_filter` (string): "today" (default), "this_week", "this_month", or "YYYY-MM-DD"
- `status` (string): "scheduled", "completed", "cancelled", or "in_progress"
- `limit` (number): Max results (default: 50, max: 500)
- `offset` (number): Pagination offset (default: 0)
- `include_transcripts` (boolean): Include transcript data (default: false)

**Example:**
```javascript
// Get today's completed meetings with transcripts
list_meetings({ 
  date_filter: "today", 
  status: "completed", 
  include_transcripts: true,
  limit: 20
})
```

### 3. `get_transcript`
Get transcript content for a specific meeting.

**Parameters:**
- `meeting_id` (string, required): The meeting ID
- `format` (string): "text" (default), "structured", "srt", or "vtt"
- `include_speakers` (boolean): Include speaker names (default: true)
- `include_timestamps` (boolean): Include timestamps (default: true)

**Example:**
```javascript
// Get structured transcript with speakers and timestamps
get_transcript({
  meeting_id: "meeting_12345",
  format: "structured",
  include_speakers: true,
  include_timestamps: true
})
```

## Troubleshooting

### Authentication Issues

**Problem:** Getting 401 "Unable to decode token" or 404 "No Workspace" errors.

**Solution:** Fellow's API likely uses workspace-specific URLs. Try these steps:

1. **Check your Fellow workspace URL** - Your API URL should match your workspace:
   - If you access Fellow at `https://yourcompany.fellow.app`, try:
   - `https://yourcompany.fellow.app/api/v1` or 
   - `https://api.yourcompany.fellow.app/v1`

2. **Verify API key scope** - Make sure your API key has the necessary permissions:
   - Contacts access
   - Meetings access  
   - Transcript access

3. **Contact Fellow support** - If still having issues:
   - Email: help@fellow.co
   - Ask for the correct API base URL for your workspace
   - Verify your API key permissions

### Testing API Connectivity

Test your API connection directly:

```bash
# Test API connectivity (replace with your details)
curl -H "Authorization: Bearer YOUR_API_KEY" \\
     -H "Content-Type: application/json" \\
     "https://your-workspace.fellow.app/api/v1/contacts"
```

### Enable Debug Mode

Set `DEBUG=true` in your environment to see detailed API request/response logs:

```bash
DEBUG=true npm start
```

## Architecture

```
src/
├── index.js                 # Main MCP server entry point
├── fellow.js               # Fellow API client with error handling
├── tools/
│   ├── toolSchemas.js      # Tool definitions for MCP protocol
│   ├── handlers.js         # Tool handler mappings
│   ├── contacts/           # Contact-related tools
│   │   ├── index.js        
│   │   └── list.js         # List contacts with date filtering
│   ├── meetings/           # Meeting-related tools
│   │   ├── index.js
│   │   └── list.js         # List meetings with status/date filters
│   └── transcripts/        # Transcript-related tools
│       ├── index.js
│       └── get.js          # Get meeting transcripts
```

## Development

### Adding New Tools

1. Create a new tool file in the appropriate directory
2. Follow the existing tool pattern:

```javascript
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import { fellowClient } from "../../fellow.js";

const toolSchema = {
  name: "your_tool_name",
  description: "What your tool does",
  inputSchema: {
    type: "object",
    properties: {
      // Define parameters
    },
    required: ["required_param"],
  },
};

async function yourToolHandler({ param1 }) {
  try {
    const response = await fellowClient.get('/your-endpoint', { params: { param1 } });
    return response.data;
  } catch (error) {
    throw new McpError(ErrorCode.InvalidRequest, error.message);
  }
}

export { toolSchema, yourToolHandler as handler };
```

3. Add to the appropriate `index.js` export file

### Testing

```bash
# Run with file watching for development
npm run dev

# Test specific tool
echo '{"method": "tools/call", "params": {"name": "list_contacts", "arguments": {"date_filter": "today"}}}' | npm start
```

## Credits

This project uses:
- [Model Context Protocol SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Fellow API](https://developers.fellow.ai/) 
- [Axios](https://github.com/axios/axios) for HTTP requests

## License

MIT License


