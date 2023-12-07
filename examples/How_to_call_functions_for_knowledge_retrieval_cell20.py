# Add another user message to induce our system to use the second tool
paper_conversation.add_message(
    "user",
    "Can you read the PPO sequence generation paper for me and give me a summary",
)
updated_response = chat_completion_with_function_execution(
    paper_conversation.conversation_history, functions=arxiv_functions
)
display(Markdown(updated_response["choices"][0]["message"]["content"]))
