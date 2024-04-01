import csv
import json
import random
from chromadb.utils import embedding_functions

def generate_random_values(n):
    return [random.uniform(-1, 1) for _ in range(n)]

# longest title is 141, round up to 256
# longest definition is 1658, round up to 2048
# vector dimension is 384 for all-MiniLM-L6-v2 and 768 for multi-qa-mpnet-base-dot-v1

key = 0
def next_key():
    global key
    key += 1
    return key

# EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_MODEL = "multi-qa-mpnet-base-dot-v1"
embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

def compute_embedding(row):
    text = row['Class title'] + ': ' + row['Class definition']
    return embedding_func(input=[text])[0]

def read_noc_data():
    filename = 'data/NOC-2021-v1.0/NOCs without TEER.csv'
    with open(filename) as noc_file:
        return [
            {
                'primary_key': next_key(), 
                'noc_code': int(row['Code - NOC 2021 V1.0 as number']),
                'title': row['Class title'],
                'definition': row['Class definition'],
                'vector': compute_embedding(row)
            } for row in csv.DictReader(noc_file)
        ]

noc_codes = read_noc_data()

valid_noc_codes = [code for code in noc_codes 
                        if code['noc_code'] not in [11, 1, 0, 14, 12, 13, 10]]

with open('noc_data.json', 'w') as json_file:
    json.dump(valid_noc_codes, json_file, indent=4)

print('embedding vector length is ' + str(len(valid_noc_codes[0]['vector'])))
