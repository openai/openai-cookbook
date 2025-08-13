# Intercom Analytics & High-Performance Export Toolkit

A comprehensive toolkit for exporting and analyzing Intercom conversation data, providing insights into customer support performance, response times, conversation volumes, and topic trends.

## Recent Updates (2024)

- **High-Performance Node.js Export**: Added `fast-export-intercom.js` for rapid, concurrent export of large Intercom datasets with robust error handling and detailed metadata extraction.
- **New CSV Structure**: Exports now include fields for creation date, owner name, user ID, company ID, message content, and more.
- **Environment-based Configuration**: Uses `.env` for secure API token management.
- **Output Directory**: Exports are saved in `intercom_reports/latest_export/` by default.
- **Legacy scripts removed**: Old Python-based exporters have been deprecated in favor of the new Node.js solution.

---

## Features

- **Fast, concurrent export** of all conversations in a date range
- **Detailed CSV output** with all key fields for analytics
- **Robust retry and error handling** for API rate limits and failures
- **Easy configuration** via `.env` file
- **Compatible with downstream analytics scripts** (Python, Jupyter, etc.)

## Requirements

- Node.js 18+
- Intercom API access token
- (Optional) Python 3.8+ for analytics scripts

## Installation & Setup

1. **Clone this repository:**
   git clone https://github.com/yourusername/intercom-analytics.git
   cd intercom-analytics

2. **Install Node.js dependencies:**
   cd scripts/intercom
   npm install

3. **Configure your Intercom API token:**
   - Create a `.env` file in the project root (not in scripts/intercom)
   - Add your Intercom API token:
     INTERCOM_ACCESS_TOKEN=your_token_here

4. **(Optional) Set up Python environment for analytics:**
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

## Usage: Fast Export Script

### Export Conversations to CSV

From the project root, run:

    node scripts/intercom/fast-export-intercom.js --from YYYY-MM-DD --to YYYY-MM-DD --output intercom_reports/latest_export/conversations-YYYYMMDD.csv

**Options:**
- `--from <date>`: Start date (YYYY-MM-DD, required)
- `--to <date>`: End date (YYYY-MM-DD, defaults to today)
- `--output <filename>`: Output CSV file (default: intercom-conversations-abril.csv)
- `--batch-size <number>`: Batch size for API requests (default: 50)
- `--max-concurrent <number>`: Max concurrent requests (default: auto, based on CPU)
- `--chunk-size <number>`: Number of conversations to process before writing to disk (default: 500)

**Example:**

    node scripts/intercom/fast-export-intercom.js --from 2025-05-13 --to 2025-05-14 --output intercom_reports/latest_export/conversations-150.csv --batch-size 50 --chunk-size 150

### Output

- The script generates a CSV file in `intercom_reports/latest_export/`.
- Each row represents a message or part of a conversation, with columns:
    - Conversation ID
    - Created At
    - Updated At
    - Message ID
    - Message Body
    - Part Type
    - Author Type
    - Author ID
    - Author Name
    - Owner Name
    - User ID
    - Company ID
    - State
    - Read

### Error Handling & Performance
- The script uses robust retry logic for API rate limits (HTTP 429) and network errors.
- Concurrency is automatically tuned for your machine, but can be overridden.
- Progress and batch writing are logged to the console.

## Analytics & Visualization

Once exported, you can analyze the CSV using Python, Jupyter, or your preferred BI tool. See the analytics scripts in `scripts/intercom/` and the main README for more details.

## Best Practices
- Always keep your `.env` file secure and never commit it to version control.
- For large exports, use a high batch size and chunk size, but monitor for API rate limits.
- Use the CSV output as the single source of truth for downstream analytics.

## Troubleshooting
- If you see API authentication errors, check your `.env` file and token validity.
- For performance issues, try lowering `--max-concurrent` or `--batch-size`.
- If you encounter file system errors, ensure the output directory exists or use `mkdir -p` to create it.

## Legacy Scripts
- The old Python-based exporters have been removed. Use the Node.js script for all new exports.
- Analytics and visualization scripts remain available in Python for downstream analysis.

## Changelog
- **2024-06**: Major update with Node.js high-performance exporter, new CSV schema, and improved documentation.

---

For questions or support, contact the Colppy analytics team.

## Team Performance Analysis

A comprehensive toolkit for analyzing Intercom conversation data, providing insights into customer support performance, response times, conversation volumes, and topic trends.

## Features

- **Team Performance Analysis**: Measure admin and team performance with response times and CSAT scores
- **Response Time Analysis**: Understand response time patterns by admin, team, and time of day
- **Conversation Metrics**: Track conversation volumes, resolution times, and key metrics
- **Topic Analysis**: Identify common topics and themes in conversations (when content is available)
- **Data Visualization**: Generate insightful charts and graphs for all metrics
- **Export Options**: Export results as CSV files or a convenient zip archive
- **Colppy-Specific Analysis**: 
  - Identifies the most mentioned Colppy modules and features
  - Categorizes different types of customer issues
  - Extracts common phrases and questions from customer conversations
  - Performs topic modeling to identify main conversation themes
  - Analyzes sentiment indicators in customer messages
  - Provides detailed analysis of specific modules when needed

## Requirements

- Python 3.8+
- PostgreSQL (for database features)
- Intercom API access token
- Required Python libraries:
  - pandas
  - numpy
  - matplotlib
  - seaborn
  - scikit-learn
  - nltk

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/intercom-analytics.git
   cd intercom-analytics
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure your Intercom API token:
   - Create a `.env` file in the project root
   - Add your Intercom API token: `INTERCOM_ACCESS_TOKEN=your_token_here`

