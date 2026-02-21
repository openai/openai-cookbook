from openai import OpenAI
client = OpenAI()

response = client.responses.create(
  prompt={
    "id": "pmpt_6999fc581644819692c886b1bce271fe0102283f6bf0219f",
    "version": "1"
  }
)
