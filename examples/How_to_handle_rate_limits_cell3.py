from openai import OpenAI # for making OpenAI API requests
client = OpenAI()

# request a bunch of completions in a loop
for _ in range(100):
    client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10,
    )