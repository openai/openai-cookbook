def find_quote_and_author(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    filter_clause = {}
    if author:
        filter_clause["author"] = author
    if tags:
        filter_clause["tags"] = {}
        for tag in tags:
            filter_clause["tags"][tag] = True
    #
    results = collection.vector_find(
        query_vector,
        limit=n,
        filter=filter_clause,
        fields=["quote", "author"]
    )
    return [
        (result["quote"], result["author"])
        for result in results
    ]