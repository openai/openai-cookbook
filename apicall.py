from openai import OpenAI

client = OpenAI()

# Set yer OpenAI API key here

# Make the API call
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Hello, world!"}
])

# Print the response
print(response.choices[0].message.content)