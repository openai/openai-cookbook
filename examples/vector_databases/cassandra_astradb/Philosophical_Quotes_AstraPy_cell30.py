BATCH_SIZE = 20

num_batches = ((len(philo_dataset) + BATCH_SIZE - 1) // BATCH_SIZE)

quotes_list = philo_dataset["quote"]
authors_list = philo_dataset["author"]
tags_list = philo_dataset["tags"]

print("Starting to store entries: ", end="")
for batch_i in range(num_batches):
    b_start = batch_i * BATCH_SIZE
    b_end = (batch_i + 1) * BATCH_SIZE
    # compute the embedding vectors for this batch
    b_emb_results = client.embeddings.create(
        input=quotes_list[b_start : b_end],
        model=embedding_model_name,
    )
    # prepare the documents for insertion
    b_docs = []
    for entry_idx, emb_result in zip(range(b_start, b_end), b_emb_results.data):
        if tags_list[entry_idx]:
            tags = {
                tag: True
                for tag in tags_list[entry_idx].split(";")
            }
        else:
            tags = {}
        b_docs.append({
            "quote": quotes_list[entry_idx],
            "$vector": emb_result.embedding,
            "author": authors_list[entry_idx],
            "tags": tags,
        })
    # write to the vector collection
    collection.insert_many(b_docs)
    print(f"[{len(b_docs)}]", end="")

print("\nFinished storing entries.")