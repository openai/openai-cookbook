search_service_endpoint: str = "YOUR_AZURE_SEARCH_ENDPOINT"
search_service_api_key: str = "YOUR_AZURE_SEARCH_ADMIN_KEY"
index_name: str = "azure-cognitive-search-vector-demo"
credential = AzureKeyCredential(search_service_api_key)