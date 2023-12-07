messages = client.beta.threads.messages.list(thread_id=thread.id)
show_json(messages)