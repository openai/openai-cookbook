from weave.monitoring.openai import message_from_stream
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[
        {"role": "system", "content": "You are a robot and only speak in robot, like beep bloop bop."},
        {"role": "user", "content": "Tell me a 50-word story."},
    ], stream=True)
for s in message_from_stream(r):
    print(s, end='')