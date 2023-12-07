# Functions dict to pass S3 operations details for the GPT model
functions = [
    {
        "name": "list_buckets",
        "description": "List all available S3 buckets",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_objects",
        "description": "List the objects or files inside a given S3 bucket",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                "prefix": {"type": "string", "description": "The folder path in the S3 bucket"},
            },
            "required": ["bucket"],
        },
    },
    {
        "name": "download_file",
        "description": "Download a specific file from an S3 bucket to a local distribution folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                "key": {"type": "string", "description": "The path to the file inside the bucket"},
                "directory": {"type": "string", "description": "The local destination directory to download the file, should be specificed by the user."},
            },
            "required": ["bucket", "key", "directory"],
        }
    },
    {
        "name": "upload_file",
        "description": "Upload a file to an S3 bucket",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "The local source path or remote URL"},
                "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                "key": {"type": "string", "description": "The path to the file inside the bucket"},
                "is_remote_url": {"type": "boolean", "description": "Is the provided source a URL (True) or local path (False)"},
            },
            "required": ["source", "bucket", "key", "is_remote_url"],
        }
    },
    {
        "name": "search_s3_objects",
        "description": "Search for a specific file name inside an S3 bucket",
        "parameters": {
            "type": "object",
            "properties": {
                "search_name": {"type": "string", "description": "The name of the file you want to search for"},
                "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                "prefix": {"type": "string", "description": "The folder path in the S3 bucket"},
                "exact_match": {"type": "boolean", "description": "Set exact_match to True if the search should match the exact file name. Set exact_match to False to compare part of the file name string (the file contains)"}
            },
            "required": ["search_name"],
        },
    }
]