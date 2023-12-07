# Dependencies
from datetime import date, timedelta  # date handling for fetching recent news
from IPython import display  # for pretty printing
import json  # for parsing the JSON api responses and model outputs
from numpy import dot  # for cosine similarity
import openai  # for using GPT and getting embeddings
import os  # for loading environment variables
import requests  # for making the API requests
from tqdm.notebook import tqdm  # for printing progress bars

# Load environment variables
news_api_key = os.getenv("NEWS_API_KEY")

GPT_MODEL = "gpt-3.5-turbo"


# Helper functions
def json_gpt(input: str):
    completion = openai.ChatCompletion.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "Output only valid JSON"},
            {"role": "user", "content": input},
        ],
        temperature=0.5,
    )

    text = completion.choices[0].message.content
    parsed = json.loads(text)

    return parsed


def embeddings(input: list[str]) -> list[list[str]]:
    response = openai.Embedding.create(model="text-embedding-ada-002", input=input)
    return [data.embedding for data in response.data]