# Python Environment Setup Guide

This guide documents the Python environment setup for MCP (Model Context Protocol) development.

## ✅ What Was Fixed

The original issues were:
1. **No `python` command** - Only `python3` was available
2. **Python version too old** - System had Python 3.9.6, but MCP requires Python ≥ 3.10
3. **Missing MCP package** - Could not install due to version requirement
4. **Virtual environment incompatibility** - Old venv was built with Python 3.9

## 🔧 Solutions Implemented

### 1. Installed Python 3.11 via Homebrew
```bash
brew install python@3.11
```

### 2. Updated Shell Configuration
Added to `~/.zshrc`:
```bash
export PATH="/opt/homebrew/opt/python@3.11/libexec/bin:$PATH"
```

This provides:
- ✅ `python` command (not just `python3`)
- ✅ `pip` command (not just `pip3`)
- ✅ Python 3.11.13 compatibility

### 3. Created New Virtual Environment
```bash
python -m venv mcp_env
```

### 4. Installed All Dependencies
```bash
source mcp_env/bin/activate
pip install mcp
pip install -r requirements.txt
```

## 🚀 How to Use

### Option 1: Use the Activation Script
```bash
# From the project root
source activate_mcp.sh
```

### Option 2: Manual Activation
```bash
# From the project root
source mcp_env/bin/activate
```

### Verify Setup
```bash
python tools/scripts/mixpanel/python_system_test.py
```

## 📦 Installed Packages

The environment includes:
- **MCP**: Model Context Protocol client library
- **OpenAI**: OpenAI API client
- **Requests**: HTTP library
- **Pandas**: Data analysis
- **Plotly**: Data visualization
- **Jupyter**: Notebook environment
- **Streamlit**: Web app framework
- **FastAPI**: API framework
- **HTTPx**: Async HTTP client
- **And all their dependencies**

## 🎯 Benefits

1. **✅ MCP Compatible**: Python 3.11+ supports all MCP features
2. **✅ Universal Commands**: Both `python` and `python3` work
3. **✅ Isolated Environment**: Clean dependencies in virtual environment
4. **✅ Future Proof**: Easy to update and maintain
5. **✅ Development Ready**: All tools for data analysis and API development

## 🔄 Environment Management

### Activate Environment
```bash
source mcp_env/bin/activate
# or
source activate_mcp.sh
```

### Deactivate Environment
```bash
deactivate
```

### Test System
```bash
python tools/scripts/mixpanel/python_system_test.py
```

### Install Additional Packages
```bash
source mcp_env/bin/activate
pip install package_name
```

### Update Requirements
```bash
source mcp_env/bin/activate
pip freeze > requirements.txt
```

## 🛠 Troubleshooting

### If `python` command not found:
1. Restart your terminal
2. Or run: `source ~/.zshrc`
3. Or use the full path: `/opt/homebrew/bin/python3.11`

### If MCP import errors:
1. Make sure you're in the virtual environment: `source mcp_env/bin/activate`
2. Check Python version: `python --version` (should be 3.11.13)
3. Reinstall MCP: `pip install --upgrade mcp`

### If old environment conflicts:
1. Deactivate old environment: `deactivate`
2. Use new environment: `source mcp_env/bin/activate`

## 📁 File Structure

```
openai-cookbook/
├── mcp_env/                    # New Python 3.11 virtual environment
├── ceo_assistant_env/          # Old Python 3.9 environment (kept for compatibility)
├── activate_mcp.sh             # Environment activation script
├── requirements.txt            # Python dependencies
└── tools/scripts/mixpanel/
    ├── python_system_test.py   # System verification script
    └── test_production_api.py  # MCP API test script
```

## 🎉 Success Verification

When properly set up, you should see:

```bash
$ python --version
Python 3.11.13

$ which python
/opt/homebrew/opt/python@3.11/libexec/bin/python

$ pip list | grep mcp
mcp                    1.9.4
```

## 💡 Next Steps

1. **Use MCP Tools**: Access Mixpanel, HubSpot, and other MCP servers
2. **Develop Scripts**: Create Python scripts with MCP integration
3. **Data Analysis**: Use Jupyter notebooks with the full environment
4. **API Development**: Build FastAPI applications with MCP backends

---

*This environment is now ready for all MCP development and data analysis tasks.* 