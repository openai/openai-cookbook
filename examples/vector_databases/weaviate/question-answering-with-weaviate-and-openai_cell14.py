### STEP 1 - load the dataset

from datasets import load_dataset
from typing import List, Iterator

# We'll use the datasets library to pull the Simple Wikipedia dataset for embedding
dataset = list(load_dataset("wikipedia", "20220301.simple")["train"])

# For testing, limited to 2.5k articles for demo purposes
dataset = dataset[:2_500]

# Limited to 25k articles for larger demo purposes
# dataset = dataset[:25_000]

# for free OpenAI acounts, you can use 50 objects
# dataset = dataset[:50]