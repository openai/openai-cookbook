from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="gpt-4o",
    input="Write a one-sentenecho $SHELLce bedtime story about a unicorn."
)

print(response.output_text)