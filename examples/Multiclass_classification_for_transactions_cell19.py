from transformers import GPT2TokenizerFast
tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

df['n_tokens'] = df.combined.apply(lambda x: len(tokenizer.encode(x)))
len(df)
