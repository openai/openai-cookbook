for prompt in straightforward_prompts:
  messages = []
  messages.append({"role": "system", "content": DRONE_SYSTEM_PROMPT})
  messages.append({"role": "user", "content": prompt})
  completion = get_chat_completion(model="gpt-3.5-turbo",messages=messages,functions=function_list)
  print(prompt)
  print(completion.function_call,'\n')
