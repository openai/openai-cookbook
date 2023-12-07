

response = openai.ChatCompletion.create(
  model=GPT_MODEL,
  messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the gold medal for curling in Olymics 2022?"},
    ]
)

print(response['choices'][0]['message']['content'])
