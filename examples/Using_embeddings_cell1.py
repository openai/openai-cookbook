import openai

embedding = openai.Embedding.create(
    input="Your text goes here", model="text-embedding-ada-002"
)["data"][0]["embedding"]
len(embedding)
