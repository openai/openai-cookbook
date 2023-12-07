client = openai.OpenAI(api_key=OPENAI_API_KEY)
embedding_model_name = "text-embedding-ada-002"

result = client.embeddings.create(
    input=[
        "This is a sentence",
        "A second sentence"
    ],
    model=embedding_model_name,
)