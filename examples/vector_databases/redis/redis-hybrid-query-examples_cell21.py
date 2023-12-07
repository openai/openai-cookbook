def search_redis(
    redis_client: redis.Redis,
    user_query: str,
    index_name: str = "product_embeddings",
    vector_field: str = "product_vector",
    return_fields: list = ["productDisplayName", "masterCategory", "gender", "season", "year", "vector_score"],
    hybrid_fields = "*",
    k: int = 20,
    print_results: bool = True,
) -> List[dict]:

    # Use OpenAI to create embedding vector from user query
    embedded_query = openai.Embedding.create(input=user_query,
                                            model="text-embedding-ada-002",
                                            )["data"][0]['embedding']

    # Prepare the Query
    base_query = f'{hybrid_fields}=>[KNN {k} @{vector_field} $vector AS vector_score]'
    query = (
        Query(base_query)
         .return_fields(*return_fields)
         .sort_by("vector_score")
         .paging(0, k)
         .dialect(2)
    )
    params_dict = {"vector": np.array(embedded_query).astype(dtype=np.float32).tobytes()}

    # perform vector search
    results = redis_client.ft(index_name).search(query, params_dict)
    if print_results:
        for i, product in enumerate(results.docs):
            score = 1 - float(product.vector_score)
            print(f"{i}. {product.productDisplayName} (Score: {round(score ,3) })")
    return results.docs
