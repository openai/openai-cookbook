# Upsert title vectors in title namespace - this can also take a few minutes
print("Uploading vectors to title namespace..")
for batch_df in df_batcher(article_df):
    index.upsert(vectors=zip(batch_df.vector_id, batch_df.title_vector), namespace='title')