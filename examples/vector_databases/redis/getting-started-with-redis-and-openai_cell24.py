# run a hybrid query for articles about Art in the title vector and only include results with the phrase "Leonardo da Vinci" in the text
results = search_redis(redis_client,
                       "Art",
                       vector_field="title_vector",
                       k=5,
                       hybrid_fields=create_hybrid_field("text", "Leonardo da Vinci")
                       )

# find specific mention of Leonardo da Vinci in the text that our full-text-search query returned
mention = [sentence for sentence in results[0].text.split("\n") if "Leonardo da Vinci" in sentence][0]
mention