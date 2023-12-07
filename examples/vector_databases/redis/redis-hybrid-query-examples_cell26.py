# hybrid query for watch in the product vector and only include results with the tag "Accessories" in the masterCategory field
results = search_redis(redis_client,
                       "watch",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@masterCategory:{Accessories}'
                       )
