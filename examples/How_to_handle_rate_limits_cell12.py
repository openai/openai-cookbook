# imports
import time
from openai import OpenAI
client = OpenAI()

# Define a function that adds a delay to a Completion API call
def delayed_completion(delay_in_seconds: float = 1, **kwargs):
    """Delay a completion by a specified amount of time."""

    # Sleep for the delay
    time.sleep(delay_in_seconds)

    # Call the Completion API and return the result
    return client.chat.completions.create(**kwargs)


# Calculate the delay based on your rate limit
rate_limit_per_minute = 20
delay = 60.0 / rate_limit_per_minute

delayed_completion(
    delay_in_seconds=delay,
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Once upon a time,"}]
)
