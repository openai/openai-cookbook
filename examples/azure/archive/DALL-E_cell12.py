from azure.identity import DefaultAzureCredential

if use_azure_active_directory:
    default_credential = DefaultAzureCredential()
    token = default_credential.get_token("https://cognitiveservices.azure.com/.default")

    