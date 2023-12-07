# example without a system message
response = openai.ChatCompletion.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "Explain asynchronous programming in the style of the pirate Blackbeard."},
    ],
    temperature=0,
)

print(response['choices'][0]['message']['content'])
