def query_tair(client, query, vector_name="title_vector", top_k=5):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input= query,
        model="text-embedding-ada-002",
    )["data"][0]['embedding']
    embedded_query = np.array(embedded_query)

    # search for the top k approximate nearest neighbors of vector in an index
    query_result = client.tvs_knnsearch(index=index+"_"+vector_name, k=top_k, vector=embedded_query)

    return query_result