tokens = [" Yes", " No"]
tokenizer = tiktoken.encoding_for_model("text-davinci-003")
ids = [tokenizer.encode(token) for token in tokens]
ids[0], ids[1]