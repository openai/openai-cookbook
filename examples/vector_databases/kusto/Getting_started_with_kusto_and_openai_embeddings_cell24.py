def embed(query):
    # Creates embedding vector from user query
    embedded_query = openai.embeddings.create(
            input=query,
            deployment_id="embed", #replace with your deployment id
            chunk_size=1
    )["data"][0]["embedding"]
    return embedded_query