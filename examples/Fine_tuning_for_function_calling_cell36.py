input_objects = []
all_but_reject = [f for f in function_list if f.get('name') != 'reject_request']

for function in all_but_reject:
    func_name = function["name"]
    params = function["parameters"]
    for arguments in generate_permutations(params):
      if any(val in arguments.values() for val in ['fill_in_int', 'fill_in_str']):
          input_object = {
              "name": func_name,
              "arguments": arguments
          }
          messages = [{"role": "user", "content": INVOCATION_FILLER_PROMPT.format(invocation=input_object,function=function)}]
          input_object = get_chat_completion(model='gpt-4',messages=messages, max_tokens = 200,temperature=.1).content
      else:
          input_object = {
              "name": func_name,
              "arguments": arguments
          }

      input_objects.append(input_object)
