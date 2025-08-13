#!/bin/bash

# Intercom Analytics Convenience Script
# This script provides easy access to common Intercom analytics tasks

# Default values
OUTPUT_DIR="intercom_reports"
LIMIT=1000

# Function to display help
show_help() {
    echo "Intercom Analytics Tool"
    echo "======================="
    echo
    echo "Usage: ./analyze_intercom.sh [command] [options]"
    echo
    echo "Commands:"
    echo "  last-month        Analyze conversations from the last month"
    echo "  last-week         Analyze conversations from the last 7 days"
    echo "  date-range        Analyze conversations from a specific date range"
    echo "  from-csv          Analyze conversations from a CSV file"
    echo "  help              Display this help message"
    echo
    echo "Options:"
    echo "  --output-dir DIR  Set output directory (default: $OUTPUT_DIR)"
    echo "  --limit N         Limit number of conversations (default: $LIMIT)"
    echo "  --export-zip      Export results to a zip file"
    echo
    echo "Examples:"
    echo "  ./analyze_intercom.sh last-month"
    echo "  ./analyze_intercom.sh last-week --export-zip"
    echo "  ./analyze_intercom.sh date-range 2023-01-01 2023-01-31 --output-dir january_report"
    echo "  ./analyze_intercom.sh from-csv recent-conversations.csv"
    echo
}

# Function to check Python and dependencies
check_environment() {
    # Check if Python is installed
    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 is required but not found"
        exit 1
    fi
    
    # Check if run_intercom_analysis.py exists
    if [ ! -f "run_intercom_analysis.py" ]; then
        echo "Error: run_intercom_analysis.py not found in the current directory"
        exit 1
    fi
    
    # Make the script executable if it's not
    if [ ! -x "run_intercom_analysis.py" ]; then
        chmod +x run_intercom_analysis.py
    fi
}

# Parse command line arguments
COMMAND=""
COMMAND_ARGS=""
SCRIPT_ARGS=""

# If no arguments provided, show help
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Parse the command
COMMAND="$1"
shift

# Process command-specific arguments and options
case "$COMMAND" in
    "last-month")
        COMMAND_ARGS="--last-month"
        ;;
    "last-week")
        COMMAND_ARGS="--days 7"
        ;;
    "date-range")
        if [ $# -lt 2 ]; then
            echo "Error: date-range command requires START_DATE and END_DATE"
            echo "Usage: ./analyze_intercom.sh date-range YYYY-MM-DD YYYY-MM-DD [options]"
            exit 1
        fi
        COMMAND_ARGS="--date-range $1 $2"
        shift 2
        ;;
    "from-csv")
        if [ $# -lt 1 ]; then
            echo "Error: from-csv command requires a CSV file path"
            echo "Usage: ./analyze_intercom.sh from-csv path/to/file.csv [options]"
            exit 1
        fi
        if [ ! -f "$1" ]; then
            echo "Error: CSV file '$1' not found"
            exit 1
        fi
        COMMAND_ARGS="--csv-file $1"
        shift
        ;;
    "help")
        show_help
        exit 0
        ;;
    *)
        echo "Error: Unknown command '$COMMAND'"
        show_help
        exit 1
        ;;
esac

# Process remaining options
while [ $# -gt 0 ]; do
    case "$1" in
        --output-dir)
            if [ -z "$2" ]; then
                echo "Error: --output-dir requires a directory path"
                exit 1
            fi
            SCRIPT_ARGS="$SCRIPT_ARGS --output-dir $2"
            shift 2
            ;;
        --limit)
            if [ -z "$2" ]; then
                echo "Error: --limit requires a number"
                exit 1
            fi
            SCRIPT_ARGS="$SCRIPT_ARGS --limit $2"
            shift 2
            ;;
        --export-zip)
            SCRIPT_ARGS="$SCRIPT_ARGS --export-zip"
            shift
            ;;
        *)
            echo "Warning: Unknown option '$1' - ignoring"
            shift
            ;;
    esac
done

# Check environment before running
check_environment

# Run the analysis
echo "Running Intercom Analytics..."
python3 run_intercom_analysis.py $COMMAND_ARGS $SCRIPT_ARGS

# Check if the command was successful
if [ $? -eq 0 ]; then
    echo "Analysis completed successfully!"
else
    echo "Analysis failed. Check error messages above."
    exit 1
fi 