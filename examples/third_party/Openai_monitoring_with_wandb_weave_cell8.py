from weave.monitoring import openai, init_monitor
m = init_monitor(f"{WB_ENTITY}/{WB_PROJECT}/{STREAM_NAME}")

# specifying a single model for simplicity
OPENAI_MODEL = 'gpt-3.5-turbo'

# prefill with some sample logs
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": "hello world!"}])
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": "what is 2+2?"}])