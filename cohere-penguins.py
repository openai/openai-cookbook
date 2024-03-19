import os
import cohere
from dotenv import load_dotenv

load_dotenv()
COHERE_API_KEY = os.getenv('COHERE_API_KEY')

co = cohere.Client(COHERE_API_KEY)

result = co.chat(
  model="command",
  message="Where do the tallest penguins live?",
  documents=[
    {"title": "Tall penguins", "snippet": "Emperor penguins are the tallest."},
    {"title": "Penguin habitats", "snippet": "Emperor penguins only live in Antarctica."},
    {"title": "What are animals?", "snippet": "Animals are different from plants."}
  ])

print(25*'x')
print(result.citations)
print(25*'x')
