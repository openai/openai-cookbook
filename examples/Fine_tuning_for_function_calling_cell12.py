@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(5))
def get_chat_completion(
    messages: list[dict[str, str]],
    model: str = "gpt-4",
    max_tokens=500,
    temperature=1.0,
    stop=None,
    functions=None,
) -> str:
    params = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'stop': stop,
    }
    if functions:
        params['functions'] = functions

    completion = client.chat.completions.create(**params)
    return completion.choices[0].message
