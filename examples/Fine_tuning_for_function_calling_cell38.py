def create_commands(invocation_list):
    example_list = []
    for i, invocation in enumerate(invocation_list):
        print(f'\033[34m{np.round(100*i/len(invocation_list),1)}% complete\033[0m')
        print(invocation)

        # Format the prompt with the invocation string
        request_prompt = COMMAND_GENERATION_PROMPT.format(invocation=invocation)

        messages = [{"role": "user", "content": f"{request_prompt}"}]
        completion = get_chat_completion(messages,temperature=0.8).content
        command_dict = {
            "Input": invocation,
            "Prompt": completion
        }
        example_list.append(command_dict)
    return example_list
