#!/bin/bash
# Monthly PQL Analysis Runner
# ==========================
# Convenience script to run monthly PQL analysis with common options

cd "$(dirname "$0")/hubspot"

echo "🎯 COLPPY MONTHLY PQL ANALYSIS"
echo "=============================="

# Check if HubSpot API key is set
if [ -z "$HUBSPOT_API_KEY" ]; then
    echo "❌ HUBSPOT_API_KEY environment variable is required"
    echo "   Please set it in your .env file or export it:"
    echo "   export HUBSPOT_API_KEY=your_key_here"
    exit 1
fi

# Parse command line arguments
case "$1" in
    "current"|"mtd"|"")
        echo "📅 Running current month-to-date analysis..."
        python monthly_pql_analysis.py --format both
        ;;
    "last4")
        CURRENT_MONTH=$(date +%Y-%m)
        LAST_MONTH=$(date -d "1 month ago" +%Y-%m)
        MONTH_2=$(date -d "2 months ago" +%Y-%m)
        MONTH_3=$(date -d "3 months ago" +%Y-%m)
        echo "📅 Running last 4 months comparison: $MONTH_3, $MONTH_2, $LAST_MONTH, $CURRENT_MONTH"
        python monthly_pql_analysis.py --months "$MONTH_3,$MONTH_2,$LAST_MONTH,$CURRENT_MONTH" --format both
        ;;
    "may-aug-2025")
        echo "📅 Running May-August 2025 comparison..."
        python monthly_pql_analysis.py --months "2025-05,2025-06,2025-07,2025-08" --format both
        ;;
    *)
        if [[ "$1" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
            echo "📅 Running analysis for month: $1"
            python monthly_pql_analysis.py --month "$1" --format both
        else
            echo "Usage: $0 [option]"
            echo ""
            echo "Options:"
            echo "  current|mtd     - Current month-to-date (default)"
            echo "  last4          - Last 4 months comparison"
            echo "  may-aug-2025   - May-August 2025 comparison"
            echo "  YYYY-MM        - Specific month (e.g., 2025-08)"
            echo ""
            echo "Examples:"
            echo "  $0                    # Current month-to-date"
            echo "  $0 current           # Same as above"
            echo "  $0 last4             # Last 4 months"
            echo "  $0 2025-08           # August 2025 only"
            echo "  $0 may-aug-2025      # May-August 2025"
            exit 1
        fi
        ;;
esac

echo ""
echo "✅ Analysis completed! Check tools/outputs/ for results."

