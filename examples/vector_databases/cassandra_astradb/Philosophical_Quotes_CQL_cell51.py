quote = "Animals are our equals."
# quote = "Be good."
# quote = "This teapot is strange."

similarity_threshold = 0.92

quote_vector = client.embeddings.create(
    input=[quote],
    model=embedding_model_name,
).data[0].embedding

# Once more: remember to prepare your statements in production for greater performance...

search_statement = f"""SELECT body, similarity_dot_product(embedding_vector, %s) as similarity
    FROM {keyspace}.philosophers_cql
    ORDER BY embedding_vector ANN OF %s
    LIMIT %s;
"""
query_values = (quote_vector, quote_vector, 8)

result_rows = session.execute(search_statement, query_values)
results = [
    (result_row.body, result_row.similarity)
    for result_row in result_rows
    if result_row.similarity >= similarity_threshold
]

print(f"{len(results)} quotes within the threshold:")
for idx, (r_body, r_similarity) in enumerate(results):
    print(f"    {idx}. [similarity={r_similarity:.3f}] \"{r_body[:70]}...\"")