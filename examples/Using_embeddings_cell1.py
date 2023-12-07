from openai import OpenAI

client = OpenAI()

embedding = client.embeddings.create(input="Your text goes here", model="text-embedding-ada-002")["data"][0]["embedding"]
len(embedding)
