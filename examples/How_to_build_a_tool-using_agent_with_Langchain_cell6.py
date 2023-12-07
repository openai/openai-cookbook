api_key = os.getenv("PINECONE_API_KEY") or "PINECONE_API_KEY"

# find environment next to your API key in the Pinecone console
env = os.getenv("PINECONE_ENVIRONMENT") or "PINECONE_ENVIRONMENT"

pinecone.init(api_key=api_key, environment=env)
pinecone.whoami()