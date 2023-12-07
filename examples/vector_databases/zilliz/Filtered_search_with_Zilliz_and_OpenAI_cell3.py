import openai

URI = 'your_uri'
TOKEN = 'your_token' # TOKEN == user:password or api_key
COLLECTION_NAME = 'book_search'
DIMENSION = 1536
OPENAI_ENGINE = 'text-embedding-ada-002'

INDEX_PARAM = {
    'metric_type':'L2',
    'index_type':"AUTOINDEX",
    'params':{}
}

QUERY_PARAM = {
    "metric_type": "L2",
    "params": {},
}

BATCH_SIZE = 1000