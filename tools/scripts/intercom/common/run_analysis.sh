#!/bin/bash

# Intercom Conversations Analysis
# This script runs all the analysis steps in sequence

echo "=== Intercom Conversations Analysis ==="
echo "Starting analysis of recent-conversations.csv..."

# Check if the CSV file exists
if [ ! -f "recent-conversations.csv" ]; then
    echo "Error: recent-conversations.csv not found!"
    echo "Please ensure the file is in the current directory."
    exit 1
fi

# Step 1: Create database schema
echo -e "\n=== Step 1: Creating database schema ==="
python3 analyze_and_prepare_db.py

# Check if previous step was successful
if [ $? -ne 0 ]; then
    echo "Error occurred during database schema creation."
    exit 1
fi

# Step 2: Import data into database
echo -e "\n=== Step 2: Importing data into database ==="
python3 import_conversations_to_db.py

# Check if previous step was successful
if [ $? -ne 0 ]; then
    echo "Error occurred during data import."
    exit 1
fi

# Step 3: Run analysis
echo -e "\n=== Step 3: Running analysis ==="
python3 analyze_conversations_db.py

# Check if previous step was successful
if [ $? -ne 0 ]; then
    echo "Error occurred during analysis."
    exit 1
fi

# Step 4: Generate visualizations
echo -e "\n=== Step 4: Generating visualizations ==="
python3 visualize_conversations.py

# Check if previous step was successful
if [ $? -ne 0 ]; then
    echo "Error occurred during visualization generation."
    exit 1
fi

echo -e "\n=== Analysis Complete ==="
echo "All steps completed successfully!"

# Check if visualizations directory exists
if [ -d "visualizations" ]; then
    echo -e "\nVisualization files:"
    ls -la visualizations/*.png
    
    # Count visualization files
    vis_count=$(ls -1 visualizations/*.png 2>/dev/null | wc -l)
    echo -e "\n$vis_count visualization files generated in the 'visualizations' directory."
fi

echo -e "\nNext steps:"
echo "1. View the visualizations in the 'visualizations' directory"
echo "2. Run custom queries with: python3 query_db.py"
echo "   - For interactive mode: python3 query_db.py"
echo "   - To see sample queries: python3 query_db.py --samples"
echo "   - To see database schema: python3 query_db.py --schema" 