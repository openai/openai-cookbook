import requests
import json
from chromadb.utils import embedding_functions
import sys
import os
from dotenv import load_dotenv

load_dotenv()
ZILLIZ_ENDPOINT = os.getenv('ZILLIZ_ENDPOINT')
ZILLIZ_API_KEY = os.getenv('ZILLIZ_API_KEY')
COLLECTION_NAME = 'noc_data_cosine_all_MiniLM_L6_v2_with_384_dimensions'
EMBED_MODEL = "all-MiniLM-L6-v2"
JOB_DESCRIPTION_FOLDER = "./data/jobdescriptions/"

def read_job_description(job):
    with open(JOB_DESCRIPTION_FOLDER + job + ".txt") as file:
        return file.read()

job_description = read_job_description(sys.argv[1])

embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

job_description_vector = embedding_func(input=[job_description])[0]

url = ZILLIZ_ENDPOINT + '/v1/vector/search'

data = json.dumps({
    'collectionName': COLLECTION_NAME,
    'vector': job_description_vector,
    'outputFields': ['noc_code', 'title', 'definition']
})

headers = {
    "Authorization": "Bearer " + ZILLIZ_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

response = requests.post(url, data=data, headers=headers)

result = response.json()['data']

print('xxxxxxxxxxxxx')
print(json.dumps(result[0:10], indent=4, sort_keys=True))
print('xxxxxxxxxxxxx')
