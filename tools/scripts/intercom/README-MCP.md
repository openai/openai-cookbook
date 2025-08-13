# 🚀 Intercom MCP Server

A high-performance Model Context Protocol (MCP) server for Intercom conversation data export and analysis. This server provides AI assistants with direct access to Intercom API functionality through standardized MCP tools.

## ✨ Features

- **🔥 High-Performance Export**: Fast, concurrent export of Intercom conversations
- **📊 Conversation Analytics**: Get insights and statistics without full data export
- **🔍 Advanced Search**: Search conversations by keywords, date ranges, and states
- **🔐 Secure Configuration**: Environment-based API token management
- **⚡ MCP Protocol**: Standard Model Context Protocol for seamless AI integration
- **🛡️ Robust Error Handling**: Automatic retries and rate limit management

## 🛠️ Available Tools

### 1. `export_intercom_conversations`
Export Intercom conversations from a specific date range to CSV or JSON format.

**Parameters:**
- `from_date` (required): Start date in YYYY-MM-DD format
- `to_date` (optional): End date in YYYY-MM-DD format (defaults to today)
- `output_format` (optional): "csv" or "json" (default: "csv")
- `limit` (optional): Maximum number of conversations to export
- `include_message_content` (optional): Include full message content (default: true)

**Example Usage:**
```json
{
  "from_date": "2025-06-01",
  "to_date": "2025-06-30",
  "output_format": "csv",
  "limit": 100,
  "include_message_content": true
}
```

### 2. `get_intercom_conversation_stats`
Get statistics about conversations in a date range without full export.

**Parameters:**
- `from_date` (required): Start date in YYYY-MM-DD format
- `to_date` (optional): End date in YYYY-MM-DD format (defaults to today)

**Example Usage:**
```json
{
  "from_date": "2025-06-01",
  "to_date": "2025-06-30"
}
```

### 3. `search_intercom_conversations`
Search for specific conversations based on criteria.

**Parameters:**
- `query` (optional): Search query or keywords
- `from_date` (optional): Start date in YYYY-MM-DD format
- `to_date` (optional): End date in YYYY-MM-DD format
- `state` (optional): Conversation state - "open", "closed", or "snoozed"
- `limit` (optional): Maximum number of results (default: 50, max: 150)

**Example Usage:**
```json
{
  "query": "billing issue",
  "from_date": "2025-06-01",
  "state": "open",
  "limit": 25
}
```

## 📋 Prerequisites

- **Node.js 18+**: Required for running the MCP server
- **Intercom API Access**: Valid Intercom access token with conversations:read permissions
- **Environment Configuration**: `.env` file with API credentials

## 🚀 Installation & Setup

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone https://github.com/jonetto1978/intercom-export.git
cd intercom-export/tools/scripts/intercom

# Install MCP server dependencies
npm install --save @modelcontextprotocol/sdk axios dotenv

# Make the server executable
chmod +x mcp-intercom-server.js
```

### 2. Configure Environment Variables

Create a `.env` file in the `tools` directory:

```env
INTERCOM_ACCESS_TOKEN=your_intercom_access_token_here
```

**Getting Your Intercom Access Token:**
1. Go to your Intercom workspace settings
2. Navigate to "Developers" → "Developer Hub"
3. Create a new app or use an existing one
4. Generate an access token with `conversations:read` permissions

### 3. Test the Server

```bash
# Test the MCP server locally
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | node mcp-intercom-server.js
```

You should see a response listing the available tools.

## 🔧 Using with AI Assistants

### OpenAI Responses API (Recommended)

```bash
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "tools": [
      {
        "type": "mcp",
        "server_label": "intercom",
        "server_url": "stdio://path/to/mcp-intercom-server.js",
        "require_approval": "never"
      }
    ],
    "input": "Export all conversations from June 2025 and analyze customer sentiment"
  }'
