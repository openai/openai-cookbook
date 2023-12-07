# Add a user message
paper_conversation.add_message("user", "Hi, how does PPO reinforcement learning work?")
chat_response = chat_completion_with_function_execution(
    paper_conversation.conversation_history, functions=arxiv_functions
)
assistant_message = chat_response["choices"][0]["message"]["content"]
paper_conversation.add_message("assistant", assistant_message)
display(Markdown(assistant_message))
