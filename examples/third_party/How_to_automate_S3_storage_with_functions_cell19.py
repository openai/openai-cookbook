def run_conversation(user_input, topic="S3 bucket functions.", is_log=False):

    system_message=f"Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous. If the user ask question not related to {topic} response your scope is {topic} only."
    
    messages = [{"role": "system", "content": system_message},
                {"role": "user", "content": user_input}]
    
    # Call the model to get a response
    response = chat_completion_request(messages, functions=functions)
    response_message = response['choices'][0]['message']
    
    if is_log:
        print(response['choices'])
    
    # check if GPT wanted to call a function
    if response_message.get("function_call"):
        function_name = response_message['function_call']['name']
        function_args = json.loads(response_message['function_call']['arguments'])
        
        # Call the function
        function_response = available_functions[function_name](**function_args)
        
        # Add the response to the conversation
        messages.append(response_message)
        messages.append({
            "role": "function",
            "name": function_name,
            "content": function_response,
        })
        
        # Call the model again to summarize the results
        second_response = chat_completion_request(messages)
        final_message = second_response['choices'][0]['message']['content']
    else:
        final_message = response_message['content']

    return final_message