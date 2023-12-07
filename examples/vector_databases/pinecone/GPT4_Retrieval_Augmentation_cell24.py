from openai import OpenAI

client = OpenAI(api_key="sk-...")

# initialize openai API key
  #platform.openai.com

embed_model = "text-embedding-ada-002"

res = client.embeddings.create(input=[
    "Sample document text goes here",
    "there will be several phrases in each batch"
], engine=embed_model)