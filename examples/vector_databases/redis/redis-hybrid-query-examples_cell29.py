# hybrid query for a brown belt filtering results by a year (NUMERIC) with a specific article types (TAG) and with a brand name (TEXT)
results = search_redis(redis_client,
                       "brown belt",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='(@year:[2012 2012] @articleType:{Shirts | Belts} @productDisplayName:"Wrangler")'
                       )
