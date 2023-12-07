import openai

# initialize openai API key
openai.api_key = "sk-..."  #platform.openai.com

embed_model = "text-embedding-ada-002"

res = openai.Embedding.create(
    input=[
        "Sample document text goes here",
        "there will be several phrases in each batch"
    ], engine=embed_model
)