{
 "cells": [
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Embedding texts that are longer than the model's maximum context length\n",
    "\n",
    "OpenAI's embedding models cannot embed text that exceeds a maximum length. The maximum length varies by model, and is measured by _tokens_, not string length. If you are unfamiliar with tokenization, check out [How to count tokens with tiktoken](How_to_count_tokens_with_tiktoken.ipynb).\n",
    "\n",
    "This notebook shows how to handle texts that are longer than a model's maximum context length. We'll demonstrate using embeddings from `text-embedding-3-small`, but the same ideas can be applied to other models and tasks. To learn more about embeddings, check out the [OpenAI Embeddings Guide](https://beta.openai.com/docs/guides/embeddings).\n"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 1. Model context length\n",
    "\n",
    "First, we select the model and define a function to get embeddings from the API."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 2,
   "metadata": {},
   "outputs": [],
   "source": [
    "from openai import OpenAI\n",
    "import os\n",
    "import openai\n",
    "from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type\n",
    "\n",
    "client = OpenAI(api_key=os.environ.get(\"OPENAI_API_KEY\", \"<your OpenAI API key if not set as env var>\"))\n",
    "\n",
    "EMBEDDING_MODEL = 'text-embedding-3-small'\n",
    "EMBEDDING_CTX_LENGTH = 8191\n",
    "EMBEDDING_ENCODING = 'cl100k_base'\n",
    "\n",
    "# let's make sure to not retry on an invalid request, because that is what we want to demonstrate\n",
    "@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6), retry=retry_if_not_exception_type(openai.BadRequestError))\n",
    "def get_embedding(text_or_tokens, model=EMBEDDING_MODEL):\n",
    "    return client.embeddings.create(input=text_or_tokens, model=model).data[0].embedding"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "The `text-embedding-3-small` model has a context length of 8191 tokens with the `cl100k_base` encoding, and we can see that going over that limit causes an error."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 4,
   "metadata": {},
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "Error code: 400 - {'error': {'message': \"This model's maximum context length is 8192 tokens, however you requested 10001 tokens (10001 in your prompt; 0 for the completion). Please reduce your prompt; or completion length.\", 'type': 'invalid_request_error', 'param': None, 'code': None}}\n"
     ]
    }
   ],
   "source": [
    "long_text = 'AGI ' * 5000\n",
    "try:\n",
    "    get_embedding(long_text)\n",
    "except openai.BadRequestError as e:\n",
    "    print(e)"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Clearly we want to avoid these errors, particularly when handling programmatically with a large number of embeddings. Yet, we still might be faced with texts that are longer than the maximum context length. Below we describe and provide recipes for the main approaches to handling these longer texts: (1) simply truncating the text to the maximum allowed length, and (2) chunking the text and embedding each chunk individually."
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 1. Truncating the input text\n",
    "\n",
    "The simplest solution is to truncate the input text to the maximum allowed length. Because the context length is measured in tokens, we have to first tokenize the text before truncating it. The API accepts inputs both in the form of text or tokens, so as long as you are careful that you are using the appropriate encoding, there is no need to convert the tokens back into string form. Below is an example of such a truncation function."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "metadata": {},
   "outputs": [],
   "source": [
    "import tiktoken\n",
    "\n",
    "def truncate_text_tokens(text, encoding_name=EMBEDDING_ENCODING, max_tokens=EMBEDDING_CTX_LENGTH):\n",
    "    \"\"\"Truncate a string to have `max_tokens` according to the given encoding.\"\"\"\n",
    "    encoding = tiktoken.get_encoding(encoding_name)\n",
    "    return encoding.encode(text)[:max_tokens]"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Our example from before now works without error."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 4,
   "metadata": {},
   "outputs": [
    {
     "data": {
      "text/plain": [
       "1536"
      ]
     },
     "execution_count": 4,
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "truncated = truncate_text_tokens(long_text)\n",
    "len(get_embedding(truncated))"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 2. Chunking the input text\n",
    "\n",
    "Though truncation works, discarding potentially relevant text is a clear drawback. Another approach is to divide the input text into chunks and then embed each chunk individually. Then, we can either use the chunk embeddings separately, or combine them in some way, such as averaging (weighted by the size of each chunk).\n",
    "\n",
    "We will take a function from [Python's own cookbook](https://docs.python.org/3/library/itertools.html#itertools-recipes) that breaks up a sequence into chunks."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 5,
   "metadata": {},
   "outputs": [],
   "source": [
    "from itertools import islice\n",
    "\n",
    "def batched(iterable, n):\n",
    "    \"\"\"Batch data into tuples of length n. The last batch may be shorter.\"\"\"\n",
    "    # batched('ABCDEFG', 3) --> ABC DEF G\n",
    "    if n < 1:\n",
    "        raise ValueError('n must be at least one')\n",
    "    it = iter(iterable)\n",
    "    while (batch := tuple(islice(it, n))):\n",
    "        yield batch"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Now we define a function that encodes a string into tokens and then breaks it up into chunks."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 6,
   "metadata": {},
   "outputs": [],
   "source": [
    "def chunked_tokens(text, encoding_name, chunk_length):\n",
    "    encoding = tiktoken.get_encoding(encoding_name)\n",
    "    tokens = encoding.encode(text)\n",
    "    chunks_iterator = batched(tokens, chunk_length)\n",
    "    yield from chunks_iterator"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Finally, we can write a function that safely handles embedding requests, even when the input text is longer than the maximum context length, by chunking the input tokens and embedding each chunk individually. The `average` flag can be set to `True` to return the weighted average of the chunk embeddings, or `False` to simply return the unmodified list of chunk embeddings."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 7,
   "metadata": {},
   "outputs": [],
   "source": [
    "import numpy as np\n",
    "\n",
    "\n",
    "def len_safe_get_embedding(text, model=EMBEDDING_MODEL, max_tokens=EMBEDDING_CTX_LENGTH, encoding_name=EMBEDDING_ENCODING, average=True):\n",
    "    chunk_embeddings = []\n",
    "    chunk_lens = []\n",
    "    for chunk in chunked_tokens(text, encoding_name=encoding_name, chunk_length=max_tokens):\n",
    "        chunk_embeddings.append(get_embedding(chunk, model=model))\n",
    "        chunk_lens.append(len(chunk))\n",
    "\n",
    "    if average:\n",
    "        chunk_embeddings = np.average(chunk_embeddings, axis=0, weights=chunk_lens)\n",
    "        chunk_embeddings = chunk_embeddings / np.linalg.norm(chunk_embeddings)  # normalizes length to 1\n",
    "        chunk_embeddings = chunk_embeddings.tolist()\n",
    "    return chunk_embeddings"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Once again, we can now handle long input texts."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 8,
   "metadata": {},
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "Setting average=True gives us a single 1536-dimensional embedding vector for our long text.\n",
      "Setting average=False gives us 2 embedding vectors, one for each of the chunks.\n"
     ]
    }
   ],
   "source": [
    "average_embedding_vector = len_safe_get_embedding(long_text, average=True)\n",
    "chunks_embedding_vectors = len_safe_get_embedding(long_text, average=False)\n",
    "\n",
    "print(f\"Setting average=True gives us a single {len(average_embedding_vector)}-dimensional embedding vector for our long text.\")\n",
    "print(f\"Setting average=False gives us {len(chunks_embedding_vectors)} embedding vectors, one for each of the chunks.\")\n"
   ]
  },
  {
   "attachments": {},
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "In some cases, it may make sense to split chunks on paragraph boundaries or sentence boundaries to help preserve the meaning of the text."
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3 (ipykernel)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.11.5"
  },
  "vscode": {
   "interpreter": {
    "hash": "365536dcbde60510dc9073d6b991cd35db2d9bac356a11f5b64279a5e6708b97"
   }
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}
