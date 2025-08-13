#!/usr/bin/env python3
"""
Python System Test
Verifies that all the system improvements are working correctly.
"""

import sys
import subprocess
import os
from datetime import datetime

def test_python_version():
    """Test Python version is 3.11+"""
    print(f"🐍 Python Version: {sys.version}")
    major, minor = sys.version_info[:2]
    
    if major >= 3 and minor >= 11:
        print("✅ Python version is 3.11+ - Compatible with MCP")
        return True
    else:
        print("❌ Python version is too old for MCP (requires 3.11+)")
        return False

def test_virtual_environment():
    """Test if we're in a virtual environment"""
    venv_path = os.environ.get('VIRTUAL_ENV')
    if venv_path:
        print(f"✅ Virtual Environment Active: {venv_path}")
        return True
    else:
        print("❌ No virtual environment detected")
        return False

def test_package_installations():
    """Test if required packages are installed"""
    packages = [
        'mcp',
        'openai',
        'requests',
        'pandas',
        'plotly',
        'jupyter',
        'streamlit',
        'fastapi',
        'httpx'
    ]
    
    print("\n📦 Testing Package Installations:")
    all_installed = True
    
    for package in packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - Not installed")
            all_installed = False
    
    return all_installed

def test_python_command():
    """Test if python command works"""
    try:
        result = subprocess.run(['python', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ 'python' command works: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ 'python' command failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 'python' command timed out")
        return False
    except FileNotFoundError:
        print("❌ 'python' command not found")
        return False

def test_node_npm():
    """Test if Node.js and npm are available for MCP servers"""
    print("\n🟢 Testing Node.js/npm for MCP servers:")
    
    # Test Node.js
    try:
        result = subprocess.run(['node', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ Node.js: {result.stdout.strip()}")
            node_ok = True
        else:
            print(f"❌ Node.js not working: {result.stderr}")
            node_ok = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Node.js not found")
        node_ok = False
    
    # Test npm
    try:
        result = subprocess.run(['npm', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ npm: {result.stdout.strip()}")
            npm_ok = True
        else:
            print(f"❌ npm not working: {result.stderr}")
            npm_ok = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ npm not found")
        npm_ok = False
    
    # Test npx (needed for MCP servers)
    try:
        result = subprocess.run(['npx', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ npx: {result.stdout.strip()}")
            npx_ok = True
        else:
            print(f"❌ npx not working: {result.stderr}")
            npx_ok = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ npx not found")
        npx_ok = False
    
    return node_ok and npm_ok and npx_ok

def main():
    """Run all system tests"""
    print("🧪 Python System Test")
    print("=" * 50)
    print(f"🕐 Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Python Version", test_python_version),
        ("Virtual Environment", test_virtual_environment),
        ("Python Command", test_python_command),
        ("Package Installations", test_package_installations),
        ("Node.js/npm", test_node_npm)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔧 Testing {test_name}...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All systems are working correctly!")
        print("✅ Your Python environment is ready for MCP development")
        sys.exit(0)
    else:
        print("⚠️  Some issues were found")
        print("❌ Please review the failed tests above")
        sys.exit(1)

if __name__ == "__main__":
    main() 