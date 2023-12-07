messages.append(
    {
        "role": "function",
        "name": "get_current_weather",
        "content": json.dumps(response)
    }
)

function_completion = openai.ChatCompletion.create(
    deployment_id="gpt-35-turbo-0613",
    messages=messages,
    functions=functions,
)

print(function_completion.choices[0].message.content.strip())