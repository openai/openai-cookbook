def query_typesense(query, field='title', top_k=20):

    # Creates embedding vector from user query
    openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )['data'][0]['embedding']

    typesense_results = typesense_client.multi_search.perform({
        "searches": [{
            "q": "*",
            "collection": "wikipedia_articles",
            "vector_query": f"{field}_vector:([{','.join(str(v) for v in embedded_query)}], k:{top_k})"
        }]
    }, {})

    return typesense_results