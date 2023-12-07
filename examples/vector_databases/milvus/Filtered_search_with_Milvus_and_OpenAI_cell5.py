import openai

HOST = 'localhost'
PORT = 19530
COLLECTION_NAME = 'movie_search'
DIMENSION = 1536
OPENAI_ENGINE = 'text-embedding-ada-002'
openai.api_key = 'sk-your_key'

INDEX_PARAM = {
    'metric_type':'L2',
    'index_type':"HNSW",
    'params':{'M': 8, 'efConstruction': 64}
}

QUERY_PARAM = {
    "metric_type": "L2",
    "params": {"ef": 64},
}

BATCH_SIZE = 1000