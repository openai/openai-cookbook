# For using OpenAI to generate query embedding
openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
results = search_redis(redis_client, 'modern art in Europe', k=10)