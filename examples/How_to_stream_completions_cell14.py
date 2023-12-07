# Example of an OpenAI Completion request
# https://beta.openai.com/docs/api-reference/completions/create

# record the time before the request is sent
start_time = time.time()

# send a Completion request to count to 100
response = openai.Completion.create(
    model='text-davinci-002',
    prompt='1,2,3,',
    max_tokens=193,
    temperature=0,
)

# calculate the time it took to receive the response
response_time = time.time() - start_time

# extract the text from the response
completion_text = response['choices'][0]['text']

# print the time delay and text received
print(f"Full response received {response_time:.2f} seconds after request")
print(f"Full text received: {completion_text}")