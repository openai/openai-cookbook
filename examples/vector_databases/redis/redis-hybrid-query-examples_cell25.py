# hybrid query for shirt in the product vector and only include results with the phrase "slim fit" in the title
results = search_redis(redis_client,
                       "shirt",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@productDisplayName:"slim fit"'
                       )
