#!/bin/bash
# MCP Environment Activation Script
# This script activates the Python 3.11 environment with all MCP dependencies

echo "🚀 Activating MCP Environment..."
echo "Python 3.11.13 with MCP tools and dependencies"
echo "================================================"

# Activate the virtual environment
source mcp_env/bin/activate

# Show current setup
echo "✅ Environment: $(which python)"
echo "✅ Python: $(python --version)"
echo "✅ Virtual Environment: $VIRTUAL_ENV"

echo ""
echo "🎯 Ready for MCP development!"
echo "💡 To test system: python tools/scripts/mixpanel/python_system_test.py"
echo "💡 To deactivate: deactivate" 