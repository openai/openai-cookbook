def query_qdrant(query, collection_name, vector_name='title', top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )['data'][0]['embedding']
    
    query_results = qdrant.search(
        collection_name=collection_name,
        query_vector=(
            vector_name, embedded_query
        ),
        limit=top_k,
    )
    
    return query_results