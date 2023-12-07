# Best practice
from openai import OpenAI

client = OpenAI()
from tenacity import retry, wait_random_exponential, stop_after_attempt

# Retry up to 6 times with exponential backoff, starting at 1 second and maxing out at 20 seconds delay
@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6))
def get_embedding(text: str, model="text-embedding-ada-002") -> list[float]:
    return client.embeddings.create(input=[text], model=model)["data"][0]["embedding"]

embedding = get_embedding("Your text goes here", model="text-embedding-ada-002")
print(len(embedding))