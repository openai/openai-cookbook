messages = [
    {"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."},
    {"role": "user", "content": "What's the weather like today in Seattle?"}
]

chat_completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    functions=functions,
)
print(chat_completion)