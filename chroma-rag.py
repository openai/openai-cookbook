import csv
import os
import chromadb
from chromadb.utils import embedding_functions

# code taken from https://realpython.com/chromadb-vector-database/

CHROMA_DATA_PATH = "./data/chroma.db/"
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "demo_docs"

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


db_exists = os.path.exists(CHROMA_DATA_PATH)

persistent_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
sentence_transformer_embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

cosine_collection = persistent_client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=sentence_transformer_embedding_func,
    metadata={"hnsw:space": "cosine"},
)

if not db_exists:
    all_noc_codes = read_noc_data()
    valid_noc_codes = [code for code in all_noc_codes 
                        if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]

    documents = ['NOC Code ' + code['noc_code'] + ': ' + code['title'] + ': ' + code['definition'] for code in valid_noc_codes]
    ids = [code['noc_code'] for code in valid_noc_codes]
    metadatas = [{'title': code['title'], 'code': code['noc_code']} for code in valid_noc_codes]

    print('loading a total of ' + str(len(documents)) + ' documents')
    cosine_collection.add(documents=documents, ids=ids, metadatas=metadatas)

query_results = cosine_collection.query( query_texts=["I need new tires on my pick up truck"], n_results=5,)

print(query_results.keys())
print(query_results["documents"])
print(query_results["ids"])
print(query_results["distances"])
print(query_results["metadatas"])
