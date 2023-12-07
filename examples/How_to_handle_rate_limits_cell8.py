import backoff  # for exponential backoff
from openai import OpenAI # for OpenAI API calls
import openai
client = OpenAI()  


@backoff.on_exception(backoff.expo, openai.RateLimitError)
def completions_with_backoff(**kwargs):
    return client.chat.completions.create(**kwargs)


completions_with_backoff(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Once upon a time,"}])
