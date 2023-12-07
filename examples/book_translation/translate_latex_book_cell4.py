chunks = text.split('\n\n')
ntokens = []
for chunk in chunks:
    ntokens.append(len(tokenizer.encode(chunk)))
max(ntokens)