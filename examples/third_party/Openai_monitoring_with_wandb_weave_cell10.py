response = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[
        {"role": "user", "content": f"What is the meaning of life, the universe, and everything?"},
    ])
print(response['choices'][0]['message']['content'])