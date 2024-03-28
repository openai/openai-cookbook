import csv
import json
import chromadb
# from sentence_transformers import SentenceTransformer
from chromadb.utils import embedding_functions
default_ef = embedding_functions.DefaultEmbeddingFunction()

# read noc codes from files

def get_noc_data():
    result = []
    with open('data/NOC-2021-v1.0/NOCs without TEER.csv') as noc_file:
        result = [
            { 
                'noc_code': str(row['Code - NOC 2021 V1.0 as number']),
                'title': row['Class title'],
                'definition': row['Class definition']
            }
            for row in csv.DictReader(noc_file)
        ]
    return result

all_noc_codes = get_noc_data()

# print(json.dumps(default_ef("hello"), indent=2))


# remove records with non-unique noc codes
noc_codes = [code for code in all_noc_codes if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]

# just take a few noc codes for testing
noc_codes = noc_codes[500:550]

# add them to a vector database, this should not involve any LLM
ef = embedding_functions.DefaultEmbeddingFunction()
# embedding_model = SentenceTransformer('multi-qa-MiniLM-L6-cos-v1')
chroma_client = chromadb.PersistentClient('./data/chroma.db')
# chroma_client = chromadb.HttpClient(host='localhost', port=8000)

collection_name = 'noc_codes'
collection = chroma_client.get_or_create_collection(name=collection_name, embedding_function=ef)

collection.add(
    ids=[code['noc_code'] for code in noc_codes],
    # try to not give documents as input, just the metadata
    documents=['NOC Code ' + code['noc_code'] + ': ' + code['title'] + ': ' + code['definition'] for code in noc_codes],
    metadatas=[
        {
            'top_level_noc': code['noc_code'][0],
            'teer': code['noc_code'][1] if len(code['noc_code']) >= 2 else 'n/a',
            'code': code['noc_code'],
            'title': code['title'],
        } for code in noc_codes
    ]
)

def read_job_description(job_name):
    with open('./jobdescriptions/'+ job_name+ '.txt', 'r') as file:
        content = file.read()
    return content

query_text = read_job_description('pet_groomers_and_animal_care_workers')

print('xxxxx results xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
results = collection.query(
    query_texts=[query_text],
    n_results=4
)
print(json.dumps(results, indent=2))



# get the top level noc code from user  
# query the vector database for noc codes matching the top level noc code
# query to the database: pull noc documents that have noc codes starting with X, and be similar to job description Y
# pass these documents to the LLM model to get the noc code that most closely match the job description, is this even needindg an LLM at all?

