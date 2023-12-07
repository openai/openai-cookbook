@retry(stop=stop_after_attempt(3), wait=wait_fixed(60))
def call_openai(messages="", model="gpt-3.5-turbo"):
  return openai.ChatCompletion.create(model=model, messages=messages, max_tokens=10)