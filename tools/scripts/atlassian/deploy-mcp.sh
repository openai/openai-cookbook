#!/bin/bash

# Atlassian MCP Server Deployment Script
# This script installs and configures the Atlassian MCP server

echo "🚀 Atlassian MCP Server Deployment"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "mcp-atlassian-server.js" ]; then
    echo "❌ Error: mcp-atlassian-server.js not found!"
    echo "Please run this script from the tools/scripts/atlassian directory"
    exit 1
fi

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js is not installed!"
    echo "Please install Node.js 18 or higher from https://nodejs.org"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v | cut -d 'v' -f 2 | cut -d '.' -f 1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Error: Node.js version 18 or higher is required!"
    echo "Current version: $(node -v)"
    exit 1
fi

echo "✅ Node.js version: $(node -v)"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install dependencies!"
    exit 1
fi

# Check for .env file
ENV_FILE="../../.env"
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "⚠️  Warning: .env file not found at $ENV_FILE"
    echo "Creating from template..."
    
    # Create .env from example if it exists
    if [ -f ".env.example" ]; then
        cp .env.example "$ENV_FILE"
        echo "✅ Created .env file from template"
        echo "📝 Please edit $ENV_FILE and add your Atlassian credentials:"
        echo "   - ATLASSIAN_DOMAIN"
        echo "   - ATLASSIAN_EMAIL"
        echo "   - ATLASSIAN_API_TOKEN"
    else
        echo "❌ Error: .env.example not found!"
        echo "Please create $ENV_FILE with the following variables:"
        echo "ATLASSIAN_DOMAIN=your-domain"
        echo "ATLASSIAN_EMAIL=your-email@company.com"
        echo "ATLASSIAN_API_TOKEN=your-api-token"
        exit 1
    fi
else
    # Check if Atlassian variables are set
    if ! grep -q "ATLASSIAN_DOMAIN" "$ENV_FILE"; then
        echo ""
        echo "⚠️  Warning: ATLASSIAN_DOMAIN not found in .env file"
        echo "Please add your Atlassian configuration to $ENV_FILE"
    else
        echo "✅ .env file found"
    fi
fi

# Create logs directory
mkdir -p logs

echo ""
echo "✅ Atlassian MCP Server is ready!"
echo ""
echo "📖 Next steps:"
echo "1. Ensure your .env file contains valid Atlassian credentials"
echo "2. Generate an API token at: https://id.atlassian.com/manage-profile/security/api-tokens"
echo "3. Run the server with: npm start"
echo ""
echo "🔧 Available commands:"
echo "   npm start    - Start the MCP server"
echo "   npm test     - Run tests (when available)"
echo ""
echo "📚 See README-MCP.md for detailed documentation"
echo ""

# Make the script executable
chmod +x mcp-atlassian-server.js

echo "✨ Deployment complete!"






