import csv
import json
import chromadb

# read noc codes from files

all_noc_codes = []
with open('data/NOC-2021-v1.0/NOCs without TEER.csv') as noc_file:
    all_noc_codes = [
        { 
            'noc_code': str(row['Code - NOC 2021 V1.0 as number']),
            'title': row['Class title'],
            'definition': row['Class definition']
        }
        for row in csv.DictReader(noc_file)
    ]

# remove records with non-unique noc codes

noc_codes = [code for code in all_noc_codes if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]

# just take a few noc codes for testing
noc_codes = noc_codes[500:510]

# add them to a vector database, this should not involve any LLM
chroma_client = chromadb.Client()
collection = chroma_client.create_collection(name="my_collection")

collection.add(
    ids=[code['noc_code'] for code in noc_codes],
    documents=['NOC Code ' + code['noc_code'] + ': ' + code['title'] + ': ' + code['definition'] for code in noc_codes],
    metadatas=[
        {
            'top_level_noc': code['noc_code'][0],
            'teer': code['noc_code'][1] if len(code['noc_code']) >= 2 else 'n/a',
            'code': code['noc_code'], 
        } for code in noc_codes
    ]
)

query_text = 'Labourers in textile processing perform a variety of manual duties to assist in processing fibres into yarn or thread, or to assist in weaving, knitting, bleaching, dyeing or finishing textile fabrics or other textile products. Labourers in textile cutting cut fabric, fur, or leather to make parts for garments, linens, shoes and other articles.'

results = collection.query(
    query_texts=[query_text],
    n_results=4
)
print(json.dumps(results, indent=2))



# get the top level noc code from user  
# query the vector database for noc codes matching the top level noc code
# query to the database: pull noc documents that have noc codes starting with X, and be similar to job description Y
# pass these documents to the LLM model to get the noc code that most closely match the job description, is this even needindg an LLM at all?

