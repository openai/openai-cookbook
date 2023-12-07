SEED = 123
response = await get_chat_response(
    system_message=system_message, seed=SEED, user_request=user_request
)
previous_response = response
response = await get_chat_response(
    system_message=system_message, seed=SEED, user_request=user_request
)

compare_responses(previous_response, response)