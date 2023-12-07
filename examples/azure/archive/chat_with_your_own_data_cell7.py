openai.api_base = os.environ["OPENAI_API_BASE"]

# Azure OpenAI on your own data is only supported by the 2023-08-01-preview API version
openai.api_version = "2023-08-01-preview"