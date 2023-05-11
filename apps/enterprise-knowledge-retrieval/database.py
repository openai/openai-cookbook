import ast
from math import isnan
import numpy as np
import pandas as pd
import openai
from redis import Redis as r
from redis.commands.search.query import Query

from config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    VECTOR_FIELD_NAME,
    EMBEDDINGS_MODEL,
    INDEX_NAME,
)


def get_redis_connection():
    redis_client = r(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False
    )
    return redis_client


# Make query to Redis
def query_redis(redis_conn, query, index_name, top_k=5):

    ## Creates embedding vector from user query
    embedded_query = np.array(
        openai.Embedding.create(input=query, model=EMBEDDINGS_MODEL,)["data"][
            0
        ]["embedding"],
        dtype=np.float32,
    ).tobytes()

    # prepare the query
    q = (
        Query(f"*=>[KNN {top_k} @{VECTOR_FIELD_NAME} $vec_param AS vector_score]")
        .sort_by("vector_score")
        .paging(0, top_k)
        .return_fields("vector_score", "url", "title", "content", "text_chunk_index")
        .dialect(2)
    )
    params_dict = {"vec_param": embedded_query}

    # Execute the query
    results = redis_conn.ft(index_name).search(q, query_params=params_dict)

    return results


# Get mapped documents from Redis results
def get_redis_results(redis_conn, query, index_name):

    # Get most relevant documents from Redis
    query_result = query_redis(redis_conn, query, index_name)

    # Extract info into a list
    query_result_list = []
    for i, result in enumerate(query_result.docs):
        result_order = i
        url = result.url
        title = result.title
        text = result.content
        score = result.vector_score
        query_result_list.append((result_order, url, title, text, score))

    # Display result as a DataFrame for ease of us
    result_df = pd.DataFrame(query_result_list)
    result_df.columns = ["id", "url", "title", "result", "certainty"]
    return result_df
