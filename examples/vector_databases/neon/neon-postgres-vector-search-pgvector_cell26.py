# Query based on `content_vector` embeddings
query_results = query_neon("Famous battles in Greek history", "Articles", "content_vector")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")