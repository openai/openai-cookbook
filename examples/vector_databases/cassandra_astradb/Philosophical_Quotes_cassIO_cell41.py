quote = "Animals are our equals."
# quote = "Be good."
# quote = "This teapot is strange."

metric_threshold = 0.84

quote_vector = client.embeddings.create(
    input=[quote],
    model=embedding_model_name,
).data[0].embedding

results = list(v_table.metric_ann_search(
    quote_vector,
    n=8,
    metric="cos",
    metric_threshold=metric_threshold,
))

print(f"{len(results)} quotes within the threshold:")
for idx, result in enumerate(results):
    print(f"    {idx}. [distance={result['distance']:.3f}] \"{result['body_blob'][:70]}...\"")