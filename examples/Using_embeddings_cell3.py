# Negative example (slow and rate-limited)
from openai import OpenAI

client = OpenAI()

num_embeddings = 10000 # Some large number
for i in range(num_embeddings):
    embedding = client.embeddings.create(input="Your text goes here", model="text-embedding-ada-002")["data"][0]["embedding"]
    print(len(embedding))