## Usage

### Command Line Interface

The toolkit provides several ways to run analyses:

#### Using the Convenience Shell Script

The simplest way to run common analyses:

```bash
# Analyze last month's conversations
./analyze_intercom.sh last-month

# Analyze the last 7 days of conversations
./analyze_intercom.sh last-week --export-zip

# Analyze a specific date range
./analyze_intercom.sh date-range 2023-01-01 2023-01-31 --output-dir january_report

# Analyze conversations from a CSV file
./analyze_intercom.sh from-csv recent-conversations.csv
```

#### Using the Python Runner Script

For more control over the analysis:

```bash
# Analyze last month's conversations
python run_intercom_analysis.py --last-month

# Analyze the last 30 days
python run_intercom_analysis.py --days 30 --export-zip

# Analyze a specific date range
python run_intercom_analysis.py --date-range 2023-01-01 2023-01-31 --output-dir january_analysis

# Limit the number of conversations
python run_intercom_analysis.py --last-month --limit 500
```

#### Using the Core Module Directly

For the most flexibility:

```python
from intercom_analytics import IntercomAnalytics, INTERCOM_ACCESS_TOKEN

# Initialize the analytics object
analytics = IntercomAnalytics(INTERCOM_ACCESS_TOKEN, output_dir='my_analysis')

# Run a full analysis for a date range
results = analytics.run_full_analysis(
    start_date='2023-01-01', 
    end_date='2023-01-31',
    limit=1000
)

# Export results to a zip file
analytics.export_results_to_zip()
```

### Colppy Intercom Conversation Analysis

For analyzing Colppy-specific Intercom conversation data:

```bash
python analyze_colppy_may_conversations.py [options]
```

#### Options

- `--input, -i`: Input CSV file path (will auto-detect the most recent one if not specified)
- `--from-date, -f`: Start date in YYYY-MM-DD format
- `--to-date, -t`: End date in YYYY-MM-DD format
- `--output-dir, -o`: Output directory (auto-generated based on date range if not specified)
- `--detailed, -d`: Generate more detailed analysis including module-specific questions (slower)

#### Examples

1. Analyze a specific file:
```bash
python analyze_colppy_may_conversations.py --input intercom-conversations-may-2025.csv
```

2. Analyze a specific date range:
```bash
python analyze_colppy_may_conversations.py --from-date 2025-05-01 --to-date 2025-05-15
```

3. Generate detailed analysis for a time period:
```bash
python analyze_colppy_may_conversations.py --from-date 2025-05-01 --to-date 2025-05-07 --detailed
```

#### Colppy Analysis Output

The script generates a directory with analysis results, including:

- `summary_report.txt`: Overall analysis summary with key findings
- `report_data.json`: Machine-readable data for programmatic use
- `top_user_questions.txt`: Most frequently asked questions from users
- `conversation_topics.txt`: Main topics identified in conversations
- Various PNG files with visualizations (module mentions, issue types, etc.)
- Module-specific question files (when using --detailed flag)

### Database-based Analysis

For analyzing data already imported into the PostgreSQL database:

1. Create the database schema:
   ```
   python create_db_schema.py
   ```

2. Import conversation data:
   ```
   python import_conversations_to_db.py recent-conversations.csv
   ```

3. Run the analysis:
   ```
   python analyze_conversations_db.py
   ```

4. Generate visualizations:
   ```
   python visualize_conversations.py
   ```

## Output

The toolkit generates the following outputs in the specified output directory:

- **CSV files**: Raw data and metrics for further analysis
- **PNG files**: Visualizations of key metrics and trends
- **ZIP archive** (optional): All results bundled for easy sharing

## Advanced Usage

### Custom Analysis

You can use the `IntercomAnalytics` class as a library for custom analysis:

```python
from intercom_analytics import IntercomAnalytics

analytics = IntercomAnalytics(api_token, output_dir='custom_analysis')

# Get conversations
conversations = analytics.get_conversations(start_date='2023-01-01', limit=500)

# Run specific analyses
admin_metrics, team_metrics = analytics.get_team_performance(conversations, admins, teams)
admin_times, team_times, hourly_times = analytics.analyze_response_times(conversations)

# Generate specific visualizations
analytics.visualize_team_performance(admin_metrics, team_metrics)
```

### Topic Analysis

When conversation content is available, the toolkit can perform topic analysis:

```python
# Run topic analysis on a conversations DataFrame
clusters, keywords = analytics.analyze_conversation_topics(conversations_df)

# Print the top keywords for each topic cluster
for cluster, words in keywords.items():
    print(f"Cluster {cluster}: {', '.join(words)}")
```

## Troubleshooting

- **API Rate Limiting**: The toolkit includes automatic rate limit handling
- **Missing Data**: Visualization methods handle missing data gracefully
- **Database Errors**: Check PostgreSQL connection and permissions
- **CSV File Detection**: If the script cannot find any CSV files, make sure there are Intercom conversation exports in the current directory
- **Date Filtering**: If date filtering returns no results, check the date format (YYYY-MM-DD) and that the dates are within the range present in the data
- **Visualization Issues**: For visualization problems, ensure matplotlib and seaborn are properly installed

For any issues with Colppy-specific analysis, please contact the Data Analytics team.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 