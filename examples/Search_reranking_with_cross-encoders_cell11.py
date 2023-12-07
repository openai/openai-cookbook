content = result_list[0]["title"] + ": " + result_list[0]["summary"]

# Set logprobs to 1 so our response will include the most probable token the model identified
response = openai.Completion.create(
    model="text-davinci-003",
    prompt=prompt.format(query=query, document=content),
    temperature=0,
    logprobs=1,
    logit_bias={3363: 1, 1400: 1},
    max_tokens=1,
)