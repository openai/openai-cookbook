import os
from openai import OpenAI

client = OpenAI()
    # This is the default and can be omitted
    #api_key=os.environ.get("OPENAI_API_KEY"),


response = client.responses.create(
    model="gpt-4o-mini",
    instructions="You are a coding assistant that talks like a pirate.",
    # input="How do I check if a Python object is an instance of a class?",
    input="Make a basic test OpenAI API call using a small Python script on 'Hello world'",
)
   


print(response.output_text)