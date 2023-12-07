messages.append({"role": "user", "content": "What is the name of the album with the most tracks?"})
chat_response = chat_completion_request(messages, tools)
assistant_message = chat_response.json()["choices"][0]["message"]
assistant_message['content'] = str(assistant_message["tool_calls"][0]["function"])
messages.append(assistant_message)
if assistant_message.get("tool_calls"):
    results = execute_function_call(assistant_message)
    messages.append({"role": "tool", "tool_call_id": assistant_message["tool_calls"][0]['id'], "name": assistant_message["tool_calls"][0]["function"]["name"], "content": results})
pretty_print_conversation(messages)