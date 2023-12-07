import openai
from transformers import GPT2Tokenizer

# OpenAI GPT-2 tokenizer is the same as GPT-3 tokenizer
# we use it to count the number of tokens in the text
tokenizer = GPT2Tokenizer.from_pretrained("gpt2")

with open("data/geometry_slovenian.tex", "r") as f:
    text = f.read()