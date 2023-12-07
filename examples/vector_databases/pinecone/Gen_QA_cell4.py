query = "who was the 12th person on the moon and when did they land?"

# now query text-davinci-003 WITHOUT context
res = openai.Completion.create(
    engine='text-davinci-003',
    prompt=query,
    temperature=0,
    max_tokens=400,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
    stop=None
)

res['choices'][0]['text'].strip()