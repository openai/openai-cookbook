messages.append(
    {
        "role": "function",
        "name": "get_current_weather",
        "content": json.dumps(response)
    }
)

function_completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    functions=functions,
)

print(function_completion.choices[0].message.content.strip())