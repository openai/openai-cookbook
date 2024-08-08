import csv
import os
import json
import chromadb
from chromadb.utils import embedding_functions

""""
The plan
Store the NOC data in a vector database
Receive from the user a job description and maybe a top level NOC code
Use the job description to retrieve a small number of NOC codes from the 
vector database. This involves converting the query into a vector (I think 
this is done by the cosine_collection.query() call), and find closest matches.

It could be possible to retrieve just one document and use that as the NOC
code. However, if we pull a number (5 or so) documents and feed them to a
LLM, we can pull richer information, including assessment of how good the match
is.

Now prepare an LLM prompt, that will contain (1) the job description, 
(2) the closely matched NOC codes, and the question to find the best 
matching NOC code. Rather than just asking for the best matching NOC code,
it could be useful to ask for richer data, such as an explanation of how
close each of the short listed NOC codes is to the job description.

This could be a good example to follow: https://medium.com/@vndee.huynh/build-your-own-rag-and-run-it-locally-langchain-ollama-streamlit-181d42805895

"""

# code taken from https://realpython.com/chromadb-vector-database/

# Build the vector database if it doesn't exist already
CHROMA_DATA_PATH = "./data/chroma.db/"
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "noc_data"

def read_noc_data():
    filename = 'data/NOC-2021-v1.0/NOCs without TEER.csv'
    with open(filename) as noc_file:
        return [
            {
                'noc_code': str(row['Code - NOC 2021 V1.0 as number']),
                'title': row['Class title'],
                'definition': row['Class definition']
            } for row in csv.DictReader(noc_file)
        ]

def read_job_description(job):
    with open("./data/jobdescriptions/" + job + ".txt") as file:
        return file.read()

db_exists = os.path.exists(CHROMA_DATA_PATH)

persistent_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
sentence_transformer_embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

cosine_collection = persistent_client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=sentence_transformer_embedding_func,
    metadata={"hnsw:space": "cosine"},
)

print('sentence_transformer_embedding_func: ')
print(sentence_transformer_embedding_func(input="hello world"))

if not db_exists:
    all_noc_codes = read_noc_data()
    # Remove weird NOC codes that have duplicate ids
    valid_noc_codes = [code for code in all_noc_codes 
                        if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]

    print('loading a total of ' + str(len(valid_noc_codes)) + ' documents')

    documents = ['NOC Code ' + code['noc_code'] + '. Job title: ' + code['title'] + '. Description: ' + code['definition'] for code in valid_noc_codes]
    ids = [code['noc_code'] for code in valid_noc_codes]
    metadatas = [{
        'title': code['title'], 
        'code': code['noc_code'],
        'top_level_code': code['noc_code'][0],
        'teer_code': code['noc_code'][1] if len(code['noc_code']) >= 2 else 'n/a',
        } for code in valid_noc_codes]

    cosine_collection.add(documents=documents, ids=ids, metadatas=metadatas)

# Find NOC codes closely related to the job description

job_description1 = read_job_description('nutritionist')
job_description2 = read_job_description('geological_engineer')
query_results = cosine_collection.query(query_texts=[job_description1, job_description2], n_results=5)

print('keys:')
print(query_results.keys())
print('documents:')
print(query_results["documents"])
print('ids:')
print(query_results["ids"])
# distances can be used to help rank the results and distinguish really close from not so close results
print('distances:')
print(query_results["distances"])
print('metadatas:')
print(query_results["metadatas"])
