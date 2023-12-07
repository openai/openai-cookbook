# Example of an OpenAI ChatCompletion request with stream=True
# https://platform.openai.com/docs/guides/chat

# a ChatCompletion request
response = openai.ChatCompletion.create(
    model='gpt-3.5-turbo',
    messages=[
        {'role': 'user', 'content': "What's 1+1? Answer in one word."}
    ],
    temperature=0,
    stream=True  # this time, we set stream=True
)

for chunk in response:
    print(chunk)