# Example of an OpenAI Completion request, using the stream=True option
# https://beta.openai.com/docs/api-reference/completions/create

# record the time before the request is sent
start_time = time.time()

# send a Completion request to count to 100
response = openai.Completion.create(
    model='text-davinci-002',
    prompt='1,2,3,',
    max_tokens=193,
    temperature=0,
    stream=True,  # this time, we set stream=True
)

# create variables to collect the stream of events
collected_events = []
completion_text = ''
# iterate through the stream of events
for event in response:
    event_time = time.time() - start_time  # calculate the time delay of the event
    collected_events.append(event)  # save the event response
    event_text = event['choices'][0]['text']  # extract the text
    completion_text += event_text  # append the text
    print(f"Text received: {event_text} ({event_time:.2f} seconds after request)")  # print the delay and text

# print the time delay and text received
print(f"Full response received {event_time:.2f} seconds after request")
print(f"Full text received: {completion_text}")