from openai import OpenAI

client = OpenAI()

def query_qdrant(query, collection_name, vector_name="title", top_k=20):
    # Creates embedding vector from user query
    embedded_query = client.embeddings.create(input=query,
    model="text-embedding-ada-002")["data"][0]["embedding"]

    query_results = client.search(
        collection_name=collection_name,
        query_vector=(
            vector_name, embedded_query
        ),
        limit=top_k,
    )

    return query_results