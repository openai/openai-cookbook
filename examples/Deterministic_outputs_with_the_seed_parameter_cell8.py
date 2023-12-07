topic = "a journey to Mars"
system_message = "You are a helpful assistant that generates short stories."
user_request = f"Generate a short story about {topic}."

previous_response = await get_chat_response(
    system_message=system_message, user_request=user_request
)

response = await get_chat_response(
    system_message=system_message, user_request=user_request
)

# The function compare_responses is then called with the two responses as arguments.
# This function will compare the two responses and display the differences in a table.
# If no differences are found, it will print "No differences found."
compare_responses(previous_response, response)