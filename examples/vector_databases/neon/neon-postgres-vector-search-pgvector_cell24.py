# Query based on `title_vector` embeddings
import openai

query_results = query_neon("Greek mythology", "Articles")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")