```

### Claude Desktop (MCP Integration)

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "intercom": {
      "command": "node",
      "args": ["/path/to/mcp-intercom-server.js"],
      "env": {
        "INTERCOM_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

### Custom Applications

Use any MCP-compatible client:

```javascript
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const transport = new StdioClientTransport({
  command: 'node',
  args: ['mcp-intercom-server.js']
});

const client = new Client({
  name: "intercom-client",
  version: "1.0.0"
});

await client.connect(transport);

// Export conversations
const result = await client.callTool({
  name: "export_intercom_conversations",
  arguments: {
    from_date: "2025-06-01",
    to_date: "2025-06-30"
  }
});
```

## 📊 Example Responses

### Conversation Export Response
```json
{
  "success": true,
  "date_range": { "from": "2025-06-01", "to": "2025-06-30" },
  "total_conversations": 150,
  "total_messages": 450,
  "output_format": "csv",
  "include_message_content": true,
  "conversations_summary": [
    {
      "id": "12345",
      "created_at": 1717200000,
      "state": "closed",
      "message_count": 3
    }
  ],
  "data": "conversation_id,created_at,message_body...\n12345,2025-06-01T10:00:00Z,Hello..."
}
```

### Statistics Response
```json
{
  "success": true,
  "date_range": { "from": "2025-06-01", "to": "2025-06-30" },
  "total_conversations_found": 150,
  "sample_size": 20,
  "statistics": {
    "states": { "closed": 15, "open": 3, "snoozed": 2 },
    "avg_parts_per_conversation": 2.8,
    "assigned_conversations": 18,
    "assignment_rate": 0.9
  }
}
```

## 🔧 Configuration Options

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `INTERCOM_ACCESS_TOKEN` | Intercom API access token | ✅ Yes | - |

### Performance Tuning

The server automatically optimizes for:
- **Concurrent Processing**: Up to 10 concurrent API requests for MCP stability
- **Rate Limit Handling**: Automatic backoff and retry logic
- **Memory Management**: Batched processing to handle large datasets
- **Error Recovery**: Robust error handling with detailed logging

## 🐛 Troubleshooting

### Common Issues

**1. "INTERCOM_ACCESS_TOKEN not found"**
- Ensure `.env` file exists in the `tools` directory
- Verify the token variable name is exactly `INTERCOM_ACCESS_TOKEN`
- Check that the token has proper permissions

**2. "Rate limit exceeded"**
- The server automatically handles rate limits with exponential backoff
- For high-volume exports, consider using smaller date ranges

**3. "No conversations found"**
- Verify the date range contains actual conversations
- Check that your Intercom account has data in the specified period
- Ensure your API token has access to the conversations

**4. MCP Connection Issues**
- Verify Node.js version is 18+
- Check that all dependencies are installed correctly
- Test the server with direct JSON-RPC calls first

### Debug Mode

Run the server with debug logging:

```bash
DEBUG=1 node mcp-intercom-server.js
```

## 📦 Publishing the MCP Server

### Option 1: NPM Package

```bash
# Prepare for publishing
npm version patch
npm publish

# Install globally
npm install -g intercom-mcp-server
```

### Option 2: GitHub Release

1. Create a new release on GitHub
2. Attach the compiled server file
3. Users can download and run directly

### Option 3: Docker Container

```dockerfile
FROM node:18-alpine
COPY mcp-intercom-server.js /app/
COPY package-mcp.json /app/package.json
WORKDIR /app
RUN npm install
ENTRYPOINT ["node", "mcp-intercom-server.js"]
```

## 🔄 Migration from CLI Script

To migrate from the original `fast-export-intercom.js`:

### Before (CLI):
```bash
node fast-export-intercom.js --from 2025-06-01 --to 2025-06-30 --output conversations.csv
```

### After (MCP):
```json
{
  "tool": "export_intercom_conversations",
  "arguments": {
    "from_date": "2025-06-01",
    "to_date": "2025-06-30",
    "output_format": "csv"
  }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check this README and inline code comments
- **Issues**: Report bugs or request features on GitHub Issues
- **Colppy Team**: Contact the analytics team for internal support

---

**Made with ❤️ by the Colppy Analytics Team for smarter customer insights** 