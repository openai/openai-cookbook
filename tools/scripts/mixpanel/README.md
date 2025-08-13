# Mixpanel User Lookup CLI Tool

A command-line tool for looking up Mixpanel user profiles using OpenAI's MCP tools.

## Prerequisites

- Python 3.7+
- OpenAI API key with access to MCP tools
- `openai` and `python-dotenv` packages

## Installation

1. Clone the repository or download the script
2. Install the required dependencies:

```bash
pip install openai python-dotenv
```

3. Create a `.env` file in the same directory as the script with your OpenAI API key:

```
OPENAI_API_KEY=sk-your-api-key-here
```

## Usage

The script supports several ways to query Mixpanel user profiles:

### Look up a user by email

```bash
python3 mcp_user_lookup.py --email jonetto@colppy.com
```

### Look up a user by distinct ID

```bash
python3 mcp_user_lookup.py --distinct-id 12345678
```

### Get a sample of user profiles

```bash
python3 mcp_user_lookup.py --sample 10
```

### Custom query with a where clause

```bash
python3 mcp_user_lookup.py --where 'properties["plan"] == "premium"' --limit 5
```

## Additional Options

- `--limit`: Limit the number of results (default: 10)
- `--output-dir`: Specify a custom output directory
- `--model`: Specify a different OpenAI model (default: gpt-4o)

## Output

The script will:

1. Display a summary of found profiles
2. Save the full results as a JSON file in the output directory

## Examples

```bash
# Look up a user by email
python3 mcp_user_lookup.py --email jonetto@colppy.com

# Get the 5 most recent users
python3 mcp_user_lookup.py --where 'properties["$last_seen"] > "2025-05-01"' --limit 5

# Find users on the premium plan
python3 mcp_user_lookup.py --where 'properties["plan"] == "premium"' --limit 20

# Get a sample of 15 profiles
python3 mcp_user_lookup.py --sample 15
```

## Troubleshooting

- If you get an authentication error, check that your OpenAI API key is correctly set in the `.env` file
- Make sure your API key has access to the MCP tools and Mixpanel integration
- For complex queries, wrap the where clause in single quotes to avoid shell interpretation of special characters 