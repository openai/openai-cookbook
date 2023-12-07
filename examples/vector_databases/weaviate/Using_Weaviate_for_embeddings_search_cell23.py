def query_weaviate(query, collection_name, top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )["data"][0]['embedding']
    
    near_vector = {"vector": embedded_query}

    # Queries input schema with vectorised user query
    query_result = (
        client.query
        .get(collection_name, ["title", "content", "_additional {certainty distance}"])
        .with_near_vector(near_vector)
        .with_limit(top_k)
        .do()
    )
    
    return query_result