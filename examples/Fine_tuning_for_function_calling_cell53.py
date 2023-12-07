for eval_question in challenging_prompts:
  messages = []
  messages.append({"role": "system", "content": DRONE_SYSTEM_PROMPT})
  messages.append({"role": "user", "content": eval_question})
  completion = get_chat_completion(model="ft:gpt-3.5-turbo-0613:openai-internal::8DloQKS2",messages=messages,functions=function_list)
  print(eval_question)
  print(completion.function_call,'\n')
