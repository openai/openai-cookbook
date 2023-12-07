if not use_azure_active_directory:
    openai.api_type = 'azure'
    openai.api_key = os.environ["OPENAI_API_KEY"]