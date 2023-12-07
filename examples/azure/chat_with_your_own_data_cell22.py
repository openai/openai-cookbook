response = client.chat.completions.create(
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
    },
    stream=True,
)

for chunk in response:
    delta = chunk.choices[0].delta

    if delta.role:
        print("\n"+ delta.role + ": ", end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
    if delta.model_extra.get("context"):
        print(f"Context: {delta.model_extra['context']}", end="", flush=True)