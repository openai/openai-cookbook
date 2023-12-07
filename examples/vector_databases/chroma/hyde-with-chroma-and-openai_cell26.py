batch_size = 100

for i in range(0, len(corpus_df), batch_size):
    batch_df = corpus_df[i:i+batch_size]
    scifact_corpus_collection.add(
        ids=batch_df['doc_id'].apply(lambda x: str(x)).tolist(), # Chroma takes string IDs.
        documents=(batch_df['title'] + '. ' + batch_df['abstract'].apply(lambda x: ' '.join(x))).to_list(), # We concatenate the title and abstract.
        metadatas=[{"structured": structured} for structured in batch_df['structured'].to_list()] # We also store the metadata, though we don't use it in this example.
    )