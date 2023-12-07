response = openai.ChatCompletion.create(
    deployment_id=deployment_id,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Knock knock."},
        {"role": "assistant", "content": "Who's there?"},
        {"role": "user", "content": "Orange."},
    ],
    temperature=0,
    stream=True
)

for chunk in response:
    if len(chunk.choices) > 0:
        delta = chunk.choices[0].delta

        if "role" in delta.keys():
            print(delta.role + ": ", end="", flush=True)
        if "content" in delta.keys():
            print(delta.content, end="", flush=True)