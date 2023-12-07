long_text = 'AGI ' * 5000
try:
    get_embedding(long_text)
except openai.InvalidRequestError as e:
    print(e)