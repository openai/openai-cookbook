# Option #2 - SaaS - (Weaviate Cloud Service)
client = weaviate.Client(
    url="https://your-wcs-instance-name.weaviate.network",
    additional_headers={
        "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")
    }
)