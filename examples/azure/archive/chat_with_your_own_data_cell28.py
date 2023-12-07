response = openai.ChatCompletion.create(
    messages=[{"role": "user", "content": "What are the differences between Azure Machine Learning and Azure AI services?"}],
    deployment_id="gpt-4",
    dataSources=[
        {
            "type": "AzureCognitiveSearch",
            "parameters": {
                "endpoint": os.environ["SEARCH_ENDPOINT"],
                "key": os.environ["SEARCH_KEY"],
                "indexName": os.environ["SEARCH_INDEX_NAME"],
            }
        }
    ],
    stream=True,
)

for chunk in response:
    delta = chunk.choices[0].delta

    if "role" in delta:
        print("\n"+ delta.role + ": ", end="", flush=True)
    if "content" in delta:
        print(delta.content, end="", flush=True)
    if "context" in delta:
        print(f"Context: {delta.context}", end="", flush=True)