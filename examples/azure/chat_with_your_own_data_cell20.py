completion = client.chat.completions.create(
    messages=[{"role": "user", "content": "What are the differences between Azure Machine Learning and Azure AI services?"}],
    model=deployment,
    extra_body={
        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": os.environ["SEARCH_ENDPOINT"],
                    "key": os.environ["SEARCH_KEY"],
                    "indexName": os.environ["SEARCH_INDEX_NAME"],
                }
            }
        ]
    }
)
print(f"{completion.choices[0].message.role}: {completion.choices[0].message.content}")

# `context` is in the model_extra for Azure
print(f"\nContext: {completion.choices[0].message.model_extra['context']['messages'][0]['content']}")