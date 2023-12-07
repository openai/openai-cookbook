average_embedding_vector = len_safe_get_embedding(long_text, average=True)
chunks_embedding_vectors = len_safe_get_embedding(long_text, average=False)

print(f"Setting average=True gives us a single {len(average_embedding_vector)}-dimensional embedding vector for our long text.")
print(f"Setting average=False gives us {len(chunks_embedding_vectors)} embedding vectors, one for each of the chunks.")
