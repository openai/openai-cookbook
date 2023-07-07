import openai

from typing import List, Iterator
import pandas as pd
import numpy as np
import os
import wget
from ast import literal_eval
import warnings
import zipfile
import argparse

import lancedb

def arg_parse():
    default_query = "Important battles related to the American Revolutionary War"
    global EMBEDDING_MODEL

    parser = argparse.ArgumentParser(description='Embeddings Search')
    parser.add_argument('--query', type=str, default=default_query, help='Query to search')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to show')
    parser.add_argument('--openai-key', type=str, help='OpenAI API Key')
    parser.add_argument('--model', type=str, default="text-embedding-ada-002", help='OpenAI embedding model')
    args = parser.parse_args()

    if not args.openai_key:
        if "OPENAI_API_KEY" not in os.environ:
            raise ValueError("OPENAI_API_KEY environment variable not set. Please set it or pass --openai_key")
    else:
        openai.api_key = args.openai_key
    EMBEDDING_MODEL = args.model

    return args

def embed_func(c):    
    rs = openai.Embedding.create(input=c, engine=EMBEDDING_MODEL)
    return [record["embedding"] for record in rs["data"]]

def query_article(query, tbl, top_k=5):
    # Create vector embeddings based on the user query
    emb = embed_func(query)[0]

    # Search the table for the top_k most similar results
    df = tbl.search(emb).limit(top_k).to_df()

    return df

if __name__ == "__main__":
    args = arg_parse()

    uri = "data/sample-lancedb"
    db = lancedb.connect(uri)

    table_name = "wikipedia"

    if table_name not in db.table_names():
        warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning) 
        embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

        wget.download(embeddings_url)

        with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
            zip_ref.extractall("data")

        article_df = pd.read_csv('data/vector_database_wikipedia_articles_embedded.csv')

        article_df['title_vector'] = article_df.title_vector.apply(literal_eval)
        article_df['content_vector'] = article_df.content_vector.apply(literal_eval)
        article_df['vector_id'] = article_df['vector_id'].apply(str)
        article_df.info(show_counts=True)

        article_df.rename(columns={"title_vector":"vector"}, inplace=True)

        tbl = db.create_table(table_name, data=article_df)
    else:
        tbl = db.open_table(table_name)

    results = query_article(args.query, tbl, args.top_k)

    print(results["title"])
