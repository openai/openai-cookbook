quote = "Animals are our equals."
# quote = "Be good."
# quote = "This teapot is strange."

metric_threshold = 0.92

quote_vector = client.embeddings.create(
    input=[quote],
    model=embedding_model_name,
).data[0].embedding

results_full = collection.vector_find(
    quote_vector,
    limit=8,
    fields=["quote"]
)
results = [res for res in results_full if res["$similarity"] >= metric_threshold]

print(f"{len(results)} quotes within the threshold:")
for idx, result in enumerate(results):
    print(f"    {idx}. [similarity={result['$similarity']:.3f}] \"{result['quote'][:70]}...\"")