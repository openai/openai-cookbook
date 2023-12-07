SYSTEM_MESSAGE = """
You are a helpful assistant.
Respond to the following prompt by using function_call and then summarize actions.
Ask for clarification if a user request is ambiguous.
"""

# Maximum number of function calls allowed to prevent infinite or lengthy loops
MAX_CALLS = 5


def get_openai_response(functions, messages):
    return client.chat.completions.create(
        model="gpt-3.5-turbo-16k",
        functions=functions,
        function_call="auto",  # "auto" means the model can pick between generating a message or calling a function.
        temperature=0,
        messages=messages,
    )


def process_user_instruction(functions, instruction):
    num_calls = 0
    messages = [
        {"content": SYSTEM_MESSAGE, "role": "system"},
        {"content": instruction, "role": "user"},
    ]

    while num_calls < MAX_CALLS:
        response = get_openai_response(functions, messages)
        message = response.choices[0].message
        print(message)
        try:
            message.function_call.name
            print(f"\n>> Function call #: {num_calls + 1}\n")
            pp(message.function_call)
            messages.append(message)

            # For the sake of this example, we'll simply add a message to simulate success.
            # Normally, you'd want to call the function here, and append the results to messages.
            messages.append(
                {
                    "role": "function",
                    "content": "success",
                    "name": message.function_call.name
                }
            )

            num_calls += 1
        except:
            print("\n>> Message:\n")
            print(message.content)
            break

    if num_calls >= MAX_CALLS:
        print(f"Reached max chained function calls: {MAX_CALLS}")


USER_INSTRUCTION = """
Instruction: Get all the events.
Then create a new event named AGI Party.
Then delete event with id 2456.
"""

process_user_instruction(functions, USER_INSTRUCTION)
