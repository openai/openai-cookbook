messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "what is the weather going to be like in San Francisco and Glasgow over the next 4 days"})
chat_response = chat_completion_request(
    messages, tools=tools, model='gpt-3.5-turbo-1106'
)

chat_response.json()
assistant_message = chat_response.json()["choices"][0]["message"]['tool_calls']
assistant_message