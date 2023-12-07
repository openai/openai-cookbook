completion = openai.ChatCompletion.create(
    messages=[{"role": "user", "content": "What are the differences between Azure Machine Learning and Azure AI services?"}],
    deployment_id="gpt-4",
    dataSources=[  # camelCase is intentional, as this is the format the API expects
        {
            "type": "AzureCognitiveSearch",
            "parameters": {
                "endpoint": os.environ["SEARCH_ENDPOINT"],
                "key": os.environ["SEARCH_KEY"],
                "indexName": os.environ["SEARCH_INDEX_NAME"],
            }
        }
    ]
)
print(completion)