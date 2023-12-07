def find_quote_and_author_p(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    metadata = {}
    partition_id = None
    if author:
        partition_id = author
    if tags:
        for tag in tags:
            metadata[tag] = True
    #
    results = v_table_partitioned.ann_search(
        query_vector,
        n=n,
        partition_id=partition_id,
        metadata=metadata,
    )
    return [
        (result["body_blob"], result["partition_id"])
        for result in results
    ]