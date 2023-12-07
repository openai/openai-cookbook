def chat_completion_request(messages, functions=None, function_call='auto', 
                            model_name=GPT_MODEL):
    
    if functions is not None:
        return openai.ChatCompletion.create(
            model=model_name,
            messages=messages,
            functions=functions,
            function_call=function_call)
    else:
        return openai.ChatCompletion.create(
            model=model_name,
            messages=messages)