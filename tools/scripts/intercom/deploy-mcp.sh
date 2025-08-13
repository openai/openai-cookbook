#!/bin/bash

# 🚀 Intercom MCP Server Deployment Script
# 
# This script prepares and deploys the Intercom MCP server for production use.

set -e  # Exit on any error

echo "🔧 Deploying Intercom MCP Server..."

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt "18" ]; then
    echo "❌ Node.js 18+ required. Current version: $(node --version)"
    exit 1
fi
echo "✅ Node.js version: $(node --version)"

# Check if .env file exists
if [ ! -f "../../.env" ]; then
    echo "❌ .env file not found in tools directory"
    echo "Please create ../../.env with INTERCOM_ACCESS_TOKEN"
    exit 1
fi

# Check if INTERCOM_ACCESS_TOKEN is set
if ! grep -q "INTERCOM_ACCESS_TOKEN" "../../.env"; then
    echo "❌ INTERCOM_ACCESS_TOKEN not found in .env file"
    exit 1
fi
echo "✅ Environment configuration found"

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Make server executable
echo "🔐 Setting permissions..."
chmod +x mcp-intercom-server.js

# Test the server
echo "🧪 Testing MCP server..."
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | timeout 10s node mcp-intercom-server.js > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ MCP server test passed"
else
    echo "❌ MCP server test failed"
    exit 1
fi

# Create symlink for global access (optional)
echo "🔗 Creating global access..."
sudo ln -sf "$(pwd)/mcp-intercom-server.js" /usr/local/bin/intercom-mcp-server 2>/dev/null || true

echo ""
echo "🎉 Deployment Complete!"
echo ""
echo "📚 Usage Examples:"
echo ""
echo "1. Test the server:"
echo "   echo '{\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"tools/list\"}' | node mcp-intercom-server.js"
echo ""
echo "2. Use with OpenAI Responses API:"
echo "   curl https://api.openai.com/v1/responses \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -H \"Authorization: Bearer \$OPENAI_API_KEY\" \\"
echo "     -d '{"
echo "       \"model\": \"gpt-4.1\","
echo "       \"tools\": [{"
echo "         \"type\": \"mcp\","
echo "         \"server_label\": \"intercom\","
echo "         \"server_url\": \"stdio://$(pwd)/mcp-intercom-server.js\","
echo "         \"require_approval\": \"never\""
echo "       }],"
echo "       \"input\": \"Export conversations from June 2025\""
echo "     }'"
echo ""
echo "3. Add to Claude Desktop config:"
echo "   {"
echo "     \"mcpServers\": {"
echo "       \"intercom\": {"
echo "         \"command\": \"node\","
echo "         \"args\": [\"$(pwd)/mcp-intercom-server.js\"]"
echo "       }"
echo "     }"
echo "   }"
echo ""
echo "📖 For full documentation, see README-MCP.md"
echo "🆘 For support, contact the Colppy Analytics Team" 