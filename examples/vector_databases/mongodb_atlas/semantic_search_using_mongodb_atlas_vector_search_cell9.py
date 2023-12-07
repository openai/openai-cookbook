model = "text-embedding-ada-002"
def generate_embedding(text: str) -> list[float]:
    return openai.embeddings.create(input = [text], model=model).data[0].embedding
