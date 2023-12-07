def index_documents(client: redis.Redis, prefix: str, documents: pd.DataFrame):
    product_vectors = embeddings_batch_request(documents)
    records = documents.to_dict("records")
    batchsize = 500

    # Use Redis pipelines to batch calls and save on round trip network communication
    pipe = client.pipeline()
    for idx,doc in enumerate(records,start=1):
        key = f"{prefix}:{str(doc['product_id'])}"

        # create byte vectors
        text_embedding = np.array((product_vectors[idx-1]), dtype=np.float32).tobytes()

        # replace list of floats with byte vectors
        doc["product_vector"] = text_embedding

        pipe.hset(key, mapping = doc)
        if idx % batchsize == 0:
            pipe.execute()
    pipe.execute()
