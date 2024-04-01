import requests
import json
from chromadb.utils import embedding_functions
import sys
import os
from dotenv import load_dotenv

load_dotenv()
ZILLIZ_ENDPOINT = os.getenv('ZILLIZ_ENDPOINT')
ZILLIZ_API_KEY = os.getenv('ZILLIZ_API_KEY')
JOB_DESCRIPTION_FOLDER = "./data/jobdescriptions/"

def read_job_description(job):
    with open(JOB_DESCRIPTION_FOLDER + job + ".txt") as file:
        return file.read()

def validate_model_arg(arg):
    if arg not in ['all-MiniLM-L6-v2', 'multi-qa-mpnet-base-dot-v1']:
        print('Invalid model argument. Use either "all-MiniLM-L6-v2" or "multi-qa-mpnet-base-dot-v1"')
        sys.exit(1)
    return arg

def get_collection(model):
    if model == 'all-MiniLM-L6-v2':
        return 'noc_data_cosine_all_MiniLM_L6_v2_with_384_dimensions'
    elif model == 'multi-qa-mpnet-base-dot-v1':
        return 'noc_data_cosine_multi_qa_mpnet_base_dot_v1_with_768_dimensions'

model_name = validate_model_arg(sys.argv[2])

collection_name = get_collection(model_name)

job_description = read_job_description(sys.argv[1])

embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)

job_description_vector = embedding_func(input=[job_description])[0]

url = f'{ZILLIZ_ENDPOINT}/v1/vector/search'

data = json.dumps({
    'collectionName': collection_name,
    'vector': job_description_vector,
    'outputFields': ['noc_code', 'title', 'definition'],
    'limit': 10
})

headers = {
    "Authorization": "Bearer " + ZILLIZ_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

response = requests.post(url, data=data, headers=headers)

result = response.json()['data']

print(json.dumps(result, indent=4, sort_keys=True))
