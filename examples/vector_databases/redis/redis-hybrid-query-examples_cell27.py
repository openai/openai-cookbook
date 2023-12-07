# hybrid query for sandals in the product vector and only include results within the 2011-2012 year range
results = search_redis(redis_client,
                       "sandals",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@year:[2011 2012]'
                       )
