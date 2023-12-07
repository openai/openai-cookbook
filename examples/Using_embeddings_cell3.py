# Negative example (slow and rate-limited)
import openai

num_embeddings = 10000 # Some large number
for i in range(num_embeddings):
    embedding = openai.Embedding.create(
        input="Your text goes here", model="text-embedding-ada-002"
    )["data"][0]["embedding"]
    print(len(embedding))