import csv
import json
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DATA_PATH = "./data/chroma.db/"
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "demo_docs"

client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

collection = client.create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_func,
    metadata={"hnsw:space": "cosine"},
)


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
noc_codes = [code for code in all_noc_codes if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]
noc_codes = noc_codes[500:550]

# documents = ['NOC Code ' + code['noc_code'] + ': ' + code['title'] + ': ' + code['definition'] for code in noc_codes]

documents = ['NOC Code ' + code['noc_code'] + ': ' + code['title'] + ': ' + code['definition'] for code in noc_codes]
ids = [code['noc_code'] for code in noc_codes]
metadatas = [{'title': code['title'], 'code': code['noc_code']} for code in noc_codes]

# documents = [
    # "The latest iPhone model comes with impressive features and a powerful camera.",
    # "Exploring the beautiful beaches and vibrant culture of Bali is a dream for many travelers.",
    # "Einstein's theory of relativity revolutionized our understanding of space and time.",
    # "Traditional Italian pizza is famous for its thin crust, fresh ingredients, and wood-fired ovens.",
    # "The American Revolution had a profound impact on the birth of the United States as a nation.",
    # "Regular exercise and a balanced diet are essential for maintaining good physical health.",
    # "Leonardo da Vinci's Mona Lisa is considered one of the most iconic paintings in art history.",
    # "Climate change poses a significant threat to the planet's ecosystems and biodiversity.",
    # "Startup companies often face challenges in securing funding and scaling their operations.",
    # "Beethoven's Symphony No. 9 is celebrated for its powerful choral finale, 'Ode to Joy.'",
# ]

collection.add(documents=documents, ids=ids, metadatas=metadatas)

query_results = collection.query( query_texts=["I need to take my pet to the groomer"], n_results=1,)

query_results.keys()


print(query_results["documents"])


print(query_results["ids"])


print(query_results["distances"])


print(query_results["metadatas"])

