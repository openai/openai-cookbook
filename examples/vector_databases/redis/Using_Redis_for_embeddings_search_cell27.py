# search the content vector for articles about famous battles in Scottish history and only include results with Scottish in the title
results = search_redis(redis_client,
                       "Famous battles in Scottish history",
                       vector_field="title_vector",
                       k=5,
                       hybrid_fields=create_hybrid_field("title", "Scottish")
                       )