%%time
index_documents(redis_client, PREFIX, df)
print(f"Loaded {redis_client.info()['db0']['keys']} documents in Redis search index with name: {INDEX_NAME}")
