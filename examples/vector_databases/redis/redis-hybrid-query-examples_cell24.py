# improve search quality by adding hybrid query for "man blue jeans" in the product vector combined with a phrase search for "blue jeans"
results = search_redis(redis_client,
                       "man blue jeans",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@productDisplayName:"blue jeans"'
                       )
