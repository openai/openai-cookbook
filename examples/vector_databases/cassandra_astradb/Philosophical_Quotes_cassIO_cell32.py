def find_quote_and_author(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    metadata = {}
    if author:
        metadata["author"] = author
    if tags:
        for tag in tags:
            metadata[tag] = True
    #
    results = v_table.ann_search(
        query_vector,
        n=n,
        metadata=metadata,
    )
    return [
        (result["body_blob"], result["metadata"]["author"])
        for result in results
    ]