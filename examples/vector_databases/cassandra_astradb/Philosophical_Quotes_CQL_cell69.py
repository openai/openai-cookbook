prepared_insertion = session.prepare(
    f"INSERT INTO {keyspace}.philosophers_cql_partitioned (quote_id, author, body, embedding_vector, tags) VALUES (?, ?, ?, ?, ?);"
)

BATCH_SIZE = 50

num_batches = ((len(philo_dataset) + BATCH_SIZE - 1) // BATCH_SIZE)

quotes_list = philo_dataset["quote"]
authors_list = philo_dataset["author"]
tags_list = philo_dataset["tags"]

print("Starting to store entries:")
for batch_i in range(num_batches):
    print("[...", end="")
    b_start = batch_i * BATCH_SIZE
    b_end = (batch_i + 1) * BATCH_SIZE
    # compute the embedding vectors for this batch
    b_emb_results = client.embeddings.create(
        input=quotes_list[b_start : b_end],
        model=embedding_model_name,
    )
    # prepare this batch's entries for insertion
    tuples_to_insert = []
    for entry_idx, emb_result in zip(range(b_start, b_end), b_emb_results.data):
        if tags_list[entry_idx]:
            tags = {
                tag
                for tag in tags_list[entry_idx].split(";")
            }
        else:
            tags = set()
        author = authors_list[entry_idx]
        quote = quotes_list[entry_idx]
        quote_id = uuid4()  # a new random ID for each quote. In a production app you'll want to have better control...
        # append a *tuple* to the list, and in the tuple the values are ordered to match "?" in the prepared statement:
        tuples_to_insert.append((quote_id, author, quote, emb_result.embedding, tags))
    # insert the batch at once through the driver's concurrent primitive
    conc_results = execute_concurrent_with_args(
        session,
        prepared_insertion,
        tuples_to_insert,
    )
    # check that all insertions succeed (better to always do this):
    if any([not success for success, _ in conc_results]):
        print("Something failed during the insertions!")
    else:
        print(f"{len(b_emb_results.data)}] ", end="")

print("\nFinished storing entries.")