import requests
import json
from chromadb.utils import embedding_functions
import sys
import os
from dotenv import load_dotenv

EMBED_MODEL = "all-MiniLM-L6-v2"
embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

def read_job_description(job):
    with open("./data/jobdescriptions/" + job + ".txt") as file:
        return file.read()

job_description = read_job_description(sys.argv[1])

vector = embedding_func(input=[job_description])[0]

load_dotenv()
ZILLIZ_ENDPOINT = os.getenv('ZILLIZ_ENDPOINT')
ZILLIZ_USER = os.getenv('ZILLIZ_USER')
ZILLIZ_PASSWORD = os.getenv('ZILLIZ_PASSWORD')
ZILLIZ_BEARER = os.getenv('ZILLIZ_BEARER')
COLLECTION_NAME = 'noc_data_cosine_all_MiniLM_L6_v2_with_384_dimensions'

url = ZILLIZ_ENDPOINT + '/v1/vector/search'

data = json.dumps({
    'collectionName': COLLECTION_NAME,
    'vector': vector,
    'outputFields': ['noc_code', 'title', 'definition']
})

headers = {
    "Authorization": "Bearer " + ZILLIZ_BEARER,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

response = requests.post(url, data=data, headers=headers)

print(response.json())
