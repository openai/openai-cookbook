messages = []
messages.append({"role": "system", "content": "Answer user questions by generating SQL queries against the Chinook Music Database."})
messages.append({"role": "user", "content": "Hi, who are the top 5 artists by number of tracks?"})
chat_response = chat_completion_request(messages, tools)
assistant_message = chat_response.json()["choices"][0]["message"]
assistant_message['content'] = str(assistant_message["tool_calls"][0]["function"])
messages.append(assistant_message)
if assistant_message.get("tool_calls"):
    results = execute_function_call(assistant_message)
    messages.append({"role": "tool", "tool_call_id": assistant_message["tool_calls"][0]['id'], "name": assistant_message["tool_calls"][0]["function"]["name"], "content": results})
pretty_print_conversation(messages)