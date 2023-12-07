# For all possible arguments see https://platform.openai.com/docs/api-reference/chat-completions/create
response = openai.ChatCompletion.create(
    deployment_id=deployment_id,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Knock knock."},
        {"role": "assistant", "content": "Who's there?"},
        {"role": "user", "content": "Orange."},
    ],
    temperature=0,
)

print(f"{response.choices[0].message.role}: {response.choices[0].message.content}")