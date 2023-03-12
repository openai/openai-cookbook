#!/bin/bash
set -e

echo "Starting Python server..."

pip install virtualenv
python -m virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
OPENAI_API_KEY=$1 python app.py
